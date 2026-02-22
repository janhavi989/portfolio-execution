"""
Notification Service — multi-channel notification dispatch.

Channels:
  1. WebSocket  → real-time push to frontend (primary)
  2. Webhook    → HTTP POST to configured URL (for external consumers)
  3. Console    → structured log output (always active, for debugging)

The notification service is called by the ExecutionEngine after all orders
are processed, summarizing results across all three channels.
"""
import uuid
import json
from datetime import datetime
from typing import List
import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.websocket_manager import ws_manager
from app.models.execution import ExecutionBatch, Order, Notification
from app.config import settings

logger = structlog.get_logger()


class NotificationService:
    """
    Dispatches execution completion notifications via WebSocket, Webhook, and Console.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_execution_complete(
        self,
        batch: ExecutionBatch,
        orders: List[Order],
        user_id: str,
    ):
        """
        Build the notification payload and dispatch it to all channels.
        Called by ExecutionEngine after all orders are processed.
        """
        payload = self._build_payload(batch, orders)

        # Dispatch to all channels concurrently
        await self._notify_console(payload)
        await self._notify_websocket(str(user_id), payload)
        await self._notify_webhook(payload)

        # Persist notification records
        await self._persist_notification(user_id, batch.id, payload)

    def _build_payload(self, batch: ExecutionBatch, orders: List[Order]) -> dict:
        """Build the standardized notification payload."""
        order_summaries = [
            {
                "symbol": o.symbol,
                "order_type": o.order_type,
                "instruction_type": o.instruction_type,
                "quantity": o.quantity,
                "status": o.order_status,
                "filled_quantity": o.filled_quantity,
                "avg_fill_price": float(o.avg_fill_price) if o.avg_fill_price else None,
                "broker_order_id": o.broker_order_id,
                "error_message": o.error_message,
            }
            for o in orders
        ]

        filled = sum(1 for o in orders if o.order_status == "FILLED")
        failed = sum(1 for o in orders if o.order_status in ("REJECTED", "FAILED"))
        partial = sum(1 for o in orders if o.order_status == "PARTIALLY_FILLED")

        return {
            "event": "EXECUTION_COMPLETE",
            "batch_id": str(batch.id),
            "user_id": str(batch.user_id),
            "broker": batch.broker,
            "execution_type": batch.execution_type,
            "batch_status": batch.status,
            "total_orders": len(orders),
            "filled_orders": filled,
            "failed_orders": failed,
            "partial_orders": partial,
            "orders": order_summaries,
            "summary": batch.summary,
            "timestamp": datetime.utcnow().isoformat(),
            "message": self._build_message(batch.status, len(orders), filled, failed),
            "paper_trading": settings.PAPER_TRADING,
        }

    def _build_message(self, status: str, total: int, filled: int, failed: int) -> str:
        if status == "COMPLETED":
            return f"[OK] Execution complete: {filled}/{total} orders filled successfully."
        elif status == "PARTIAL":
            return f"[WARN] Partial execution: {filled} filled, {failed} failed out of {total} orders."
        elif status == "FAILED":
            return f"[FAIL] Execution failed: All {total} orders failed."
        return f"[INFO] Execution finished with status: {status}"

    async def _notify_console(self, payload: dict):
        """
        Channel 1: Console / Structured Log.
        Always fires — useful for debugging and audit trail.
        """
        logger.info(
            "NOTIFICATION:EXECUTION_COMPLETE",
            batch_id=payload["batch_id"],
            broker=payload["broker"],
            status=payload["batch_status"],
            total=payload["total_orders"],
            filled=payload["filled_orders"],
            failed=payload["failed_orders"],
            message=payload["message"],
            paper_trading=payload.get("paper_trading", True),
        )

    async def _notify_websocket(self, user_id: str, payload: dict):
        """
        Channel 2: WebSocket push to connected frontend clients.
        Sends the full payload as a JSON message.
        """
        try:
            await ws_manager.send_to_user(user_id, {
                "type": "EXECUTION_COMPLETE",
                "data": payload,
            })
            logger.info("notification.websocket.sent", user_id=user_id, batch_id=payload["batch_id"])
        except Exception as e:
            logger.warning("notification.websocket.failed", user_id=user_id, error=str(e))

    async def _notify_webhook(self, payload: dict):
        """
        Channel 3: HTTP Webhook POST to configured URL.
        Sends the payload as JSON to the webhook endpoint.
        """
        if not settings.WEBHOOK_URL:
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    settings.WEBHOOK_URL,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Kalpi-Event": "EXECUTION_COMPLETE",
                        "X-Kalpi-Batch-ID": payload["batch_id"],
                    },
                )
                logger.info(
                    "notification.webhook.sent",
                    url=settings.WEBHOOK_URL,
                    status_code=resp.status_code,
                    batch_id=payload["batch_id"],
                )
        except Exception as e:
            logger.warning("notification.webhook.failed", url=settings.WEBHOOK_URL, error=str(e))

    async def _persist_notification(
        self,
        user_id: str,
        batch_id: str,
        payload: dict,
    ):
        """Persist notification record to database for audit trail."""
        try:
            for channel in ("WEBSOCKET", "WEBHOOK", "CONSOLE"):
                notif = Notification(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    batch_id=batch_id,
                    channel=channel,
                    payload=payload,
                    delivered=True,
                    delivered_at=datetime.utcnow(),
                )
                self.db.add(notif)
            await self.db.flush()
        except Exception as e:
            logger.warning("notification.persist_failed", error=str(e))


    async def send_order_progress(
        self,
        user_id: str,
        delta,
        result,
        current: int,
        total: int,
    ):
        """
        Send real-time order progress update via WebSocket during execution.
        Called by OrderRouter's on_progress callback.
        """
        await ws_manager.send_to_user(user_id, {
            "type": "ORDER_PROGRESS",
            "data": {
                "symbol": delta.symbol,
                "order_type": delta.order_type,
                "instruction_type": delta.instruction_type.value if hasattr(delta.instruction_type, 'value') else delta.instruction_type,
                "quantity": delta.quantity,
                "status": result.status.value if result.status else "UNKNOWN",
                "broker_order_id": result.broker_order_id,
                "filled_quantity": result.filled_quantity,
                "error": result.error,
                "progress": {"current": current, "total": total},
                "timestamp": datetime.utcnow().isoformat(),
            },
        })


