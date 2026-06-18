from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["entry", "dca", "rebalance", "take_profit"]
Side = Literal["BUY", "SELL"]


@dataclass
class MarketState:
    """Snapshot the engine plans against. Quote amounts are in USDT."""
    balance: float            # account wallet balance (pre-leverage)
    mark_price: float         # current mark price
    position_size: float = 0.0     # base asset held (0 = flat)
    avg_entry_price: float = 0.0    # average entry / break-even ("point zero")
    liquidation_price: float = 0.0  # exchange-reported liquidation (0 = unknown)
    min_order_notional: float = 0.0  # exchange min notional per order (0 = unknown)

    @property
    def position_notional(self) -> float:
        return self.position_size * self.avg_entry_price


@dataclass
class DesiredOrder:
    role: Role
    side: Side
    price: float
    quantity: float
    reduce_only: bool
    client_order_id: str


@dataclass
class StrategyPlan:
    orders: list[DesiredOrder] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, order: DesiredOrder) -> None:
        self.orders.append(order)

    def note(self, msg: str) -> None:
        self.notes.append(msg)
