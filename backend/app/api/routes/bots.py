from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import Account, Bot, User
from app.schemas.bot import BotCreate, BotOut, BotPnl, BotRuntime, BotUpdate
from app.schemas.order import Order
from app.schemas.position import Position
from app.strategy.manager import bot_manager

router = APIRouter()

_CONFIG_FIELDS = (
    "symbol", "direction", "entry_price", "leverage", "target_position_pct",
    "dca_step_pct", "dca_add_pct", "take_profit_pct", "take_profit_close_pct",
    "tp_width_pct", "max_dca_orders",
)


def _owned_bot(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if bot is None or bot.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
    return bot


def _pnl_from_snapshot(bot: Bot, snap: Optional[dict]) -> BotPnl:
    since = bot.started_at.isoformat() if bot.started_at else None
    if not snap:
        return BotPnl(since=since)
    realized = snap.get("realized", 0.0)
    unreal = snap.get("unrealized", 0.0)
    return BotPnl(
        realized=realized,
        unrealized=unreal,
        total=round(realized + unreal, 2),
        since=since,
    )


def _to_out(bot: Bot, db: Session) -> BotOut:
    account = db.get(Account, bot.account_id)
    snap = bot_manager.snapshot(bot.id)
    return BotOut(
        id=bot.id,
        name=bot.name,
        account_id=bot.account_id,
        account_name=account.name if account else "—",
        enabled=bot.enabled,
        created_at=bot.created_at,
        started_at=bot.started_at,
        runtime=BotRuntime(**bot_manager.status(bot.id)),
        pnl=_pnl_from_snapshot(bot, snap),
        **{f: getattr(bot, f) for f in _CONFIG_FIELDS},
    )


@router.get("", response_model=List[BotOut])
def list_bots(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bots = db.query(Bot).filter(Bot.user_id == user.id).order_by(Bot.id).all()
    return [_to_out(b, db) for b in bots]


@router.post("", response_model=BotOut)
def create_bot(
    body: BotCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = db.get(Account, body.account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account not found")

    clash = (
        db.query(Bot)
        .filter(Bot.account_id == body.account_id, Bot.symbol == body.symbol)
        .first()
    )
    if clash:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"A bot for {body.symbol} already exists on this account",
        )

    bot = Bot(
        user_id=user.id,
        account_id=body.account_id,
        name=body.name.strip() or body.symbol,
        **{f: getattr(body, f) for f in _CONFIG_FIELDS},
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return _to_out(bot, db)


@router.get("/{bot_id}", response_model=BotOut)
def get_bot(bot_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_out(_owned_bot(bot_id, user, db), db)


@router.put("/{bot_id}", response_model=BotOut)
def update_bot(
    bot_id: int,
    body: BotUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _owned_bot(bot_id, user, db)
    bot.name = body.name.strip() or bot.symbol
    for f in _CONFIG_FIELDS:
        setattr(bot, f, getattr(body, f))
    db.commit()
    db.refresh(bot)
    return _to_out(bot, db)


@router.delete("/{bot_id}")
def delete_bot(bot_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _owned_bot(bot_id, user, db)
    bot_manager.remove(bot.id, cancel_orders=True)
    db.delete(bot)
    db.commit()
    return {"deleted": bot_id}


@router.post("/{bot_id}/start", response_model=BotOut)
def start_bot(bot_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _owned_bot(bot_id, user, db)
    bot.enabled = True
    if bot.started_at is None:
        bot.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bot)
    bot_manager.start(bot.id)
    return _to_out(bot, db)


@router.post("/{bot_id}/stop", response_model=BotOut)
def stop_bot(bot_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bot = _owned_bot(bot_id, user, db)
    bot.enabled = False
    db.commit()
    bot_manager.stop(bot.id, cancel_orders=True)
    db.refresh(bot)
    return _to_out(bot, db)


@router.get("/{bot_id}/orders", response_model=List[Order])
def bot_orders(bot_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_bot(bot_id, user, db)
    snap = bot_manager.snapshot(bot_id)
    return snap["open_orders"] if snap else []


@router.get("/{bot_id}/position", response_model=Optional[Position])
def bot_position(bot_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _owned_bot(bot_id, user, db)
    snap = bot_manager.snapshot(bot_id)
    return snap["position"] if snap else None
