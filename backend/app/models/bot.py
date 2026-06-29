from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Bot(Base):
    """A trading-bot session: a strategy config bound to an account, plus
    lifecycle state. The runner reads its config from this row each tick.
    """
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(100))

    # Strategy config
    symbol: Mapped[str] = mapped_column(String(30), default="BTCUSDT")
    direction: Mapped[str] = mapped_column(String(5), default="LONG")  # LONG | SHORT
    entry_price: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = auto
    leverage: Mapped[int] = mapped_column(Integer, default=10)
    target_position_pct: Mapped[float] = mapped_column(Float, default=15.0)
    dca_step_pct: Mapped[float] = mapped_column(Float, default=2.0)
    dca_add_pct: Mapped[float] = mapped_column(Float, default=20.0)
    take_profit_pct: Mapped[float] = mapped_column(Float, default=20.0)
    take_profit_close_pct: Mapped[float] = mapped_column(Float, default=33.0)
    tp_width_pct: Mapped[float] = mapped_column(Float, default=100.0)
    max_dca_orders: Mapped[int] = mapped_column(Integer, default=8)

    # Lifecycle
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="bots")
    account = relationship("Account", back_populates="bots")
