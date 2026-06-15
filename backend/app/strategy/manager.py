"""Manages the set of running bot runners (one thread per active bot)."""
from __future__ import annotations

import threading
from typing import Any

from app.core.db import SessionLocal
from app.models import Bot
from app.strategy.bot_runner import BotRunner

_IDLE_STATUS: dict[str, Any] = {
    "running": False,
    "last_tick_at": None,
    "last_error": None,
    "desired_orders": 0,
    "open_orders": 0,
    "notes": [],
}


class BotManager:
    def __init__(self) -> None:
        self._runners: dict[int, BotRunner] = {}
        self._lock = threading.Lock()

    def _runner(self, bot_id: int) -> BotRunner:
        with self._lock:
            runner = self._runners.get(bot_id)
            if runner is None:
                runner = BotRunner(bot_id)
                self._runners[bot_id] = runner
            return runner

    def start(self, bot_id: int) -> None:
        self._runner(bot_id).start()

    def stop(self, bot_id: int, cancel_orders: bool = True) -> None:
        with self._lock:
            runner = self._runners.get(bot_id)
        if runner:
            runner.stop(cancel_orders=cancel_orders)

    def remove(self, bot_id: int, cancel_orders: bool = True) -> None:
        with self._lock:
            runner = self._runners.pop(bot_id, None)
        if runner:
            runner.stop(cancel_orders=cancel_orders)

    def is_running(self, bot_id: int) -> bool:
        with self._lock:
            runner = self._runners.get(bot_id)
        return runner.is_running() if runner else False

    def status(self, bot_id: int) -> dict[str, Any]:
        with self._lock:
            runner = self._runners.get(bot_id)
        return runner.status() if runner else dict(_IDLE_STATUS)

    def resume_enabled(self) -> None:
        db = SessionLocal()
        try:
            ids = [b.id for b in db.query(Bot).filter(Bot.enabled.is_(True)).all()]
        finally:
            db.close()
        for bot_id in ids:
            self.start(bot_id)

    def stop_all(self, cancel_orders: bool = False) -> None:
        with self._lock:
            runners = list(self._runners.values())
        for runner in runners:
            runner.stop(cancel_orders=cancel_orders)


bot_manager = BotManager()
