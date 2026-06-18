"""Per-bot strategy runner.

One thread per running bot. Each tick it reloads the bot's config + account
from the DB, pulls a market snapshot from that account's Binance client, asks
the engine for the desired orders, and reconciles. Orders are namespaced per
bot (client id prefix "b{bot_id}-") so multiple bots never touch each other's
orders.
"""
from __future__ import annotations

import logging
import threading
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
        self._twm = None  # ThreadedWebsocketManager
        self._ws_init_done = False
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

        opposite = "SHORT" if config.direction == "LONG" else "LONG"
        if any(p.side == opposite for p in positions):
            self._status["notes"] = [
                f"{opposite} position open but bot is {config.direction}; "
                "close it before trading this direction"
            ]
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

        result = engine.plan(state, config)
        self._status["notes"] = result.notes
        self._status["desired_orders"] = len(result.orders)
        self._reconcile(symbol, config, svc, result.orders, fill_detected)

    # -- reconciliation ---------------------------------------------------

    def _cid(self, engine_id: str) -> str:
        # "ab-dca-1" -> "b{id}-dca-1"
        return self.prefix + engine_id[3:]

    def _reconcile(self, symbol, config, svc, desired: list[DesiredOrder], fill_detected):
        raw_open = svc.get_raw_open_orders(symbol)
        bot_orders = {
            o["clientOrderId"]: o
            for o in raw_open
            if str(o.get("clientOrderId", "")).startswith(self.prefix)
        }
        self._status["open_orders"] = len(bot_orders)

        filters = svc.symbol_filters(symbol)
        desired_by_id = {self._cid(d.client_order_id): d for d in desired}
        price_tol = config.dca_step_pct / 100.0 / 2.0

        for cid, d in desired_by_id.items():
            existing = bot_orders.get(cid)
            if existing is not None:
                existing_price = float(existing["price"])
                drift = abs(existing_price - d.price) / max(existing_price, 1e-9)
                side_changed = existing.get("side") != d.side
                force = side_changed or (
                    fill_detected and d.role in ("take_profit", "rebalance")
                )
                if drift <= price_tol and not force:
                    continue
                self._safe_cancel(svc, symbol, existing["orderId"])

            if d.quantity < filters.min_qty:
                continue
            if filters.min_notional and d.quantity * d.price < filters.min_notional:
                continue
            self._safe_place(svc, symbol, d, cid)

        for cid, o in bot_orders.items():
            if cid not in desired_by_id:
                self._safe_cancel(svc, symbol, o["orderId"])

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
