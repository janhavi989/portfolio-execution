"""SQLAlchemy ORM models for execution batches, orders, notifications — SQLite/PostgreSQL compatible."""
import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer, Numeric, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ExecutionBatch(Base):
    __tablename__ = "execution_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    broker: Mapped[str] = mapped_column(String(50), nullable=False)
    execution_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    target_portfolio: Mapped[dict] = mapped_column(JSON, nullable=False)
    current_holdings: Mapped[list] = mapped_column(JSON, default=list)
    delta_orders: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    user = relationship("User", back_populates="execution_batches")
    orders = relationship("Order", back_populates="batch", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="batch", cascade="all, delete-orphan")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("execution_batches.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    broker: Mapped[str] = mapped_column(String(50), nullable=False)
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(255))
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), default="NSE")
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    instruction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    order_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_fill_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_response: Mapped[dict] = mapped_column(JSON, default=dict)
    placed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="orders")
    batch = relationship("ExecutionBatch", back_populates="orders")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("execution_batches.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="notifications")
    batch = relationship("ExecutionBatch", back_populates="notifications")
