"""Pydantic schemas for portfolio and execution."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


class InstructionType(str, Enum):
    BUY_NEW = "BUY_NEW"           # First-time purchase of a new stock
    SELL_EXIT = "SELL_EXIT"        # Complete exit from a position
    REBALANCE_BUY = "REBALANCE_BUY"   # Increase existing position
    REBALANCE_SELL = "REBALANCE_SELL"  # Decrease existing position


class TargetHolding(BaseModel):
    """A single stock in the target portfolio."""
    symbol: str = Field(..., description="NSE/BSE stock symbol e.g. RELIANCE")
    exchange: str = Field(default="NSE", description="Exchange: NSE or BSE")
    quantity: int = Field(..., gt=0, description="Target quantity to hold")
    # Optional: explicit instruction for rebalancing
    instruction: Optional[InstructionType] = None

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        return v.upper().strip()


class PortfolioUpload(BaseModel):
    """Full target portfolio upload payload."""
    holdings: List[TargetHolding] = Field(..., min_length=1, max_length=100)
    execution_type: str = Field(
        default="AUTO",
        description="AUTO (engine decides), FIRST_TIME, or REBALANCE"
    )
    notes: Optional[str] = None


class CurrentHolding(BaseModel):
    """A stock currently held in the broker account."""
    symbol: str
    exchange: str = "NSE"
    quantity: int
    avg_price: Optional[Decimal] = None
    current_price: Optional[Decimal] = None


class DeltaOrder(BaseModel):
    """A computed order derived from target vs current delta."""
    symbol: str
    exchange: str
    order_type: str          # BUY or SELL
    instruction_type: InstructionType
    quantity: int
    current_qty: int = 0
    target_qty: int


class ExecutionRequest(BaseModel):
    """Request body to trigger execution."""
    broker: str
    portfolio: PortfolioUpload


class OrderOut(BaseModel):
    id: str
    symbol: str
    exchange: str
    order_type: str
    instruction_type: str
    quantity: int
    order_status: str
    filled_quantity: int
    avg_fill_price: Optional[Decimal]
    broker_order_id: Optional[str]
    error_message: Optional[str]
    placed_at: Optional[datetime]
    filled_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ExecutionBatchOut(BaseModel):
    id: str
    broker: str
    execution_type: str
    status: str
    target_portfolio: dict
    current_holdings: list
    delta_orders: list
    summary: dict
    orders: List[OrderOut] = []
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


