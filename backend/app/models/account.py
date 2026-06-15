from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Account(Base):
    """A Binance API credential profile owned by a user.

    The secret is stored Fernet-encrypted; the API key is stored as-is (it is
    not usable without the secret) and only ever returned masked.
    """
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    api_key: Mapped[str] = mapped_column(String(255))
    api_secret_encrypted: Mapped[str] = mapped_column(Text)
    testnet: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user = relationship("User", back_populates="accounts")
    bots = relationship("Bot", back_populates="account", cascade="all, delete-orphan")
