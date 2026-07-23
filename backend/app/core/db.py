from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so they register on Base.metadata, then create tables.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_additive_migrations()


# Lightweight stopgap until Alembic: create_all() never ADDS columns to an
# existing table, so new strategy params must be backfilled here. Each statement
# is idempotent (ADD COLUMN IF NOT EXISTS), so it's safe to run every startup.
_ADDITIVE_MIGRATIONS = (
    "ALTER TABLE bots ADD COLUMN IF NOT EXISTS tp_width_pct "
    "double precision NOT NULL DEFAULT 100",
    "ALTER TABLE bots ADD COLUMN IF NOT EXISTS scalp_chunks "
    "text NOT NULL DEFAULT '[]'",
)


def _run_additive_migrations() -> None:
    with engine.begin() as conn:
        for stmt in _ADDITIVE_MIGRATIONS:
            conn.execute(text(stmt))
