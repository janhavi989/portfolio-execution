"""
Notification & WebSocket endpoints.
  WS   /ws/{user_id}                    → WebSocket real-time updates
  POST /notifications/webhook-receiver  → mock webhook receiver (for testing)
  GET  /notifications                   → list notification history
"""
import uuid
from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import structlog

from app.database import get_db
from app.models.user import User
from app.models.execution import Notification
from app.services.websocket_manager import ws_manager
from app.services.auth_service import get_current_user

logger = structlog.get_logger()

router = APIRouter(tags=["Notifications"])


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for real-time execution updates.

    Connect from frontend:
      const ws = new WebSocket(`ws://localhost:8000/ws/${userId}`);
      ws.onmessage = (e) => console.log(JSON.parse(e.data));

    Message types:
      - ORDER_PROGRESS: real-time per-order updates during execution
      - EXECUTION_COMPLETE: final summary after all orders processed
    """
    await ws_manager.connect(user_id, websocket)
    logger.info("ws.client_connected", user_id=user_id)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "CONNECTED",
            "data": {
                "user_id": user_id,
                "message": "Connected to Kalpi Execution Engine. Awaiting trades...",
            }
        })

        # Keep connection alive — wait for disconnect
        while True:
            data = await websocket.receive_text()
            # Echo back ping/pong for connection health checks
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
        logger.info("ws.client_disconnected", user_id=user_id)


@router.post("/api/v1/notifications/webhook-receiver")
async def webhook_receiver(request: Request):
    """
    Mock webhook receiver — receives and logs execution notifications.

    In a real system, this would be YOUR application's endpoint that
    Kalpi calls after execution completes. Here it just logs the payload.
    """
    payload = await request.json()
    logger.info(
        "WEBHOOK_RECEIVED",
        event=payload.get("event"),
        batch_id=payload.get("batch_id"),
        status=payload.get("batch_status"),
        filled=payload.get("filled_orders"),
        failed=payload.get("failed_orders"),
        message=payload.get("message"),
    )
    return {"status": "received", "batch_id": payload.get("batch_id")}


@router.get("/api/v1/notifications", response_model=List[dict])
async def list_notifications(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notification history for the current user."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .limit(limit)
    )
    notifications = result.scalars().all()
    return [
        {
            "id": str(n.id),
            "batch_id": str(n.batch_id),
            "channel": n.channel,
            "event": n.payload.get("event"),
            "status": n.payload.get("batch_status"),
            "message": n.payload.get("message"),
            "delivered": n.delivered,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]



