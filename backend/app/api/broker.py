"""
Broker API endpoints.
  POST /broker/connect          → authenticate with a broker
  GET  /broker/sessions         → list all broker sessions
  GET  /broker/sessions/{broker}→ get specific session
  DELETE /broker/disconnect/{broker} → disconnect a broker
  GET  /broker/login-url/{broker}    → get OAuth login URL
  GET  /broker/holdings/{broker}     → fetch current holdings
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database import get_db
from app.models.user import User
from app.schemas.broker import BrokerConnectRequest, BrokerSessionOut, BrokerLoginUrlResponse, BrokerCredentialsOut
from app.services.auth_service import get_current_user, get_current_user_from_query
from app.services.broker_service import BrokerService
from app.adapters import get_adapter, BrokerCredentials, BROKER_REGISTRY
from app.config import settings
from app.core.zerodha_token_fetcher import fetch_zerodha_request_token

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.post("/connect", response_model=BrokerSessionOut)
async def connect_broker(
    payload: BrokerConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Authenticate with a broker and save the session.
    In paper trading mode, any API key will work.
    """
    svc = BrokerService(db)
    success, message, session = await svc.connect_broker(current_user.id, payload)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return session


@router.get("/sessions", response_model=List[BrokerSessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all broker sessions for the current user."""
    svc = BrokerService(db)
    sessions = await svc.list_sessions(current_user.id)
    return sessions


@router.delete("/disconnect/{broker}")
async def disconnect_broker(
    broker: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disconnect (deactivate) a broker session."""
    svc = BrokerService(db)
    success = await svc.disconnect_broker(current_user.id, broker)
    if not success:
        raise HTTPException(status_code=404, detail=f"No active session for broker '{broker}'")
    return {"message": f"Disconnected from {broker}"}


@router.get("/login-url/{broker}", response_model=BrokerLoginUrlResponse)
async def get_login_url(
    broker: str,
    api_key: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the OAuth login URL for brokers that use web-based authentication
    (Zerodha, Fyers, Upstox). The user must visit this URL to get the
    request_token/auth_code to pass to /connect.
    """
    if broker not in BROKER_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown broker: {broker}")

    credentials = BrokerCredentials(api_key=api_key)
    adapter = get_adapter(broker, credentials, paper_trading=settings.PAPER_TRADING)
    login_url = adapter.get_login_url()

    instructions_map = {
        "zerodha": "Visit the URL, login with your Zerodha credentials, and copy the request_token from the redirect URL.",
        "fyers": "Visit the URL, login with your Fyers credentials, and copy the auth_code from the redirect URL.",
        "upstox": "Visit the URL, login with your Upstox credentials, and copy the code from the redirect URL.",
        "angelone": "AngelOne uses TOTP-based auth. Provide client_id, password, and totp_secret directly.",
        "groww": "Groww uses API Key auth. Provide api_key, api_secret, and client_id directly.",
    }

    return BrokerLoginUrlResponse(
        broker=broker,
        login_url=login_url or f"Direct API auth — no login URL needed for {broker}",
        instructions=instructions_map.get(broker, "Follow broker-specific auth flow."),
    )


@router.get("/zerodha/fetch-token")
async def zerodha_fetch_token(
    api_key: str = Query(..., description="Your Zerodha Kite Connect API key"),
    current_user: User = Depends(get_current_user_from_query),
):
    """
    Semi-automated Zerodha request_token capture via Selenium.

    Opens a real Chrome browser window pointed at the Kite Connect login page.
    The user types their password + TOTP manually in the browser.
    We watch the URL for the redirect containing ?request_token=... and return it.

    Streams Server-Sent Events (SSE) so the frontend gets live status updates:
      data: {"status": "opening",  "message": "..."}
      data: {"status": "waiting",  "message": "..."}
      data: {"status": "success",  "message": "...", "request_token": "<TOKEN>"}
      data: {"status": "error",    "message": "..."}
    """
    async def _event_stream():
        async for event in fetch_zerodha_request_token(api_key):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: {\"status\": \"done\"}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


@router.get("/credentials/{broker}", response_model=BrokerCredentialsOut)
async def get_credentials(
    broker: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve all saved credentials for a connected broker session.
    Returns api_key, api_secret, access_token, request_token, etc.
    Sensitive fields are only returned to the authenticated owner.
    """
    svc = BrokerService(db)
    session = await svc.get_active_session(current_user.id, broker)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"No active session for broker '{broker}'. Please connect first.",
        )

    # Pull extra fields from session_data snapshot
    snap = session.session_data or {}
    return BrokerCredentialsOut(
        broker=session.broker,
        is_active=session.is_active,
        created_at=session.created_at,
        updated_at=session.updated_at,
        api_key=session.api_key,
        api_secret=session.api_secret,
        client_id=session.client_id,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        request_token=snap.get("request_token"),
        totp_secret=snap.get("totp_secret"),
        password=snap.get("password"),
        expires_at=snap.get("expires_at"),
    )


@router.get("/funds/{broker}")
async def get_funds(
    broker: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch live margin/funds from the connected broker.
    This is the definitive validation that the broker token is working —
    a successful response with non-zero balance proves the connection is live.

    For Zerodha this calls GET /user/margins (equity + commodity segments).
    """
    svc = BrokerService(db)
    credentials = await svc.get_credentials(current_user.id, broker)
    if not credentials:
        raise HTTPException(
            status_code=404,
            detail=f"No active session for broker '{broker}'. Please connect first.",
        )

    adapter = get_adapter(broker, credentials, paper_trading=settings.PAPER_TRADING)
    funds = await adapter.get_funds()

    if not funds.success:
        raise HTTPException(status_code=502, detail=f"Failed to fetch funds: {funds.error}")

    def _seg(s):
        if s is None:
            return None
        return {
            "enabled": s.enabled,
            "net": float(s.net),
            "cash": float(s.cash),
            "opening_balance": float(s.opening_balance),
            "live_balance": float(s.live_balance),
            "collateral": float(s.collateral),
            "debits": float(s.debits),
            "span": float(s.span),
            "exposure": float(s.exposure),
        }

    return {
        "broker": broker,
        "paper_trading": settings.PAPER_TRADING,
        "equity": _seg(funds.equity),
        "commodity": _seg(funds.commodity),
    }


@router.get("/holdings/{broker}")
async def get_holdings(
    broker: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch current holdings from the connected broker."""
    svc = BrokerService(db)
    credentials = await svc.get_credentials(current_user.id, broker)
    if not credentials:
        raise HTTPException(
            status_code=404,
            detail=f"No active session for broker '{broker}'. Please connect first.",
        )

    adapter = get_adapter(broker, credentials, paper_trading=settings.PAPER_TRADING)
    holdings = await adapter.get_holdings()
    return {
        "broker": broker,
        "holdings": [
            {
                "symbol": h.symbol,
                "exchange": h.exchange,
                "quantity": h.quantity,
                "avg_price": float(h.avg_price),
                "current_price": float(h.current_price),
                "pnl": float(h.pnl),
            }
            for h in holdings
        ],
        "total_holdings": len(holdings),
    }


@router.get("/supported")
async def get_supported_brokers():
    """List all supported brokers."""
    return {
        "brokers": [
            {
                "name": "zerodha",
                "display_name": "Zerodha",
                "auth_type": "oauth",
                "description": "India's largest discount broker. Uses Kite Connect API.",
            },
            {
                "name": "fyers",
                "display_name": "Fyers",
                "auth_type": "oauth",
                "description": "Tech-first broker with Fyers API v3.",
            },
            {
                "name": "angelone",
                "display_name": "AngelOne",
                "auth_type": "totp",
                "description": "Full-service broker with SmartAPI. Uses TOTP 2FA.",
            },
            {
                "name": "upstox",
                "display_name": "Upstox",
                "auth_type": "oauth",
                "description": "Modern broker with Upstox API v2.",
            },
            {
                "name": "groww",
                "display_name": "Groww",
                "auth_type": "api_key",
                "description": "Popular retail broker with REST API.",
            },
        ]
    }


