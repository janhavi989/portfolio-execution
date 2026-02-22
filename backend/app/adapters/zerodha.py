"""
Zerodha Broker Adapter — Kite Connect API
─────────────────────────────────────────
Zerodha uses a 2-step OAuth flow:
  1. User visits login URL → redirected back with ?request_token=...
  2. We exchange request_token + api_secret → access_token (session)

Real SDK: kiteconnect (pip install kiteconnect)
Docs: https://kite.trade/docs/connect/v3/

In paper trading mode, all API calls are simulated.
"""
import httpx
import hashlib
import structlog
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, timedelta

from app.adapters.base import (
    BrokerAdapter, BrokerCredentials, AuthResult,
    Holding, PlaceOrderRequest, PlaceOrderResult, OrderStatus,
    FundsData, FundsSegment,
)

logger = structlog.get_logger()

KITE_BASE_URL = "https://api.kite.trade"
KITE_LOGIN_URL = "https://kite.zerodha.com/connect/login"


class ZerodhaAdapter(BrokerAdapter):
    """
    Adapter for Zerodha Kite Connect API.

    Authentication flow:
    ┌─────────────────────────────────────────────────────────────┐
    │ 1. GET  /login_url()  → redirect user to Kite login page    │
    │ 2. User logs in → Kite redirects to callback with           │
    │    ?request_token=<token>                                   │
    │ 3. POST /session/token with api_key + request_token +       │
    │    checksum(api_key+request_token+api_secret) → access_token│
    └─────────────────────────────────────────────────────────────┘
    """

    broker_name = "zerodha"

    def get_login_url(self) -> str:
        return f"{KITE_LOGIN_URL}?api_key={self.credentials.api_key}&v=3"

    async def authenticate(self) -> AuthResult:
        if self.paper_trading:
            logger.info("zerodha.authenticate", mode="paper_trading")
            return AuthResult(
                success=True,
                access_token="PAPER_ZERODHA_TOKEN",
                client_id="ZD0001",
                expires_at=(datetime.utcnow() + timedelta(hours=8)).isoformat(),
                raw_response={"paper_trading": True},
            )

        if not self.credentials.request_token:
            return AuthResult(success=False, error="request_token is required for Zerodha auth")

        # Compute checksum: SHA256(api_key + request_token + api_secret)
        checksum_input = (
            self.credentials.api_key
            + self.credentials.request_token
            + (self.credentials.api_secret or "")
        )
        checksum = hashlib.sha256(checksum_input.encode()).hexdigest()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{KITE_BASE_URL}/session/token",
                    data={
                        "api_key": self.credentials.api_key,
                        "request_token": self.credentials.request_token,
                        "checksum": checksum,
                    },
                    headers={"X-Kite-Version": "3"},
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return AuthResult(
                    success=True,
                    access_token=data.get("access_token"),
                    client_id=data.get("user_id"),
                    expires_at=data.get("login_time"),
                    raw_response=data,
                )
        except httpx.HTTPStatusError as e:
            logger.error("zerodha.auth_failed", status=e.response.status_code, detail=e.response.text)
            return AuthResult(success=False, error=str(e))
        except Exception as e:
            logger.error("zerodha.auth_error", error=str(e))
            return AuthResult(success=False, error=str(e))

    async def get_holdings(self) -> List[Holding]:
        if self.paper_trading:
            return self._mock_holdings()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{KITE_BASE_URL}/portfolio/holdings",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                raw = resp.json().get("data", [])
                return [
                    Holding(
                        symbol=h["tradingsymbol"],
                        exchange=h["exchange"],
                        quantity=h["quantity"],
                        avg_price=Decimal(str(h.get("average_price", 0))),
                        current_price=Decimal(str(h.get("last_price", 0))),
                        pnl=Decimal(str(h.get("pnl", 0))),
                    )
                    for h in raw
                ]
        except Exception as e:
            logger.error("zerodha.get_holdings_error", error=str(e))
            return []

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if self.paper_trading:
            return self._simulate_order(request)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{KITE_BASE_URL}/orders/regular",
                    data={
                        "tradingsymbol": request.symbol,
                        "exchange": request.exchange,
                        "transaction_type": request.side.value,
                        "order_type": "MARKET" if request.order_mode == "MARKET" else "LIMIT",
                        "quantity": request.quantity,
                        "product": request.product,
                        "price": str(request.price) if request.price else "0",
                        "tag": request.tag or "kalpi",
                    },
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return PlaceOrderResult(
                    success=True,
                    broker_order_id=str(data.get("order_id")),
                    status=OrderStatus.PLACED,
                    raw_response=data,
                )
        except httpx.HTTPStatusError as e:
            err = e.response.json().get("message", str(e))
            return PlaceOrderResult(success=False, status=OrderStatus.REJECTED, error=err, raw_response=e.response.json())
        except Exception as e:
            return PlaceOrderResult(success=False, status=OrderStatus.FAILED, error=str(e))

    async def get_order_status(self, broker_order_id: str) -> PlaceOrderResult:
        if self.paper_trading:
            return PlaceOrderResult(
                success=True, broker_order_id=broker_order_id,
                status=OrderStatus.FILLED, filled_quantity=1,
            )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{KITE_BASE_URL}/orders/{broker_order_id}",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [{}])[-1]  # latest status
                status_map = {
                    "COMPLETE": OrderStatus.FILLED,
                    "REJECTED": OrderStatus.REJECTED,
                    "CANCELLED": OrderStatus.CANCELLED,
                    "OPEN": OrderStatus.PLACED,
                }
                return PlaceOrderResult(
                    success=True,
                    broker_order_id=broker_order_id,
                    status=status_map.get(data.get("status", ""), OrderStatus.PENDING),
                    filled_quantity=data.get("filled_quantity", 0),
                    avg_fill_price=Decimal(str(data.get("average_price", 0))) or None,
                    raw_response=data,
                )
        except Exception as e:
            return PlaceOrderResult(success=False, status=OrderStatus.FAILED, error=str(e))

    async def get_funds(self) -> FundsData:
        """
        Fetch margin/funds from Zerodha via GET /user/margins.
        Returns equity + commodity segment breakdown.
        This is the definitive proof that the broker token is valid and live.
        """
        if self.paper_trading:
            logger.info("zerodha.get_funds", mode="paper_trading")
            return self._mock_funds()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{KITE_BASE_URL}/user/margins",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})

                def _parse_segment(seg: dict) -> FundsSegment:
                    avail = seg.get("available", {})
                    used = seg.get("utilised", {})
                    return FundsSegment(
                        enabled=seg.get("enabled", False),
                        net=Decimal(str(seg.get("net", 0))),
                        cash=Decimal(str(avail.get("cash", 0))),
                        opening_balance=Decimal(str(avail.get("opening_balance", 0))),
                        live_balance=Decimal(str(avail.get("live_balance", 0))),
                        collateral=Decimal(str(avail.get("collateral", 0))),
                        debits=Decimal(str(used.get("debits", 0))),
                        span=Decimal(str(used.get("span", 0))),
                        exposure=Decimal(str(used.get("exposure", 0))),
                    )

                return FundsData(
                    success=True,
                    equity=_parse_segment(data.get("equity", {})),
                    commodity=_parse_segment(data.get("commodity", {})),
                    raw_response=data,
                )
        except httpx.HTTPStatusError as e:
            logger.error("zerodha.get_funds_failed", status=e.response.status_code, detail=e.response.text)
            return FundsData(success=False, error=f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            logger.error("zerodha.get_funds_error", error=str(e))
            return FundsData(success=False, error=str(e))

    async def cancel_order(self, broker_order_id: str) -> bool:
        if self.paper_trading:
            return True
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"{KITE_BASE_URL}/orders/regular/{broker_order_id}",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    def _auth_headers(self) -> dict:
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.credentials.api_key}:{self.credentials.access_token}",
        }

    def _mock_holdings(self) -> List[Holding]:
        """Return demo holdings for paper trading."""
        return [
            Holding("RELIANCE", "NSE", 10, Decimal("2400"), Decimal("2450"), Decimal("500")),
            Holding("TCS", "NSE", 5, Decimal("3500"), Decimal("3600"), Decimal("500")),
            Holding("INFY", "NSE", 20, Decimal("1500"), Decimal("1520"), Decimal("400")),
        ]


