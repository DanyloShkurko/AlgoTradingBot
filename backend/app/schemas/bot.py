from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class BotConfigBase(BaseModel):
    symbol: str = "BTCUSDT"
    direction: Literal["LONG", "SHORT"] = "LONG"
    entry_price: float = Field(default=0.0, ge=0)  # 0 = auto
    leverage: int = Field(default=10, ge=1, le=125)
    target_position_pct: float = Field(default=15.0, gt=0, le=100)
    dca_step_pct: float = Field(default=2.0, gt=0, le=50)
    dca_add_pct: float = Field(default=20.0, gt=0, le=200)
    take_profit_pct: float = Field(default=20.0, gt=0, le=100)
    take_profit_close_pct: float = Field(default=33.0, gt=0, le=100)
    tp_width_pct: float = Field(default=100.0, gt=0, le=500)  # TP reach vs liq distance
    max_dca_orders: int = Field(default=8, ge=1, le=30)


class BotCreate(BotConfigBase):
    name: str
    account_id: int


class BotUpdate(BotConfigBase):
    name: str


class BotRuntime(BaseModel):
    running: bool
    last_tick_at: Optional[str] = None
    last_error: Optional[str] = None
    desired_orders: int = 0
    open_orders: int = 0
    notes: List[str] = []


class BotPnl(BaseModel):
    realized: float = 0.0
    unrealized: float = 0.0
    total: float = 0.0
    since: Optional[str] = None


class BotOut(BotConfigBase):
    id: int
    name: str
    account_id: int
    account_name: str
    enabled: bool
    created_at: datetime
    started_at: Optional[datetime] = None
    runtime: BotRuntime
    pnl: BotPnl
