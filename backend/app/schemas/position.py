from pydantic import BaseModel
from typing import Literal


class Position(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT"]
    size: float
    entry_price: float
    mark_price: float
    leverage: int
    unrealized_pnl: float
    pnl_pct: float
    liquidation_price: float
    margin: float
