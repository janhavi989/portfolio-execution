"""
Execution API endpoints.
  POST /execution/execute          → trigger portfolio execution
  GET  /execution/batches          → list execution history
  GET  /execution/batches/{id}     → get batch details + orders
  GET  /execution/orders           → list all orders
  POST /execution/validate         → dry-run: compute delta without executing
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.execution import ExecutionBatch, Order
from app.schemas.portfolio import ExecutionRequest, ExecutionBatchOut, DeltaOrder
from app.services.auth_service import get_current_user
from app.services.broker_service import BrokerService
from app.services.notification_service import NotificationService
from app.services.websocket_manager import ws_manager
from app.core.execution_engine import ExecutionEngine
from app.core.delta_calculator import DeltaCalculator
from app.adapters import get_adapter
from app.config import settings

router = APIRouter(prefix="/execution", tags=["Execution"])


@router.post("/execute", response_model=ExecutionBatchOut)
async def execute_portfolio(
    payload: ExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    🚀 THE CORE ENDPOINT — Execute a portfolio in one click.

    Flow:
      1. Load broker credentials from active session
      2. Fetch current holdings
      3. Compute delta (or use explicit instructions)
      4. Execute all orders with retry + rate limiting
      5. Send notifications (WebSocket + Webhook + Console)
      6. Return execution batch with full order details
    """
    # Load broker credentials
    svc = BrokerService(db)
    credentials = await svc.get_credentials(current_user.id, payload.broker)
    if not credentials:
        raise HTTPException(
            status_code=400,
            detail=f"No active broker session for '{payload.broker}'. "
                   f"Please connect your broker first via POST /api/v1/broker/connect",
        )

    # Set up notification service with WebSocket progress callback
    notification_svc = NotificationService(db)

    async def on_progress(delta, result, current, total):
        await notification_svc.send_order_progress(
            str(current_user.id), delta, result, current, total
        )

    # Run the execution engine
    engine = ExecutionEngine(
        db=db,
        notification_service=notification_svc,
    )

    batch = await engine.execute(
        user_id=current_user.id,
        broker=payload.broker,
        credentials=credentials,
        portfolio=payload.portfolio,
        on_progress=on_progress,
    )

    # Load orders for response
    result = await db.execute(
        select(ExecutionBatch)
        .options(selectinload(ExecutionBatch.orders))
        .where(ExecutionBatch.id == batch.id)
    )
    batch_with_orders = result.scalar_one()
    return batch_with_orders


@router.post("/validate", response_model=List[dict])
async def validate_portfolio(
    payload: ExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Dry-run: compute the delta orders without actually executing.
    Use this to preview what trades will be placed before committing.
    """
    svc = BrokerService(db)
    credentials = await svc.get_credentials(current_user.id, payload.broker)
    if not credentials:
        raise HTTPException(status_code=400, detail=f"No active session for broker '{payload.broker}'")

    adapter = get_adapter(payload.broker, credentials, paper_trading=settings.PAPER_TRADING)
    current_holdings = await adapter.get_holdings()

    calculator = DeltaCalculator()
    has_explicit = any(h.instruction is not None for h in payload.portfolio.holdings)

    if has_explicit or payload.portfolio.execution_type == "REBALANCE":
        delta_orders = calculator.apply_explicit_instructions(payload.portfolio.holdings)
    else:
        delta_orders = calculator.compute(current_holdings, payload.portfolio.holdings)

    return [
        {
            "symbol": d.symbol,
            "exchange": d.exchange,
            "order_type": d.order_type,
            "instruction_type": d.instruction_type.value,
            "quantity": d.quantity,
            "current_qty": d.current_qty,
            "target_qty": d.target_qty,
        }
        for d in delta_orders
    ]


@router.get("/batches", response_model=List[ExecutionBatchOut])
async def list_batches(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List execution history for the current user."""
    result = await db.execute(
        select(ExecutionBatch)
        .options(selectinload(ExecutionBatch.orders))
        .where(ExecutionBatch.user_id == current_user.id)
        .order_by(desc(ExecutionBatch.created_at))
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.get("/batches/{batch_id}", response_model=ExecutionBatchOut)
async def get_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get details of a specific execution batch including all orders."""
    result = await db.execute(
        select(ExecutionBatch)
        .options(selectinload(ExecutionBatch.orders))
        .where(
            ExecutionBatch.id == batch_id,
            ExecutionBatch.user_id == current_user.id,
        )
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Execution batch not found")
    return batch


@router.get("/orders", response_model=List[dict])
async def list_orders(
    batch_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List orders for the current user, optionally filtered by batch or status."""
    query = select(Order).where(Order.user_id == current_user.id)
    if batch_id:
        query = query.where(Order.batch_id == batch_id)
    if status:
        query = query.where(Order.order_status == status.upper())
    query = query.order_by(desc(Order.created_at)).limit(limit)

    result = await db.execute(query)
    orders = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "batch_id": str(o.batch_id),
            "symbol": o.symbol,
            "exchange": o.exchange,
            "order_type": o.order_type,
            "instruction_type": o.instruction_type,
            "quantity": o.quantity,
            "order_status": o.order_status,
            "filled_quantity": o.filled_quantity,
            "avg_fill_price": float(o.avg_fill_price) if o.avg_fill_price else None,
            "broker_order_id": o.broker_order_id,
            "error_message": o.error_message,
            "placed_at": o.placed_at.isoformat() if o.placed_at else None,
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
        }
        for o in orders
    ]


