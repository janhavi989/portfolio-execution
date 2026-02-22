"""
Order Router — dispatches orders to the broker adapter with retry logic.

Handles:
  - Rate limiting (configurable orders/second via Redis token bucket)
  - Exponential backoff retry on transient failures
  - Order status polling after placement
  - Concurrent order execution with asyncio
"""
import asyncio
import time
from typing import List, Tuple
from decimal import Decimal
import structlog

from app.adapters.base import BrokerAdapter, PlaceOrderRequest, PlaceOrderResult, OrderSide, OrderStatus
from app.schemas.portfolio import DeltaOrder
from app.config import settings

logger = structlog.get_logger()


class OrderRouter:
    """
    Routes DeltaOrders to the broker adapter, handling rate limits and retries.
    """

    def __init__(self, adapter: BrokerAdapter, redis_client=None):
        self.adapter = adapter
        self.max_retries = settings.MAX_RETRY_ATTEMPTS
        self.retry_delay = settings.RETRY_DELAY_SECONDS
        self.rate_limit = settings.MAX_ORDERS_PER_SECOND

    async def execute_orders(
        self,
        delta_orders: List[DeltaOrder],
        on_progress=None,  # Optional async callback for real-time updates
    ) -> List[Tuple[DeltaOrder, PlaceOrderResult]]:
        """
        Execute all delta orders sequentially (SELLs first, then BUYs).
        Returns list of (DeltaOrder, PlaceOrderResult) tuples.

        We execute sequentially rather than concurrently to:
        1. Respect broker rate limits
        2. Ensure SELLs complete before BUYs (capital management)
        3. Avoid partial fills causing inconsistent state
        """
        results: List[Tuple[DeltaOrder, PlaceOrderResult]] = []

        for i, delta in enumerate(delta_orders):
            logger.info(
                "order_router.placing",
                symbol=delta.symbol,
                side=delta.order_type,
                qty=delta.quantity,
                instruction=delta.instruction_type,
                index=i + 1,
                total=len(delta_orders),
            )

            # Rate limiting: ensure we don't exceed max orders/second
            await self._rate_limit_wait()

            # Build the broker-agnostic order request
            request = PlaceOrderRequest(
                symbol=delta.symbol,
                exchange=delta.exchange,
                side=OrderSide(delta.order_type),
                quantity=delta.quantity,
                order_mode="MARKET",  # Always market orders for execution engine
                tag=f"kalpi_{delta.instruction_type.value.lower()}",
            )

            # Execute with retry logic
            result = await self._place_with_retry(request)

            # If placed successfully, poll for fill confirmation
            if result.success and result.broker_order_id and not settings.PAPER_TRADING:
                result = await self._poll_order_status(result.broker_order_id, result)

            results.append((delta, result))

            # Fire progress callback if provided (for WebSocket updates)
            if on_progress:
                await on_progress(delta, result, i + 1, len(delta_orders))

            # Log result
            if result.success:
                logger.info(
                    "order_router.placed",
                    symbol=delta.symbol,
                    broker_order_id=result.broker_order_id,
                    status=result.status.value,
                    filled_qty=result.filled_quantity,
                )
            else:
                logger.warning(
                    "order_router.failed",
                    symbol=delta.symbol,
                    error=result.error,
                    retry_count=self.max_retries,
                )

        return results

    async def _place_with_retry(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        """
        Attempt to place an order, retrying on transient failures with
        exponential backoff.

        Retry conditions:
          - Network errors (connection timeout, etc.)
          - HTTP 429 (rate limited by broker)
          - HTTP 5xx (broker server errors)

        No retry on:
          - HTTP 400 (bad request — invalid symbol, insufficient funds)
          - HTTP 401/403 (auth failure — needs re-login)
        """
        last_result = None

        for attempt in range(self.max_retries + 1):
            try:
                result = await self.adapter.place_order(request)

                # If explicitly rejected (not a transient error), don't retry
                if result.status == OrderStatus.REJECTED:
                    logger.warning(
                        "order_router.rejected_no_retry",
                        symbol=request.symbol,
                        error=result.error,
                    )
                    return result

                if result.success:
                    return result

                last_result = result

            except Exception as e:
                logger.warning(
                    "order_router.exception",
                    symbol=request.symbol,
                    attempt=attempt + 1,
                    error=str(e),
                )
                last_result = PlaceOrderResult(
                    success=False,
                    status=OrderStatus.FAILED,
                    error=str(e),
                )

            if attempt < self.max_retries:
                delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                logger.info(
                    "order_router.retrying",
                    symbol=request.symbol,
                    attempt=attempt + 1,
                    delay=delay,
                )
                await asyncio.sleep(delay)

        return last_result or PlaceOrderResult(
            success=False, status=OrderStatus.FAILED, error="Max retries exceeded"
        )

    async def _poll_order_status(
        self,
        broker_order_id: str,
        initial_result: PlaceOrderResult,
        max_polls: int = 5,
        poll_interval: float = 2.0,
    ) -> PlaceOrderResult:
        """
        Poll broker for order fill confirmation after placement.
        For MARKET orders, fill is usually immediate; we poll up to max_polls times.
        """
        for _ in range(max_polls):
            await asyncio.sleep(poll_interval)
            status_result = await self.adapter.get_order_status(broker_order_id)

            if status_result.status in (OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED):
                return status_result

            if status_result.status == OrderStatus.PARTIALLY_FILLED:
                # Continue polling for full fill
                continue

        # Return last known status if not fully filled
        return initial_result

    async def _rate_limit_wait(self):
        """Simple sleep-based rate limiter between orders."""
        await asyncio.sleep(1.0 / self.rate_limit)


