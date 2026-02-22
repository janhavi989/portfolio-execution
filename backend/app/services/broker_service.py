"""
Broker Service — manages broker session persistence and credential loading.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.models.broker_session import BrokerSession
from app.adapters import get_adapter, BrokerCredentials
from app.adapters.base import AuthResult
from app.schemas.broker import BrokerConnectRequest
from app.config import settings

logger = structlog.get_logger()


class BrokerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def connect_broker(
        self,
        user_id: str,
        request: BrokerConnectRequest,
    ) -> tuple[bool, str, Optional[BrokerSession]]:
        credentials = BrokerCredentials(
            api_key=request.api_key,
            api_secret=request.api_secret,
            client_id=request.client_id,
            request_token=request.request_token,
            totp_secret=request.totp_secret,
            password=request.password,
        )

        adapter = get_adapter(request.broker.value, credentials, paper_trading=settings.PAPER_TRADING)
        auth_result: AuthResult = await adapter.authenticate()

        if not auth_result.success:
            logger.warning("broker_service.auth_failed", broker=request.broker, error=auth_result.error)
            return False, auth_result.error or "Authentication failed", None

        existing = await self.db.execute(
            select(BrokerSession).where(
                BrokerSession.user_id == user_id,
                BrokerSession.broker == request.broker.value,
            )
        )
        session = existing.scalar_one_or_none()

        # Build a full credential snapshot saved in session_data so nothing is lost
        credential_snapshot = {
            "api_key": request.api_key,
            "api_secret": request.api_secret,
            "client_id": request.client_id,
            "request_token": request.request_token,
            "totp_secret": request.totp_secret,
            "password": request.password,
            "access_token": auth_result.access_token,
            "refresh_token": auth_result.refresh_token,
            "broker_client_id": auth_result.client_id,
            "expires_at": auth_result.expires_at,
            "auth_raw": auth_result.raw_response or {},
        }

        if session:
            session.access_token = auth_result.access_token
            session.refresh_token = auth_result.refresh_token
            session.client_id = auth_result.client_id or request.client_id
            session.api_key = request.api_key
            session.api_secret = request.api_secret
            session.is_active = True
            session.updated_at = datetime.utcnow()
            session.session_data = credential_snapshot
        else:
            session = BrokerSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                broker=request.broker.value,
                access_token=auth_result.access_token,
                refresh_token=auth_result.refresh_token,
                client_id=auth_result.client_id or request.client_id,
                api_key=request.api_key,
                api_secret=request.api_secret,
                is_active=True,
                session_data=credential_snapshot,
            )
            self.db.add(session)

        await self.db.flush()
        logger.info("broker_service.connected", broker=request.broker, user_id=user_id)
        return True, "Broker connected successfully", session

    async def get_active_session(self, user_id: str, broker: str) -> Optional[BrokerSession]:
        result = await self.db.execute(
            select(BrokerSession).where(
                BrokerSession.user_id == user_id,
                BrokerSession.broker == broker,
                BrokerSession.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def get_credentials(self, user_id: str, broker: str) -> Optional[BrokerCredentials]:
        session = await self.get_active_session(user_id, broker)
        if not session:
            return None
        return BrokerCredentials(
            api_key=session.api_key or "",
            api_secret=session.api_secret,
            client_id=session.client_id,
            access_token=session.access_token,
            refresh_token=session.refresh_token,
        )

    async def disconnect_broker(self, user_id: str, broker: str) -> bool:
        session = await self.get_active_session(user_id, broker)
        if not session:
            return False
        session.is_active = False
        session.updated_at = datetime.utcnow()
        await self.db.flush()
        return True

    async def list_sessions(self, user_id: str) -> list[BrokerSession]:
        result = await self.db.execute(
            select(BrokerSession).where(BrokerSession.user_id == user_id)
        )
        return list(result.scalars().all())
