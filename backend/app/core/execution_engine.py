"""
Execution Engine — the top-level orchestrator.

Workflow:
  1. Load broker adapter from registry
  2. Authenticate with broker
  3. Fetch current holdings
  4. Compute delta (or use explicit instructions)
  5. Route orders through OrderRouter (with retry + rate limiting)
  6. Persist results to database
  7. Trigger notifications (WebSocket + Webhook + Console)
"""
import uuid
from datetime import datetime
from typing import List, Optional, Callable, Awaitable
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import get_adapter, BrokerCredentials
from app.adapters.base import OrderStatus
from app.core.delta_calculator import DeltaCalculator
from app.core.order_router import OrderRouter
from app.schemas.portfolio import PortfolioUpload, DeltaOrder
from app.models.execution import ExecutionBatch, Order
from app.config import settings

logger = structlog.get_logger()

# Type alias for progress callback
ProgressCallback = Callable[[DeltaOrder, object, int, int], Awaitable[None]]


class ExecutionEngine:
    """
    Orchestrates the full portfolio execution lifecycle.
    """

    def __init__(self, db: AsyncSession, notification_service=None):
        self.db = db
        self.notification_service = notification_service
        self.delta_calculator = DeltaCalculator()

    async def execute(
        self,
        user_id: str,
        broker: str,
        credentials: BrokerCredentials,
        portfolio: PortfolioUpload,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionBatch:
        """
        Main execution entry point. Called by the API endpoint.

        Args:
            user_id: The authenticated user's ID.
            broker: Broker name (e.g., "zerodha").
            credentials: Pre-loaded broker credentials.
            portfolio: Target portfolio upload payload.
            on_progress: Optional async callback for real-time WebSocket updates.

        Returns:
            The completed ExecutionBatch ORM object.
        """
        batch_id = str(uuid.uuid4())
        logger.info("engine.start", batch_id=str(batch_id), broker=broker, user_id=str(user_id))

        # ── Step 1: Create execution batch record ────────────────────────
        batch = ExecutionBatch(
            id=batch_id,
            user_id=user_id,
            broker=broker,
            execution_type="PENDING",
            status="IN_PROGRESS",
            target_portfolio={"holdings": [h.model_dump() for h in portfolio.holdings]},
            current_holdings=[],
            delta_orders=[],
            summary={},
        )
        self.db.add(batch)
        await self.db.flush()

        try:
            # ── Step 2: Get broker adapter ───────────────────────────────
            adapter = get_adapter(broker, credentials, paper_trading=settings.PAPER_TRADING)

            # ── Step 3: Fetch current holdings ──────────────────────────
            current_holdings = await adapter.get_holdings()
            batch.current_holdings = [
                {
                    "symbol": h.symbol,
                    "exchange": h.exchange,
                    "quantity": h.quantity,
                    "avg_price": str(h.avg_price),
                }
                for h in current_holdings
            ]

            # ── Step 4: Determine execution type & compute delta ─────────
            has_explicit_instructions = any(
                h.instruction is not None for h in portfolio.holdings
            )

            if portfolio.execution_type == "REBALANCE" or has_explicit_instructions:
                # Explicit rebalance instructions provided
                batch.execution_type = "REBALANCE"
                delta_orders = self.delta_calculator.apply_explicit_instructions(
                    portfolio.holdings
                )
            elif not current_holdings:
                # No existing holdings → first-time portfolio
                batch.execution_type = "FIRST_TIME"
                delta_orders = self.delta_calculator.compute([], portfolio.holdings)
            else:
                # Auto-detect: compute delta from current vs target
                batch.execution_type = "REBALANCE"
                delta_orders = self.delta_calculator.compute(
                    current_holdings, portfolio.holdings
                )

            batch.delta_orders = [d.model_dump() for d in delta_orders]
            await self.db.flush()

            logger.info(
                "engine.delta_computed",
                batch_id=str(batch_id),
                execution_type=batch.execution_type,
                order_count=len(delta_orders),
            )

            if not delta_orders:
                # Portfolio is already at target — nothing to do
                batch.status = "COMPLETED"
                batch.summary = {
                    "message": "Portfolio already matches target. No trades needed.",
                    "total_orders": 0,
                    "filled": 0,
                    "failed": 0,
                }
                batch.completed_at = datetime.utcnow()
                await self.db.flush()
                return batch

            # ── Step 5: Execute orders via OrderRouter ───────────────────
            router = OrderRouter(adapter=adapter)
            results = await router.execute_orders(delta_orders, on_progress=on_progress)

            # ── Step 6: Persist orders to DB ─────────────────────────────
            filled_count = 0
            failed_count = 0
            partial_count = 0
            order_records: List[Order] = []

            for delta, result in results:
                order_status = result.status.value if result.status else "FAILED"

                if result.status == OrderStatus.FILLED:
                    filled_count += 1
                elif result.status in (OrderStatus.REJECTED, OrderStatus.FAILED, OrderStatus.CANCELLED):
                    failed_count += 1
                elif result.status == OrderStatus.PARTIALLY_FILLED:
                    partial_count += 1

                order = Order(
                    id=str(uuid.uuid4()),
                    batch_id=batch_id,
                    user_id=user_id,
                    broker=broker,
                    broker_order_id=result.broker_order_id,
                    symbol=delta.symbol,
                    exchange=delta.exchange,
                    order_type=delta.order_type,
                    instruction_type=delta.instruction_type.value,
                    quantity=delta.quantity,
                    order_status=order_status,
                    filled_quantity=result.filled_quantity,
                    avg_fill_price=result.avg_fill_price,
                    error_message=result.error,
                    raw_response=result.raw_response or {},
                    placed_at=datetime.utcnow() if result.success else None,
                    filled_at=datetime.utcnow() if result.status == OrderStatus.FILLED else None,
                )
                self.db.add(order)
                order_records.append(order)

            # ── Step 7: Update batch summary ─────────────────────────────
            total = len(results)
            if failed_count == total:
                batch.status = "FAILED"
            elif failed_count > 0 or partial_count > 0:
                batch.status = "PARTIAL"
            else:
                batch.status = "COMPLETED"

            batch.summary = {
                "total_orders": total,
                "filled": filled_count,
                "failed": failed_count,
                "partial": partial_count,
                "paper_trading": settings.PAPER_TRADING,
            }
            batch.completed_at = datetime.utcnow()
            await self.db.flush()

            logger.info(
                "engine.complete",
                batch_id=str(batch_id),
                status=batch.status,
                filled=filled_count,
                failed=failed_count,
            )

            # ── Step 8: Send notifications ───────────────────────────────
            if self.notification_service:
                await self.notification_service.send_execution_complete(
                    batch=batch,
                    orders=order_records,
                    user_id=user_id,
                )

            return batch

        except Exception as e:
            logger.error("engine.error", batch_id=str(batch_id), error=str(e), exc_info=True)
            batch.status = "FAILED"
            batch.summary = {"error": str(e)}
            batch.completed_at = datetime.utcnow()
            await self.db.flush()
            raise


