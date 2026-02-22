"""
Abstract Broker Adapter — the interface every broker must implement.

Design Pattern: Adapter Pattern
───────────────────────────────
Each broker has a different API (Zerodha Kite, Fyers API v3, AngelOne SmartAPI,
Upstox v2, Groww Pro). Rather than scattering broker-specific logic throughout
the codebase, we define ONE standard interface (BrokerAdapter) here.

Adding a 6th broker = create one new file that inherits BrokerAdapter and
implement the ~5 abstract methods. Zero changes needed elsewhere.

The ExecutionEngine only ever calls methods on BrokerAdapter — it is completely
broker-agnostic.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
from decimal import Decimal
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class BrokerCredentials:
    """Normalized credentials passed to any adapter."""
    api_key: str
    api_secret: Optional[str] = None
    client_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    request_token: Optional[str] = None  # Zerodha OAuth
    totp_secret: Optional[str] = None    # AngelOne TOTP
    password: Optional[str] = None       # Some brokers need login password
    extra: Optional[dict] = None         # Broker-specific extras


@dataclass
class AuthResult:
    """Standardized result from authenticate()."""
    success: bool
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    expires_at: Optional[str] = None     # ISO datetime string
    raw_response: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class Holding:
    """A single stock position held in the broker account."""
    symbol: str
    exchange: str
    quantity: int
    avg_price: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")


@dataclass
class PlaceOrderRequest:
    """Standardized order placement request."""
    symbol: str
    exchange: str          # NSE / BSE
    side: OrderSide
    quantity: int
    order_mode: str = "MARKET"   # MARKET or LIMIT
    price: Optional[Decimal] = None
    product: str = "CNC"         # CNC (delivery) or MIS (intraday)
    tag: Optional[str] = None    # Arbitrary tag for tracking


@dataclass
class PlaceOrderResult:
    """Standardized result from place_order()."""
    success: bool
    broker_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    avg_fill_price: Optional[Decimal] = None
    raw_response: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class FundsSegment:
    """Funds/margin info for a single segment (equity or commodity)."""
    enabled: bool
    net: Decimal
    cash: Decimal
    opening_balance: Decimal
    live_balance: Decimal
    collateral: Decimal
    debits: Decimal
    span: Decimal
    exposure: Decimal


@dataclass
class FundsData:
    """Standardized funds/margin data returned by get_funds()."""
    success: bool
    equity: Optional[FundsSegment] = None
    commodity: Optional[FundsSegment] = None
    raw_response: Optional[dict] = None
    error: Optional[str] = None


class BrokerAdapter(ABC):
    """
    Abstract base class for all broker adapters.

    Every concrete adapter (ZerodhaAdapter, FyersAdapter, etc.) must
    implement these methods. The rest of the system only interacts with
    this interface — never with broker-specific code directly.
    """

    broker_name: str = "unknown"

    def __init__(self, credentials: BrokerCredentials, paper_trading: bool = True):
        self.credentials = credentials
        self.paper_trading = paper_trading

    # ──────────────────────────────────────────────────────────────────────
    # ABSTRACT METHODS — must be implemented by each broker adapter
    # ──────────────────────────────────────────────────────────────────────

    @abstractmethod
    async def authenticate(self) -> AuthResult:
        """
        Authenticate with the broker using the provided credentials.
        Returns an AuthResult with the session access_token.
        """
        ...

    @abstractmethod
    async def get_holdings(self) -> List[Holding]:
        """
        Fetch current stock holdings (long-term delivery positions).
        Returns a list of Holding objects.
        """
        ...

    @abstractmethod
    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        """
        Place a single order (BUY or SELL) with the broker.
        Returns a PlaceOrderResult with broker_order_id and status.
        """
        ...

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> PlaceOrderResult:
        """
        Poll the status of a previously placed order.
        Used for confirmation after placement.
        """
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """
        Cancel a pending order. Returns True if successfully cancelled.
        """
        ...

    @abstractmethod
    async def get_funds(self) -> "FundsData":
        """
        Fetch available margin/funds from the broker account.
        Returns a FundsData object with equity and commodity segments.
        Used to validate that the broker connection is live and working.
        """
        ...

    # ──────────────────────────────────────────────────────────────────────
    # OPTIONAL HOOK — subclasses can override for broker-specific login URL
    # ──────────────────────────────────────────────────────────────────────

    def get_login_url(self) -> Optional[str]:
        """Return the OAuth login URL for brokers that use web-based auth."""
        return None

    # ──────────────────────────────────────────────────────────────────────
    # SHARED UTILITY — paper trading simulation
    # ──────────────────────────────────────────────────────────────────────

    def _mock_funds(self) -> "FundsData":
        """Return simulated fund data for paper trading mode."""
        seg = FundsSegment(
            enabled=True,
            net=Decimal("100000.00"),
            cash=Decimal("100000.00"),
            opening_balance=Decimal("100000.00"),
            live_balance=Decimal("100000.00"),
            collateral=Decimal("0"),
            debits=Decimal("0"),
            span=Decimal("0"),
            exposure=Decimal("0"),
        )
        return FundsData(
            success=True,
            equity=seg,
            commodity=FundsSegment(
                enabled=True,
                net=Decimal("50000.00"),
                cash=Decimal("50000.00"),
                opening_balance=Decimal("50000.00"),
                live_balance=Decimal("50000.00"),
                collateral=Decimal("0"),
                debits=Decimal("0"),
                span=Decimal("0"),
                exposure=Decimal("0"),
            ),
            raw_response={"paper_trading": True},
        )

    def _simulate_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        """
        Simulate order execution in paper trading mode.
        Returns a realistic mock result without hitting the real broker API.
        """
        import uuid
        import random
        # Simulate ~95% fill rate, ~5% rejection
        success = random.random() > 0.05
        if success:
            simulated_price = Decimal(str(round(random.uniform(100, 5000), 2)))
            return PlaceOrderResult(
                success=True,
                broker_order_id=f"PAPER-{uuid.uuid4().hex[:12].upper()}",
                status=OrderStatus.FILLED,
                filled_quantity=request.quantity,
                avg_fill_price=simulated_price,
                raw_response={"mode": "paper_trading", "simulated": True},
            )
        else:
            return PlaceOrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                error="Simulated rejection: Insufficient funds or circuit breaker",
                raw_response={"mode": "paper_trading", "simulated": True},
            )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} broker={self.broker_name} paper={self.paper_trading}>"


