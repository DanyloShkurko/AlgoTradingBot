"""Per-bot strategy runner.

One thread per running bot. Each tick it reloads the bot's config + account
from the DB, pulls a market snapshot from that account's Binance client, asks
the engine for the desired orders, and reconciles. Orders are namespaced per
bot (client id prefix "b{bot_id}-") so multiple bots never touch each other's
orders.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from binance.exceptions import BinanceAPIException

from app.core.db import SessionLocal
from app.models import Account, Bot
from app.schemas.strategy import StrategyConfig
from app.services import binance_client
from app.strategy import engine
from app.strategy.models import DesiredOrder, MarketState

log = logging.getLogger("strategy.bot_runner")

# Heartbeat poll interval. The websocket wakes the loop instantly on fills;
# this is the fallback that keeps state correct if the socket drops.
_TICK_SECONDS = 5


def _anchor_from_cid(cid: str) -> float:
    """Buy price encoded in a scalp order id ("b3-scalp-97_25" -> 97.25)."""
    try:
        return float(cid.split("-scalp-", 1)[1].replace("_", "."))
    except (IndexError, ValueError):
        return 0.0


def config_from_bot(bot: Bot) -> StrategyConfig:
    return StrategyConfig(
        symbol=bot.symbol,
        direction=bot.direction,
        entry_price=bot.entry_price,
        leverage=bot.leverage,
        target_position_pct=bot.target_position_pct,
        dca_step_pct=bot.dca_step_pct,
        dca_add_pct=bot.dca_add_pct,
        take_profit_pct=bot.take_profit_pct,
        take_profit_close_pct=bot.take_profit_close_pct,
        tp_width_pct=bot.tp_width_pct,
        max_dca_orders=bot.max_dca_orders,
        enabled=bot.enabled,
    )


class BotRunner:
    def __init__(self, bot_id: int) -> None:
        self.bot_id = bot_id
        self.prefix = f"b{bot_id}-"
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._wake = threading.Event()  # set by the websocket to tick now
        self._lock = threading.Lock()
        self._last_position: Optional[tuple[float, float]] = None
        self._prepared = False
        self._symbol: Optional[str] = None
        self._started_at = None  # bot.started_at, for realized-PnL window
        self._twm = None  # ThreadedWebsocketManager
        self._ws_init_done = False
        self._realized_at = 0.0  # monotonic time of last realized-PnL fetch
        # Chunks bought beyond target awaiting unload: price_key -> [price, qty].
        # Persisted to bots.scalp_chunks so they survive restarts.
        self._chunks: dict[str, list[float]] = {}
        self._chunks_loaded = False
        self._chunks_dirty = False
        self._ws_fills: list[dict[str, Any]] = []  # fill events from the ws thread
        self._fills_lock = threading.Lock()
        self._scalp_open: set[str] = set()  # scalp cids confirmed resting
        self._scalp_done: dict[str, float] = {}  # ws-accounted fill qty per cid
        # Cache of the last Binance read, served to the API so the frontend
        # never has to hit Binance itself (avoids -1003 rate-limit bans).
        self._snapshot: dict[str, Any] = {
            "balance": 0.0,
            "position": None,
            "open_orders": [],
            "realized": 0.0,
            "unrealized": 0.0,
            "updated_at": None,
        }
        self._status: dict[str, Any] = {
            "running": False,
            "last_tick_at": None,
            "last_error": None,
            "desired_orders": 0,
            "open_orders": 0,
            "notes": [],
        }

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._wake.clear()
            self._last_position = None
            self._prepared = False
            self._ws_init_done = False
            self._thread = threading.Thread(
                target=self._run_loop, name=f"bot-{self.bot_id}", daemon=True
            )
            self._thread.start()
            self._status["running"] = True
            self._status["last_error"] = None

    def stop(self, cancel_orders: bool = True) -> None:
        self._stop.set()
        self._wake.set()  # break the heartbeat wait immediately
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=_TICK_SECONDS + 2)
        self._stop_ws()
        self._status["running"] = False
        if cancel_orders:
            try:
                cancelled = self._cancel_all_bot_orders()
                self._status["notes"] = [f"Stopped; cancelled {cancelled} orders"]
            except Exception as exc:  # noqa: BLE001
                log.warning("bot %s cancel-on-stop failed: %s", self.bot_id, exc)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict[str, Any]:
        return {**self._status, "running": self.is_running()}

    def snapshot(self) -> dict[str, Any]:
        return dict(self._snapshot)

    # -- loop -------------------------------------------------------------

    def _load(self) -> Optional[tuple[Bot, Account]]:
        db = SessionLocal()
        try:
            bot = db.get(Bot, self.bot_id)
            if bot is None:
                return None
            account = db.get(Account, bot.account_id)
            if account is None:
                return None
            db.expunge(bot)
            db.expunge(account)
            return bot, account
        finally:
            db.close()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                loaded = self._load()
                if loaded is None:
                    self._status["last_error"] = "Bot or account missing"
                    break
                bot, account = loaded
                self._started_at = bot.started_at
                if not self._chunks_loaded:
                    self._load_chunks(bot)
                svc = binance_client.get_service_for_account(account)
                config = config_from_bot(bot)

                if not self._prepared:
                    svc.prepare_symbol(config.symbol, config.leverage)
                    self._prepared = True
                if not self._ws_init_done:
                    self._start_ws(svc, config.symbol)
                    self._ws_init_done = True

                self._tick(config, svc)
                self._status["last_error"] = None
            except Exception as exc:  # noqa: BLE001
                log.exception("bot %s tick failed", self.bot_id)
                self._status["last_error"] = str(exc)
            self._status["last_tick_at"] = datetime.now(timezone.utc).isoformat()
            # Wake instantly on a fill (websocket) or fall back to the heartbeat.
            self._wake.wait(_TICK_SECONDS)
            self._wake.clear()

    # -- websocket (low-latency fill reaction) ----------------------------

    def wake(self) -> None:
        self._wake.set()

    def _start_ws(self, svc, symbol: str) -> None:
        self._symbol = symbol
        try:
            twm = svc.make_ws_manager()
            twm.start()
            twm.start_futures_user_socket(callback=self._on_ws)
            self._twm = twm
            log.info("bot %s websocket connected (user-data stream)", self.bot_id)
        except Exception as exc:  # noqa: BLE001 - degrade to polling
            self._twm = None
            log.warning("bot %s websocket unavailable, polling only: %s", self.bot_id, exc)

    def _stop_ws(self) -> None:
        twm, self._twm = self._twm, None
        if twm is not None:
            try:
                twm.stop()
            except Exception:  # noqa: BLE001
                pass

    def _on_ws(self, msg) -> None:
        """Wake the loop when an order fills or the position changes."""
        try:
            if not isinstance(msg, dict):
                return
            event = msg.get("e")
            if event == "ORDER_TRADE_UPDATE":
                o = msg.get("o", {})
                if o.get("s") == self._symbol and o.get("X") in ("FILLED", "PARTIALLY_FILLED"):
                    cid = str(o.get("c", ""))
                    if cid.startswith(self.prefix):
                        with self._fills_lock:
                            self._ws_fills.append({
                                "cid": cid,
                                "side": o.get("S"),
                                "price": float(o.get("L") or o.get("ap") or 0),
                                "qty": float(o.get("l") or 0),
                                "status": o.get("X"),
                            })
                    self.wake()
            elif event == "ACCOUNT_UPDATE":
                if any(p.get("s") == self._symbol for p in msg.get("a", {}).get("P", [])):
                    self.wake()
        except Exception:  # noqa: BLE001
            log.exception("bot %s ws handler error", self.bot_id)

    def _tick(self, config: StrategyConfig, svc) -> None:
        symbol = config.symbol
        account = svc.get_account_summary()
        positions = svc.get_positions(symbol=symbol)
        now_iso = datetime.now(timezone.utc).isoformat()

        opposite = "SHORT" if config.direction == "LONG" else "LONG"
        if any(p.side == opposite for p in positions):
            self._status["notes"] = [
                f"{opposite} position open but bot is {config.direction}; "
                "close it before trading this direction"
            ]
            self._snapshot.update(balance=account.total_balance, position=None,
                                  open_orders=[], unrealized=0.0, updated_at=now_iso)
            return

        pos = next((p for p in positions if p.side == config.direction), None)
        mark = svc.get_mark_price(symbol)
        state = MarketState(
            balance=account.total_balance,
            mark_price=mark,
            position_size=pos.size if pos else 0.0,
            avg_entry_price=pos.entry_price if pos else 0.0,
            liquidation_price=pos.liquidation_price if pos else 0.0,
            min_order_notional=svc.symbol_filters(symbol).min_notional,
        )

        current = (round(state.position_size, 8), round(state.avg_entry_price, 8))
        fill_detected = self._last_position is not None and current != self._last_position
        self._last_position = current

        # Single orders fetch — reused for the snapshot and reconciliation.
        raw_open = svc.get_raw_open_orders(symbol)
        bot_open = [svc._to_order(o) for o in raw_open
                    if str(o.get("clientOrderId", "")).startswith(self.prefix)]

        # Excess-chunk bookkeeping: catch scalp fills the ws may have missed,
        # fold in new fills, drop stale state once the excess is gone.
        target = engine.target_notional(state, config)
        self._sync_scalp_rest(svc, symbol, raw_open)
        self._process_fills(state, config, target)
        if self._chunks and (state.position_size <= 0
                             or state.position_notional <= target):
            self._chunks.clear()
            self._chunks_dirty = True
        state.excess_chunks = [(p, q) for p, q in self._chunks.values()]
        if self._chunks_dirty:
            self._save_chunks()
            self._chunks_dirty = False

        # Realized PnL (trade history) is heavier — refresh only on a fill or
        # at most once a minute.
        monotonic = time.monotonic()
        if fill_detected or (monotonic - self._realized_at) > 60:
            try:
                start_ms = (int(self._started_at.timestamp() * 1000)
                            if self._started_at else None)
                self._snapshot["realized"] = round(
                    svc.get_realized_income(symbol, start_ms), 2)
            except Exception:  # noqa: BLE001
                pass
            self._realized_at = monotonic

        self._snapshot.update(
            balance=account.total_balance,
            position=pos,
            open_orders=bot_open,
            unrealized=round(pos.unrealized_pnl, 2) if pos else 0.0,
            updated_at=now_iso,
        )

        result = engine.plan(state, config)
        self._status["notes"] = result.notes
        self._status["desired_orders"] = len(result.orders)
        self._reconcile(symbol, config, svc, result.orders, fill_detected, raw_open)

    # -- excess-chunk bookkeeping (unload beyond-target buys) --------------

    def _load_chunks(self, bot: Bot) -> None:
        self._chunks_loaded = True
        try:
            data = json.loads(bot.scalp_chunks or "[]")
        except (ValueError, TypeError):
            data = []
        self._chunks = {}
        for item in data:
            try:
                price, qty = float(item[0]), float(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            if price > 0 and qty > 1e-12:
                self._chunks[engine.price_key(price)] = [price, qty]

    def _save_chunks(self) -> None:
        db = SessionLocal()
        try:
            bot = db.get(Bot, self.bot_id)
            if bot is not None:
                bot.scalp_chunks = json.dumps(
                    [[p, q] for p, q in self._chunks.values()]
                )
                db.commit()
        except Exception:  # noqa: BLE001 - bookkeeping must not kill the tick
            log.exception("bot %s failed to persist chunks", self.bot_id)
        finally:
            db.close()

    def _add_chunk(self, price: float, qty: float) -> None:
        if price <= 0 or qty <= 1e-12:
            return
        entry = self._chunks.setdefault(engine.price_key(price), [price, 0.0])
        entry[1] += qty
        self._chunks_dirty = True

    def _consume_chunks(self, anchor: float, qty: float) -> None:
        """An unload order (anchored at `anchor`) filled: remove that quantity
        from the chunks nearest the anchor (its batch members)."""
        remaining = qty
        ordered = sorted(self._chunks.items(),
                         key=lambda kv: abs(kv[1][0] - anchor))
        for key, (_, have) in ordered:
            if remaining <= 1e-12:
                break
            take = min(have, remaining)
            remaining -= take
            if have - take <= 1e-12:
                del self._chunks[key]
            else:
                self._chunks[key][1] = have - take
            self._chunks_dirty = True

    def _process_fills(self, state: MarketState, config: StrategyConfig,
                       target: float) -> None:
        """Fold websocket fill events into the chunk ledger."""
        with self._fills_lock:
            fills, self._ws_fills = self._ws_fills, []
        if not fills:
            return
        open_side = "SELL" if config.direction == "SHORT" else "BUY"

        # Opening fills: the part of each fill that pushed the position beyond
        # target becomes an unload chunk at that fill's price.
        buys = [f for f in fills
                if f["side"] == open_side and f["price"] > 0 and f["qty"] > 0]
        running = state.position_notional - sum(f["price"] * f["qty"] for f in buys)
        for f in buys:
            after = running + f["price"] * f["qty"]
            if after > target:
                chunk_q = (f["qty"] if running >= target
                           else (after - target) / f["price"])
                self._add_chunk(f["price"], chunk_q)
            running = after

        # Unload fills: shrink the ledger by what was sold.
        for f in fills:
            if f["side"] != open_side and "-scalp-" in f["cid"]:
                self._scalp_done[f["cid"]] = (
                    self._scalp_done.get(f["cid"], 0.0) + f["qty"]
                )
                self._consume_chunks(_anchor_from_cid(f["cid"]), f["qty"])
                if f["status"] == "FILLED":
                    self._scalp_open.discard(f["cid"])
                    self._scalp_done.pop(f["cid"], None)

    def _sync_scalp_rest(self, svc, symbol: str, raw_open: list) -> None:
        """REST fallback: a scalp order that was resting but is now gone either
        filled or was cancelled — ask Binance which, so a fill the websocket
        missed doesn't get re-placed and sell the position twice."""
        open_cids = {str(o.get("clientOrderId", "")) for o in raw_open}
        for cid in list(self._scalp_open):
            if cid in open_cids:
                continue
            self._scalp_open.discard(cid)
            try:
                order = svc.get_order(symbol, cid)
            except Exception:  # noqa: BLE001 - engine's excess cap bounds drift
                self._scalp_done.pop(cid, None)
                continue
            done = float(order.get("executedQty", 0) or 0)
            done -= self._scalp_done.pop(cid, 0.0)
            if done > 1e-12:
                self._consume_chunks(_anchor_from_cid(cid), done)

    # -- reconciliation ---------------------------------------------------

    def _cid(self, engine_id: str) -> str:
        # "ab-dca-1" -> "b{id}-dca-1"
        return self.prefix + engine_id[3:]

    def _reconcile(self, symbol, config, svc, desired: list[DesiredOrder],
                   fill_detected, raw_open):
        bot_orders = {
            o["clientOrderId"]: o
            for o in raw_open
            if str(o.get("clientOrderId", "")).startswith(self.prefix)
        }
        self._status["open_orders"] = len(bot_orders)
        for cid in bot_orders:
            if "-scalp-" in cid:
                self._scalp_open.add(cid)

        filters = svc.symbol_filters(symbol)
        desired_by_id = {self._cid(d.client_order_id): d for d in desired}
        price_tol = config.dca_step_pct / 100.0 / 2.0

        for cid, d in desired_by_id.items():
            existing = bot_orders.get(cid)
            if existing is not None:
                existing_price = float(existing["price"])
                drift = abs(existing_price - d.price) / max(existing_price, 1e-9)
                side_changed = existing.get("side") != d.side
                # Scalp orders sit at fixed prices, but their batch quantity
                # can change as chunks come and go — recreate on qty drift.
                qty_changed = d.role == "scalp" and abs(
                    float(existing.get("origQty", 0) or 0) - d.quantity
                ) > max(filters.min_qty, 0.01 * d.quantity)
                force = side_changed or qty_changed or (
                    fill_detected
                    and d.role in ("take_profit", "rebalance", "reaccumulate")
                )
                if drift <= price_tol and not force:
                    continue
                self._drop_scalp_tracking(cid)
                self._safe_cancel(svc, symbol, existing["orderId"])

            if d.quantity < filters.min_qty:
                continue
            if filters.min_notional and d.quantity * d.price < filters.min_notional:
                continue
            self._safe_place(svc, symbol, d, cid)

        for cid, o in bot_orders.items():
            if cid not in desired_by_id:
                self._drop_scalp_tracking(cid)
                self._safe_cancel(svc, symbol, o["orderId"])

    def _drop_scalp_tracking(self, cid: str) -> None:
        # We cancel this order ourselves — don't let the REST fallback later
        # mistake its absence for a fill.
        if "-scalp-" in cid:
            self._scalp_open.discard(cid)
            self._scalp_done.pop(cid, None)

    def _cancel_all_bot_orders(self) -> int:
        loaded = self._load()
        if loaded is None:
            return 0
        bot, account = loaded
        svc = binance_client.get_service_for_account(account)
        raw = svc.get_raw_open_orders(bot.symbol)
        count = 0
        for o in raw:
            if str(o.get("clientOrderId", "")).startswith(self.prefix):
                self._safe_cancel(svc, bot.symbol, o["orderId"])
                count += 1
        return count

    def _safe_place(self, svc, symbol, d: DesiredOrder, cid: str) -> None:
        try:
            svc.place_limit_order(
                symbol=symbol, side=d.side, quantity=d.quantity, price=d.price,
                reduce_only=d.reduce_only, client_order_id=cid,
            )
        except BinanceAPIException as exc:
            log.warning("bot %s place %s failed: %s", self.bot_id, cid, exc.message)

    def _safe_cancel(self, svc, symbol, order_id: Any) -> None:
        try:
            svc.cancel_order(symbol, str(order_id))
        except BinanceAPIException as exc:
            log.warning("bot %s cancel %s failed: %s", self.bot_id, order_id, exc.message)
