"""
Upstox Broker Adapter — Upstox API v2
──────────────────────────────────────
Upstox uses OAuth2 Authorization Code flow.
  1. Redirect user to login URL
  2. Exchange code for access_token via POST /login/authorization/token

Real SDK: upstox-python-sdk (pip install upstox-python-sdk)
Docs: https://upstox.com/developer/api-documentation/

In paper trading mode, all API calls are simulated.
"""
import httpx
import structlog
from typing import List
from decimal import Decimal
from datetime import datetime, timedelta

from app.adapters.base import (
    BrokerAdapter, BrokerCredentials, AuthResult,
    Holding, PlaceOrderRequest, PlaceOrderResult, OrderStatus,
    FundsData, FundsSegment,
)

logger = structlog.get_logger()

UPSTOX_BASE_URL = "https://api.upstox.com/v2"
UPSTOX_AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


class UpstoxAdapter(BrokerAdapter):
    """
    Adapter for Upstox API v2.

    Authentication flow:
    ┌─────────────────────────────────────────────────────────────┐
    │ 1. GET /login/authorization/dialog?client_id=...            │
    │    &redirect_uri=...&response_type=code                     │
    │ 2. User authorizes → callback with ?code=<auth_code>        │
    │ 3. POST /login/authorization/token                          │
    │    Body: code + client_id + client_secret + redirect_uri    │
    │    → access_token                                           │
    └─────────────────────────────────────────────────────────────┘
    """

    broker_name = "upstox"
    REDIRECT_URI = "https://127.0.0.1/"

    def get_login_url(self) -> str:
        return (
            f"{UPSTOX_AUTH_URL}?response_type=code"
            f"&client_id={self.credentials.api_key}"
            f"&redirect_uri={self.REDIRECT_URI}"
        )

    async def authenticate(self) -> AuthResult:
        if self.paper_trading:
            logger.info("upstox.authenticate", mode="paper_trading")
            return AuthResult(
                success=True,
                access_token="PAPER_UPSTOX_TOKEN",
                client_id="UP0001",
                expires_at=(datetime.utcnow() + timedelta(hours=24)).isoformat(),
                raw_response={"paper_trading": True},
            )

        auth_code = self.credentials.request_token
        if not auth_code:
            return AuthResult(success=False, error="auth_code (request_token) required for Upstox")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    UPSTOX_TOKEN_URL,
                    data={
                        "code": auth_code,
                        "client_id": self.credentials.api_key,
                        "client_secret": self.credentials.api_secret,
                        "redirect_uri": self.REDIRECT_URI,
                        "grant_type": "authorization_code",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return AuthResult(
                    success=True,
                    access_token=data.get("access_token"),
                    client_id=data.get("user_id"),
                    expires_at=data.get("expires_in"),
                    raw_response=data,
                )
        except Exception as e:
            logger.error("upstox.auth_error", error=str(e))
            return AuthResult(success=False, error=str(e))

    async def get_holdings(self) -> List[Holding]:
        if self.paper_trading:
            return self._mock_holdings()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{UPSTOX_BASE_URL}/portfolio/long-term-holdings",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                raw = resp.json().get("data", [])
                return [
                    Holding(
                        symbol=h["tradingsymbol"],
                        exchange=h["exchange"].replace("NSE_EQ", "NSE").replace("BSE_EQ", "BSE"),
                        quantity=h["quantity"],
                        avg_price=Decimal(str(h.get("average_price", 0))),
                        current_price=Decimal(str(h.get("last_price", 0))),
                        pnl=Decimal(str(h.get("pnl", 0))),
                    )
                    for h in raw
                ]
        except Exception as e:
            logger.error("upstox.get_holdings_error", error=str(e))
            return []

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if self.paper_trading:
            return self._simulate_order(request)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{UPSTOX_BASE_URL}/order/place",
                    json={
                        "quantity": request.quantity,
                        "product": "D",  # D=Delivery
                        "validity": "DAY",
                        "price": float(request.price) if request.price else 0,
                        "tag": request.tag or "kalpi",
                        "instrument_token": f"{request.exchange}_EQ|{request.symbol}",
                        "order_type": "MARKET" if request.order_mode == "MARKET" else "LIMIT",
                        "transaction_type": request.side.value,
                        "disclosed_quantity": 0,
                        "trigger_price": 0,
                        "is_amo": False,
                    },
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return PlaceOrderResult(
                    success=True,
                    broker_order_id=data.get("order_id"),
                    status=OrderStatus.PLACED,
                    raw_response=data,
                )
        except Exception as e:
            return PlaceOrderResult(success=False, status=OrderStatus.FAILED, error=str(e))

    async def get_order_status(self, broker_order_id: str) -> PlaceOrderResult:
        if self.paper_trading:
            return PlaceOrderResult(success=True, broker_order_id=broker_order_id, status=OrderStatus.FILLED, filled_quantity=1)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{UPSTOX_BASE_URL}/order/details?order_id={broker_order_id}",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                status_map = {
                    "complete": OrderStatus.FILLED,
                    "rejected": OrderStatus.REJECTED,
                    "cancelled": OrderStatus.CANCELLED,
                    "open": OrderStatus.PLACED,
                }
                return PlaceOrderResult(
                    success=True,
                    broker_order_id=broker_order_id,
                    status=status_map.get(data.get("status", "").lower(), OrderStatus.PENDING),
                    filled_quantity=data.get("filled_quantity", 0),
                    avg_fill_price=Decimal(str(data.get("average_price", 0))) or None,
                    raw_response=data,
                )
        except Exception as e:
            return PlaceOrderResult(success=False, status=OrderStatus.FAILED, error=str(e))

    async def cancel_order(self, broker_order_id: str) -> bool:
        if self.paper_trading:
            return True
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"{UPSTOX_BASE_URL}/order/cancel?order_id={broker_order_id}",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                return resp.json().get("status") == "success"
        except Exception:
            return False

    async def get_funds(self) -> FundsData:
        """Fetch funds from Upstox API v2 (GET /user/get-funds-and-margin)."""
        if self.paper_trading:
            return self._mock_funds()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{UPSTOX_BASE_URL}/user/get-funds-and-margin",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                equity_raw = data.get("equity", {})
                commodity_raw = data.get("commodity", {})

                def _parse(d: dict) -> FundsSegment:
                    return FundsSegment(
                        enabled=True,
                        net=Decimal(str(d.get("net_margin", 0))),
                        cash=Decimal(str(d.get("available_margin", 0))),
                        opening_balance=Decimal(str(d.get("available_margin", 0))),
                        live_balance=Decimal(str(d.get("net_margin", 0))),
                        collateral=Decimal(str(d.get("collateral", 0))),
                        debits=Decimal(str(d.get("used_margin", 0))),
                        span=Decimal("0"),
                        exposure=Decimal("0"),
                    )

                return FundsData(
                    success=True,
                    equity=_parse(equity_raw),
                    commodity=_parse(commodity_raw) if commodity_raw else None,
                    raw_response=data,
                )
        except Exception as e:
            return FundsData(success=False, error=str(e))

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _mock_holdings(self) -> List[Holding]:
        return [
            Holding("SBIN", "NSE", 50, Decimal("550"), Decimal("570"), Decimal("1000")),
            Holding("TATASTEEL", "NSE", 30, Decimal("130"), Decimal("135"), Decimal("150")),
        ]


