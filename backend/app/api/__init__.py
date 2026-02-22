from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.broker import router as broker_router
from app.api.execution import router as execution_router
from app.api.notifications import router as notification_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(broker_router)
api_router.include_router(execution_router)
# Notification routes are included directly in main (WebSocket + non-prefixed webhook)

__all__ = ["api_router", "notification_router"]



