"""Per-account wrapper around python-binance for USDT-M futures.

Each Account has its own API credentials, so a BinanceService instance is bound
to one account's keys. Instances are cached by account id (rebuilt when the
account's credentials change). The underlying python-binance Client is
synchronous; FastAPI sync handlers and the runner threads call it directly.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from binance.client import Client
from binance.exceptions import BinanceAPIException

from app.core.security import decrypt_secret
from app.schemas.account import AccountSummary
from app.schemas.order import Order
from app.schemas.position import Position

_MARGIN_ALREADY_SET = -4046


@dataclass
class SymbolFilters:
    price_tick: float
    qty_step: float
    min_qty: float
    min_notional: float


class BinanceService:
    def __init__(self, api_key: str, api_secret: str, testnet: bool) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._client: Optional[Client] = None
        self._filters: dict[str, SymbolFilters] = {}
        self._lock = threading.Lock()

    def _client_(self) -> Client:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = Client(
                        self._api_key, self._api_secret, testnet=self._testnet
                    )
        return self._client

    # -- connectivity -----------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        try:
            acct = self._client_().futures_account()
            return {
                "ok": True,
                "can_trade": acct.get("canTrade", False),
                "total_wallet_balance": float(acct.get("totalWalletBalance", 0)),
            }
        except BinanceAPIException as exc:
            return {"ok": False, "error": f"{exc.code}: {exc.message}"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # -- reads ------------------------------------------------------------

    def get_account_summary(self) -> AccountSummary:
        acct = self._client_().futures_account()
        margin_balance = float(acct.get("totalMarginBalance", 0)) or 1.0
        maint_margin = float(acct.get("totalMaintMargin", 0))
        return AccountSummary(
            total_balance=float(acct.get("totalWalletBalance", 0)),
            available_balance=float(acct.get("availableBalance", 0)),
            unrealized_pnl=float(acct.get("totalUnrealizedProfit", 0)),
            margin_ratio=round(maint_margin / margin_balance * 100, 2),
        )

    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        client = self._client_()
        raw = (
            client.futures_position_information(symbol=symbol)
            if symbol
            else client.futures_position_information()
        )
        positions: list[Position] = []
        for p in raw:
            amt = float(p.get("positionAmt", 0))
            if amt == 0:
                continue
            entry = float(p.get("entryPrice", 0))
            mark = float(p.get("markPrice", 0))
            leverage = int(float(p.get("leverage", 1)))
            pnl = float(p.get("unRealizedProfit", 0))
            margin = float(p.get("isolatedMargin", 0)) or (
                abs(amt) * entry / leverage if leverage else 0
            )
            pnl_pct = (pnl / margin * 100) if margin else 0.0
            positions.append(
                Position(
                    symbol=p["symbol"],
                    side="LONG" if amt > 0 else "SHORT",
                    size=abs(amt),
                    entry_price=entry,
                    mark_price=mark,
                    leverage=leverage,
                    unrealized_pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    liquidation_price=float(p.get("liquidationPrice", 0)),
                    margin=round(margin, 2),
                )
            )
        return positions

    def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        client = self._client_()
        raw = (
            client.futures_get_open_orders(symbol=symbol)
            if symbol
            else client.futures_get_open_orders()
        )
        return [self._to_order(o) for o in raw]

    @staticmethod
    def _to_order(o: dict[str, Any]) -> Order:
        return Order(
            order_id=str(o["orderId"]),
            symbol=o["symbol"],
            side=o["side"],
            type=o["type"],
            quantity=float(o["origQty"]),
            price=float(o["price"]),
            status=o["status"],
            reduce_only=bool(o.get("reduceOnly", False)),
        )

    def get_raw_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        return self._client_().futures_get_open_orders(symbol=symbol)

    def get_open_orders_with_prefix(self, symbol: str, prefix: str) -> list[Order]:
        raw = self._client_().futures_get_open_orders(symbol=symbol)
        return [
            self._to_order(o)
            for o in raw
            if str(o.get("clientOrderId", "")).startswith(prefix)
        ]

    def get_mark_price(self, symbol: str) -> float:
        return float(self._client_().futures_mark_price(symbol=symbol)["markPrice"])

    def get_realized_income(self, symbol: str, start_ms: Optional[int]) -> float:
        """Net realized PnL for a symbol (realized profit minus commissions),
        from trade history. More reliable than the income endpoint on testnet.
        """
        params: dict[str, Any] = {"symbol": symbol, "limit": 1000}
        if start_ms:
            params["startTime"] = start_ms
        trades = self._client_().futures_account_trades(**params)
        return sum(
            float(t.get("realizedPnl", 0)) - float(t.get("commission", 0))
            for t in trades
        )

    # -- trading ----------------------------------------------------------

    def prepare_symbol(self, symbol: str, leverage: int) -> None:
        client = self._client_()
        try:
            client.futures_change_margin_type(symbol=symbol, marginType="ISOLATED")
        except BinanceAPIException as exc:
            if exc.code != _MARGIN_ALREADY_SET:
                raise
        client.futures_change_leverage(symbol=symbol, leverage=leverage)

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> dict[str, Any]:
        filters = self._get_filters(symbol)
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": self._round_step(quantity, filters.qty_step),
            "price": self._round_step(price, filters.price_tick),
            "reduceOnly": reduce_only,
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return self._client_().futures_create_order(**params)

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        return self._client_().futures_cancel_order(symbol=symbol, orderId=int(order_id))

    # -- websockets -------------------------------------------------------

    def make_ws_manager(self):
        """A ThreadedWebsocketManager bound to this account's credentials.

        Used to subscribe to the futures user-data stream (order fills,
        position updates) for low-latency reaction. Caller starts/stops it.
        """
        from binance import ThreadedWebsocketManager

        return ThreadedWebsocketManager(
            api_key=self._api_key, api_secret=self._api_secret, testnet=self._testnet
        )

    # -- helpers ----------------------------------------------------------

    def symbol_filters(self, symbol: str) -> SymbolFilters:
        return self._get_filters(symbol)

    def _get_filters(self, symbol: str) -> SymbolFilters:
        if symbol in self._filters:
            return self._filters[symbol]
        info = self._client_().futures_exchange_info()
        for s in info["symbols"]:
            if s["symbol"] != symbol:
                continue
            f = {flt["filterType"]: flt for flt in s["filters"]}
            filters = SymbolFilters(
                price_tick=float(f["PRICE_FILTER"]["tickSize"]),
                qty_step=float(f["LOT_SIZE"]["stepSize"]),
                min_qty=float(f["LOT_SIZE"]["minQty"]),
                min_notional=float(f.get("MIN_NOTIONAL", {}).get("notional", 0)),
            )
            self._filters[symbol] = filters
            return filters
        raise ValueError(f"Symbol {symbol} not found on exchange")

    @staticmethod
    def _round_step(value: float, step: float) -> float:
        if step <= 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)


# -- per-account cache ------------------------------------------------------

_cache: dict[int, tuple[tuple[str, bool], BinanceService]] = {}
_cache_lock = threading.Lock()


def get_service_for_account(account) -> BinanceService:
    """Return a cached BinanceService for an Account model (decrypts secret)."""
    sig = (account.api_key, account.testnet)
    with _cache_lock:
        cached = _cache.get(account.id)
        if cached and cached[0] == sig:
            return cached[1]
        svc = BinanceService(
            account.api_key, decrypt_secret(account.api_secret_encrypted), account.testnet
        )
        _cache[account.id] = (sig, svc)
        return svc


def invalidate_account(account_id: int) -> None:
    with _cache_lock:
        _cache.pop(account_id, None)


def utc_ms() -> int:
    return int(time.time() * 1000)
