"""
WebSocket Connection Manager — manages active WebSocket connections per user.

Allows the execution engine to push real-time updates to connected frontend clients.
"""
from typing import Dict, List
from fastapi import WebSocket
import json
import structlog

logger = structlog.get_logger()


class WebSocketManager:
    """
    Manages WebSocket connections keyed by user_id.
    Multiple tabs/connections per user are supported.
    """

    def __init__(self):
        # user_id → list of active WebSocket connections
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        logger.info("ws.connected", user_id=user_id, total=len(self._connections[user_id]))

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self._connections:
            self._connections[user_id] = [
                ws for ws in self._connections[user_id] if ws != websocket
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("ws.disconnected", user_id=user_id)

    async def send_to_user(self, user_id: str, message: dict):
        """Send a JSON message to all connections for a user."""
        if user_id not in self._connections:
            logger.debug("ws.no_connections", user_id=user_id)
            return

        dead_connections = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_text(json.dumps(message))
            except Exception as e:
                logger.warning("ws.send_failed", user_id=user_id, error=str(e))
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(user_id, ws)

    async def broadcast(self, message: dict):
        """Send a message to ALL connected users."""
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, message)

    def is_connected(self, user_id: str) -> bool:
        return user_id in self._connections and len(self._connections[user_id]) > 0

    def connected_users(self) -> List[str]:
        return list(self._connections.keys())


# Singleton instance shared across the application
ws_manager = WebSocketManager()



