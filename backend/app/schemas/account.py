from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AccountSummary(BaseModel):
    """Live account-level balance snapshot from Binance."""
    total_balance: float
    available_balance: float
    unrealized_pnl: float
    margin_ratio: float


class AccountCreate(BaseModel):
    name: str
    api_key: str
    api_secret: str
    testnet: bool = True


class AccountOut(BaseModel):
    id: int
    name: str
    api_key_masked: str
    testnet: bool
    created_at: datetime


class ConnectionTest(BaseModel):
    ok: bool
    can_trade: Optional[bool] = None
    total_wallet_balance: Optional[float] = None
    error: Optional[str] = None
