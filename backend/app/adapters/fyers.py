"""
Fyers Broker Adapter — Fyers API v3
────────────────────────────────────
Fyers uses OAuth2 with PKCE for authentication.
  1. Generate auth_code via login URL
  2. Exchange auth_code for access_token

Real SDK: fyers-apiv3 (pip install fyers-apiv3)
Docs: https://myapi.fyers.in/docs/

In paper trading mode, all API calls are simulated.
"""
import httpx
import hashlib
import base64
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

FYERS_BASE_URL = "https://api-t1.fyers.in/api/v3"
FYERS_AUTH_URL = "https://api-t2.fyers.in/api/v3/generate-authcode"


class FyersAdapter(BrokerAdapter):
    """
    Adapter for Fyers API v3.

    Authentication flow:
    ┌─────────────────────────────────────────────────────────────┐
    │ 1. Build login URL with app_id (api_key) + redirect_uri     │
    │ 2. User logs in → redirected with ?auth_code=<code>         │
    │ 3. POST /validate-authcode with                             │
    │    grant_type=authorization_code + auth_code → access_token │
    └─────────────────────────────────────────────────────────────┘
    """

    broker_name = "fyers"

    def get_login_url(self) -> str:
        app_id = self.credentials.api_key
        redirect_uri = "https://127.0.0.1/"
        state = "kalpi_state"
        return (
            f"{FYERS_AUTH_URL}?client_id={app_id}&redirect_uri={redirect_uri}"
            f"&response_type=code&state={state}"
        )

    async def authenticate(self) -> AuthResult:
        if self.paper_trading:
            logger.info("fyers.authenticate", mode="paper_trading")
            return AuthResult(
                success=True,
                access_token="PAPER_FYERS_TOKEN",
                client_id="FY0001",
                expires_at=(datetime.utcnow() + timedelta(hours=24)).isoformat(),
                raw_response={"paper_trading": True},
            )

        auth_code = self.credentials.request_token  # reuse request_token field for auth_code
        if not auth_code:
            return AuthResult(success=False, error="auth_code (request_token) is required for Fyers")

        # Fyers uses SHA256(api_key:api_secret) as app_hash
        app_hash = hashlib.sha256(
            f"{self.credentials.api_key}:{self.credentials.api_secret}".encode()
        ).hexdigest()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{FYERS_BASE_URL}/validate-authcode",
                    json={
                        "grant_type": "authorization_code",
                        "appIdHash": app_hash,
                        "code": auth_code,
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return AuthResult(
                    success=True,
                    access_token=data.get("access_token"),
                    client_id=data.get("fy_id"),
                    raw_response=data,
                )
        except Exception as e:
            logger.error("fyers.auth_error", error=str(e))
            return AuthResult(success=False, error=str(e))

    async def get_holdings(self) -> List[Holding]:
        if self.paper_trading:
            return self._mock_holdings()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{FYERS_BASE_URL}/holdings",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                raw = resp.json().get("holdings", [])
                return [
                    Holding(
                        symbol=h["symbol"].split(":")[1] if ":" in h["symbol"] else h["symbol"],
                        exchange=h["symbol"].split(":")[0] if ":" in h["symbol"] else "NSE",
                        quantity=h["quantity"],
                        avg_price=Decimal(str(h.get("costPrice", 0))),
                        current_price=Decimal(str(h.get("ltp", 0))),
                        pnl=Decimal(str(h.get("pl", 0))),
                    )
                    for h in raw
                ]
        except Exception as e:
            logger.error("fyers.get_holdings_error", error=str(e))
            return []

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if self.paper_trading:
            return self._simulate_order(request)

        try:
            # Fyers symbol format: "NSE:RELIANCE-EQ"
            fyers_symbol = f"{request.exchange}:{request.symbol}-EQ"
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{FYERS_BASE_URL}/orders/sync",
                    json={
                        "symbol": fyers_symbol,
                        "qty": request.quantity,
                        "type": 2 if request.order_mode == "MARKET" else 1,  # 2=MARKET, 1=LIMIT
                        "side": 1 if request.side.value == "BUY" else -1,
                        "productType": "CNC",
                        "limitPrice": float(request.price) if request.price else 0,
                        "stopPrice": 0,
                        "validity": "DAY",
                        "disclosedQty": 0,
                        "offlineOrder": False,
                    },
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return PlaceOrderResult(
                    success=True,
                    broker_order_id=data.get("id"),
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
                    f"{FYERS_BASE_URL}/orders/sync?id={broker_order_id}",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("orderBook", [{}])[0]
                status_map = {2: OrderStatus.FILLED, 5: OrderStatus.REJECTED, 6: OrderStatus.CANCELLED}
                return PlaceOrderResult(
                    success=True,
                    broker_order_id=broker_order_id,
                    status=status_map.get(data.get("status", 0), OrderStatus.PLACED),
                    filled_quantity=data.get("filledQty", 0),
                    avg_fill_price=Decimal(str(data.get("tradedPrice", 0))) or None,
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
                    f"{FYERS_BASE_URL}/orders/sync",
                    json={"id": broker_order_id},
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                return resp.json().get("s") == "ok"
        except Exception:
            return False

    async def get_funds(self) -> FundsData:
        """Fetch funds from Fyers API v3 (GET /funds)."""
        if self.paper_trading:
            return self._mock_funds()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{FYERS_BASE_URL}/funds",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("fund_limit", [])
                # Fyers returns a list of {title, equityAmount, commodityAmount}
                cash = next((d.get("equityAmount", 0) for d in data if d.get("title") == "Total Balance"), 0)
                seg = FundsSegment(
                    enabled=True,
                    net=Decimal(str(cash)),
                    cash=Decimal(str(cash)),
                    opening_balance=Decimal(str(cash)),
                    live_balance=Decimal(str(cash)),
                    collateral=Decimal("0"),
                    debits=Decimal("0"),
                    span=Decimal("0"),
                    exposure=Decimal("0"),
                )
                return FundsData(success=True, equity=seg, raw_response={"fund_limit": data})
        except Exception as e:
            return FundsData(success=False, error=str(e))

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"{self.credentials.api_key}:{self.credentials.access_token}",
            "Content-Type": "application/json",
        }

    def _mock_holdings(self) -> List[Holding]:
        return [
            Holding("HDFC", "NSE", 8, Decimal("1600"), Decimal("1650"), Decimal("400")),
            Holding("WIPRO", "NSE", 15, Decimal("450"), Decimal("460"), Decimal("150")),
        ]


