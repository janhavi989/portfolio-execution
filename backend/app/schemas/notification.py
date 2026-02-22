"""Pydantic schemas for notifications."""
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class OrderSummary(BaseModel):
    symbol: str
    order_type: str
    instruction_type: str
    quantity: int
    status: str
    avg_fill_price: Optional[float] = None
    error_message: Optional[str] = None


class NotificationPayload(BaseModel):
    event: str = "EXECUTION_COMPLETE"
    batch_id: str
    user_id: str
    broker: str
    execution_type: str
    batch_status: str
    total_orders: int
    filled_orders: int
    failed_orders: int
    partial_orders: int
    orders: List[OrderSummary]
    timestamp: str
    message: str



