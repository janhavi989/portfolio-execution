"""
Delta Calculator — computes the difference between current holdings and target portfolio.

This is the brain of the rebalancing logic:
  - If a stock is in target but NOT in current → BUY_NEW
  - If a stock is in current but NOT in target → SELL_EXIT
  - If a stock is in BOTH with different quantities:
      - target > current → REBALANCE_BUY (buy the difference)
      - target < current → REBALANCE_SELL (sell the difference)
      - target == current → no action needed
"""
from typing import List
from app.adapters.base import Holding, OrderSide
from app.schemas.portfolio import TargetHolding, DeltaOrder, InstructionType
import structlog

logger = structlog.get_logger()


class DeltaCalculator:
    """
    Computes the minimal set of orders needed to move from
    current holdings to the target portfolio.
    """

    def compute(
        self,
        current_holdings: List[Holding],
        target_holdings: List[TargetHolding],
    ) -> List[DeltaOrder]:
        """
        Main entry point.

        Args:
            current_holdings: What the broker account currently holds.
            target_holdings: What we WANT the account to hold.

        Returns:
            List of DeltaOrder objects — the minimal set of trades needed.
        """
        # Build lookup maps (symbol → quantity)
        current_map: dict[str, Holding] = {h.symbol.upper(): h for h in current_holdings}
        target_map: dict[str, TargetHolding] = {t.symbol.upper(): t for t in target_holdings}

        delta_orders: List[DeltaOrder] = []

        # ── Pass 1: Process all target holdings ───────────────────────────
        for symbol, target in target_map.items():
            current = current_map.get(symbol)
            current_qty = current.quantity if current else 0
            target_qty = target.quantity
            exchange = target.exchange

            if current_qty == 0:
                # Stock not in current portfolio → fresh BUY
                delta_orders.append(DeltaOrder(
                    symbol=symbol,
                    exchange=exchange,
                    order_type=OrderSide.BUY.value,
                    instruction_type=InstructionType.BUY_NEW,
                    quantity=target_qty,
                    current_qty=0,
                    target_qty=target_qty,
                ))
                logger.debug("delta.buy_new", symbol=symbol, qty=target_qty)

            elif target_qty > current_qty:
                # Need to increase position → REBALANCE_BUY
                buy_qty = target_qty - current_qty
                delta_orders.append(DeltaOrder(
                    symbol=symbol,
                    exchange=exchange,
                    order_type=OrderSide.BUY.value,
                    instruction_type=InstructionType.REBALANCE_BUY,
                    quantity=buy_qty,
                    current_qty=current_qty,
                    target_qty=target_qty,
                ))
                logger.debug("delta.rebalance_buy", symbol=symbol, current=current_qty, target=target_qty, delta=buy_qty)

            elif target_qty < current_qty:
                # Need to reduce position → REBALANCE_SELL
                sell_qty = current_qty - target_qty
                delta_orders.append(DeltaOrder(
                    symbol=symbol,
                    exchange=exchange,
                    order_type=OrderSide.SELL.value,
                    instruction_type=InstructionType.REBALANCE_SELL,
                    quantity=sell_qty,
                    current_qty=current_qty,
                    target_qty=target_qty,
                ))
                logger.debug("delta.rebalance_sell", symbol=symbol, current=current_qty, target=target_qty, delta=sell_qty)

            else:
                # target_qty == current_qty → no action
                logger.debug("delta.no_change", symbol=symbol, qty=current_qty)

        # ── Pass 2: Stocks in current but NOT in target → full exit ───────
        for symbol, current in current_map.items():
            if symbol not in target_map:
                delta_orders.append(DeltaOrder(
                    symbol=symbol,
                    exchange=current.exchange,
                    order_type=OrderSide.SELL.value,
                    instruction_type=InstructionType.SELL_EXIT,
                    quantity=current.quantity,
                    current_qty=current.quantity,
                    target_qty=0,
                ))
                logger.debug("delta.sell_exit", symbol=symbol, qty=current.quantity)

        # ── Ordering: SELLs first (free up capital), then BUYs ────────────
        sells = [o for o in delta_orders if o.order_type == OrderSide.SELL.value]
        buys = [o for o in delta_orders if o.order_type == OrderSide.BUY.value]

        ordered = sells + buys

        logger.info(
            "delta.computed",
            total=len(ordered),
            sells=len(sells),
            buys=len(buys),
        )
        return ordered

    def apply_explicit_instructions(
        self,
        instructions: List[TargetHolding],
    ) -> List[DeltaOrder]:
        """
        For REBALANCE mode where explicit instructions are provided in the payload
        (e.g., instruction=SELL_EXIT, REBALANCE_BUY, etc.).
        Bypasses the delta computation and uses instructions as-is.
        """
        delta_orders: List[DeltaOrder] = []
        for item in instructions:
            if item.instruction is None:
                # Default: treat as BUY_NEW if no instruction given
                item.instruction = InstructionType.BUY_NEW

            order_type = (
                OrderSide.SELL.value
                if item.instruction in (InstructionType.SELL_EXIT, InstructionType.REBALANCE_SELL)
                else OrderSide.BUY.value
            )
            delta_orders.append(DeltaOrder(
                symbol=item.symbol,
                exchange=item.exchange,
                order_type=order_type,
                instruction_type=item.instruction,
                quantity=item.quantity,
                current_qty=0,
                target_qty=item.quantity,
            ))

        # SELLs first
        sells = [o for o in delta_orders if o.order_type == OrderSide.SELL.value]
        buys = [o for o in delta_orders if o.order_type == OrderSide.BUY.value]
        return sells + buys



