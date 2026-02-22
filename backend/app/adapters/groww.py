"""
Groww Broker Adapter — Groww Pro API (REST)
────────────────────────────────────────────
Groww does not have an official public Python SDK (as of 2025).
We integrate directly with their REST API using API key authentication.

Note on SDK choice: Since Groww lacks an official SDK, we use httpx
(async HTTP client) directly. This is the same approach used for all
adapters to maintain consistency and avoid SDK version conflicts.

Docs: https://groww.in/developer (Pro/Partner API)

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

GROWW_BASE_URL = "https://api.groww.in/v1"


class GrowwAdapter(BrokerAdapter):
    """
    Adapter for Groww Pro REST API.

    Authentication flow:
    ┌─────────────────────────────────────────────────────────────┐
    │ Groww Pro uses API Key + Client ID authentication.          │
    │ No OAuth redirect needed — credentials are passed directly. │
    │                                                             │
    │ POST /user/login → { access_token }                         │
    │ All subsequent requests: Authorization: Bearer <token>      │
    └─────────────────────────────────────────────────────────────┘
    """

    broker_name = "groww"

    async def authenticate(self) -> AuthResult:
        if self.paper_trading:
            logger.info("groww.authenticate", mode="paper_trading")
            return AuthResult(
                success=True,
                access_token="PAPER_GROWW_TOKEN",
                client_id=self.credentials.client_id or "GW0001",
                expires_at=(datetime.utcnow() + timedelta(hours=24)).isoformat(),
                raw_response={"paper_trading": True},
            )

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{GROWW_BASE_URL}/user/login",
                    json={
                        "client_id": self.credentials.client_id,
                        "api_key": self.credentials.api_key,
                        "api_secret": self.credentials.api_secret,
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return AuthResult(
                    success=True,
                    access_token=data.get("access_token"),
                    client_id=self.credentials.client_id,
                    raw_response=data,
                )
        except Exception as e:
            logger.error("groww.auth_error", error=str(e))
            return AuthResult(success=False, error=str(e))

    async def get_holdings(self) -> List[Holding]:
        if self.paper_trading:
            return self._mock_holdings()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GROWW_BASE_URL}/portfolio/holdings",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                raw = resp.json().get("holdings", [])
                return [
                    Holding(
                        symbol=h["symbol"],
                        exchange=h.get("exchange", "NSE"),
                        quantity=h["quantity"],
                        avg_price=Decimal(str(h.get("avg_price", 0))),
                        current_price=Decimal(str(h.get("ltp", 0))),
                        pnl=Decimal(str(h.get("pnl", 0))),
                    )
                    for h in raw
                ]
        except Exception as e:
            logger.error("groww.get_holdings_error", error=str(e))
            return []

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if self.paper_trading:
            return self._simulate_order(request)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{GROWW_BASE_URL}/orders",
                    json={
                        "symbol": request.symbol,
                        "exchange": request.exchange,
                        "side": request.side.value,
                        "quantity": request.quantity,
                        "order_type": "MARKET" if request.order_mode == "MARKET" else "LIMIT",
                        "product_type": "CNC",
                        "price": float(request.price) if request.price else None,
                        "tag": request.tag or "kalpi",
                    },
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
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
                    f"{GROWW_BASE_URL}/orders/{broker_order_id}",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
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
                    avg_fill_price=Decimal(str(data.get("avg_price", 0))) or None,
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
                    f"{GROWW_BASE_URL}/orders/{broker_order_id}",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                return resp.json().get("status") == "success"
        except Exception:
            return False

    async def get_funds(self) -> FundsData:
        """Fetch funds from Groww Pro API (GET /user/trading-info)."""
        if self.paper_trading:
            return self._mock_funds()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GROWW_BASE_URL}/user/trading-info",
                    headers=self._auth_headers(),
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                avail = Decimal(str(data.get("availableBalance", 0)))
                used = Decimal(str(data.get("usedBalance", 0)))
                seg = FundsSegment(
                    enabled=True,
                    net=avail,
                    cash=avail,
                    opening_balance=avail + used,
                    live_balance=avail,
                    collateral=Decimal("0"),
                    debits=used,
                    span=Decimal("0"),
                    exposure=Decimal("0"),
                )
                return FundsData(success=True, equity=seg, raw_response=data)
        except Exception as e:
            return FundsData(success=False, error=str(e))

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.access_token}",
            "Content-Type": "application/json",
            "X-API-KEY": self.credentials.api_key,
        }

    def _mock_holdings(self) -> List[Holding]:
        return [
            Holding("MARUTI", "NSE", 2, Decimal("10000"), Decimal("10500"), Decimal("1000")),
            Holding("ASIANPAINT", "NSE", 5, Decimal("3200"), Decimal("3250"), Decimal("250")),
        ]


