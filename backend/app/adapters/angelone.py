"""
AngelOne Broker Adapter — SmartAPI
────────────────────────────────────
AngelOne (formerly Angel Broking) uses SmartAPI with TOTP-based 2FA.
  1. POST /user/login with clientcode + password + totp
  2. Returns jwtToken (access_token) + refreshToken

Real SDK: smartapi-python (pip install smartapi-python)
Docs: https://smartapi.angelbroking.com/docs

In paper trading mode, all API calls are simulated.
"""
import httpx
import pyotp
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

ANGEL_BASE_URL = "https://apiconnect.angelbroking.com"


class AngelOneAdapter(BrokerAdapter):
    """
    Adapter for AngelOne SmartAPI.

    Authentication flow:
    ┌─────────────────────────────────────────────────────────────┐
    │ 1. POST /rest/auth/angelbroking/user/v1/loginByPassword     │
    │    Body: { clientcode, password, totp }                     │
    │    totp is generated from totp_secret using pyotp           │
    │ 2. Response: { jwtToken, refreshToken, feedToken }          │
    └─────────────────────────────────────────────────────────────┘
    """

    broker_name = "angelone"

    async def authenticate(self) -> AuthResult:
        if self.paper_trading:
            logger.info("angelone.authenticate", mode="paper_trading")
            return AuthResult(
                success=True,
                access_token="PAPER_ANGEL_TOKEN",
                client_id=self.credentials.client_id or "AO0001",
                expires_at=(datetime.utcnow() + timedelta(hours=24)).isoformat(),
                raw_response={"paper_trading": True},
            )

        # Generate TOTP from secret
        totp_code = ""
        if self.credentials.totp_secret:
            try:
                totp_code = pyotp.TOTP(self.credentials.totp_secret).now()
            except Exception as e:
                return AuthResult(success=False, error=f"TOTP generation failed: {e}")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{ANGEL_BASE_URL}/rest/auth/angelbroking/user/v1/loginByPassword",
                    json={
                        "clientcode": self.credentials.client_id,
                        "password": self.credentials.password,
                        "totp": totp_code,
                    },
                    headers=self._base_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return AuthResult(
                    success=True,
                    access_token=data.get("jwtToken"),
                    refresh_token=data.get("refreshToken"),
                    client_id=self.credentials.client_id,
                    raw_response=data,
                )
        except Exception as e:
            logger.error("angelone.auth_error", error=str(e))
            return AuthResult(success=False, error=str(e))

    async def get_holdings(self) -> List[Holding]:
        if self.paper_trading:
            return self._mock_holdings()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{ANGEL_BASE_URL}/rest/secure/angelbroking/portfolio/v1/getHolding",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                raw = resp.json().get("data", [])
                return [
                    Holding(
                        symbol=h["tradingsymbol"],
                        exchange=h["exchange"],
                        quantity=int(h.get("quantity", 0)),
                        avg_price=Decimal(str(h.get("averageprice", 0))),
                        current_price=Decimal(str(h.get("ltp", 0))),
                        pnl=Decimal(str(h.get("profitandloss", 0))),
                    )
                    for h in raw
                ]
        except Exception as e:
            logger.error("angelone.get_holdings_error", error=str(e))
            return []

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if self.paper_trading:
            return self._simulate_order(request)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{ANGEL_BASE_URL}/rest/secure/angelbroking/order/v1/placeOrder",
                    json={
                        "variety": "NORMAL",
                        "tradingsymbol": request.symbol,
                        "symboltoken": "",   # In real usage, fetch token from symbol lookup
                        "transactiontype": request.side.value,
                        "exchange": request.exchange,
                        "ordertype": "MARKET" if request.order_mode == "MARKET" else "LIMIT",
                        "producttype": "DELIVERY",
                        "duration": "DAY",
                        "price": str(request.price or "0"),
                        "squareoff": "0",
                        "stoploss": "0",
                        "quantity": str(request.quantity),
                        "ordertag": request.tag or "kalpi",
                    },
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return PlaceOrderResult(
                    success=True,
                    broker_order_id=data.get("orderid"),
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
                    f"{ANGEL_BASE_URL}/rest/secure/angelbroking/order/v1/details/{broker_order_id}",
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
                    status=status_map.get(data.get("orderstatus", "").lower(), OrderStatus.PENDING),
                    filled_quantity=int(data.get("filledshares", 0)),
                    avg_fill_price=Decimal(str(data.get("averageprice", 0))) or None,
                    raw_response=data,
                )
        except Exception as e:
            return PlaceOrderResult(success=False, status=OrderStatus.FAILED, error=str(e))

    async def cancel_order(self, broker_order_id: str) -> bool:
        if self.paper_trading:
            return True
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{ANGEL_BASE_URL}/rest/secure/angelbroking/order/v1/cancelOrder",
                    json={"variety": "NORMAL", "orderid": broker_order_id},
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                return resp.json().get("status", False)
        except Exception:
            return False

    async def get_funds(self) -> FundsData:
        """Fetch RMS limits from AngelOne SmartAPI (GET /rms/rlimit/getRMSLimits)."""
        if self.paper_trading:
            return self._mock_funds()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{ANGEL_BASE_URL}/rest/secure/angelbroking/user/v1/getRMS",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                net = Decimal(str(data.get("net", 0)))
                seg = FundsSegment(
                    enabled=True,
                    net=net,
                    cash=Decimal(str(data.get("availablecash", 0))),
                    opening_balance=Decimal(str(data.get("availablecash", 0))),
                    live_balance=net,
                    collateral=Decimal(str(data.get("collateral", 0))),
                    debits=Decimal(str(data.get("utiliseddebits", 0))),
                    span=Decimal(str(data.get("utilisedspan", 0))),
                    exposure=Decimal(str(data.get("utilisedexposure", 0))),
                )
                return FundsData(success=True, equity=seg, raw_response=data)
        except Exception as e:
            return FundsData(success=False, error=str(e))

    def _base_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self.credentials.api_key,
        }

    def _auth_headers(self) -> dict:
        headers = self._base_headers()
        headers["Authorization"] = f"Bearer {self.credentials.access_token}"
        return headers

    def _mock_holdings(self) -> List[Holding]:
        return [
            Holding("BAJFINANCE", "NSE", 3, Decimal("7000"), Decimal("7200"), Decimal("600")),
            Holding("HDFCBANK", "NSE", 12, Decimal("1600"), Decimal("1650"), Decimal("600")),
            Holding("ICICIBANK", "NSE", 20, Decimal("950"), Decimal("980"), Decimal("600")),
        ]


