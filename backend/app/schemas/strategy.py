from typing import Literal

from pydantic import BaseModel


class StrategyConfig(BaseModel):
    symbol: str = "BTCUSDT"
    direction: Literal["LONG", "SHORT"] = "LONG"
    entry_price: float = 0.0  # 0 = auto (one DCA step from mark)
    leverage: int = 10
    target_position_pct: float = 15.0
    dca_step_pct: float = 2.0
    dca_add_pct: float = 20.0
    take_profit_pct: float = 20.0
    take_profit_close_pct: float = 33.0
    tp_width_pct: float = 100.0  # TP reach as % of entry→liquidation distance
    max_dca_orders: int = 8
    enabled: bool = False
