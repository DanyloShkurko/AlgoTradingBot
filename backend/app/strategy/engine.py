"""DCA futures strategy planner.

Pure functions: given a market snapshot + config, produce the set of limit
orders that *should* be resting on the exchange. The runner reconciles the
live order book to match this plan. No network, no side effects — fully
unit-testable.

Direction-aware (LONG or SHORT). LONG is the documented base case; SHORT is
its mirror image (sign = -1):

* Entry first: while flat, place ONE limit entry order at entry_price (or one
  DCA step from mark if entry_price is 0). The grid is only spread once that
  order fills and a position exists.
* Target active position notional = balance x target_position_pct% x leverage.
  The "100-200$ margin -> 1000-2000$ notional" working size, and the ceiling
  above which we trim back to break-even.
* DCA ladder: geometric rungs *against* the position (LONG: BUY below price;
  SHORT: SELL above price), each larger by dca_add_pct%, spaced dca_step_pct%
  apart, bounded by leveraged buying power (the cushion against liquidation).
* Rebalance: once the position grows beyond target by a full averaging step,
  a reduce-only order at the average entry (break-even) trims the excess.
* Take profit: reduce-only closes at fractions of the entry->liquidation
  distance, mirrored on the profit side of entry.
"""
from __future__ import annotations

from app.schemas.strategy import StrategyConfig
from app.strategy.models import DesiredOrder, MarketState, StrategyPlan


def price_key(price: float) -> str:
    """Stable client-order-id fragment for a price (97.25 -> "97_25")."""
    key = f"{price:.8f}".rstrip("0").rstrip(".")
    return key.replace(".", "_")


def _direction(config: StrategyConfig) -> tuple[int, str, str]:
    """Return (sign, open_side, close_side). sign +1 = LONG, -1 = SHORT."""
    if config.direction == "SHORT":
        return -1, "SELL", "BUY"
    return 1, "BUY", "SELL"


def target_notional(state: MarketState, config: StrategyConfig) -> float:
    return state.balance * (config.target_position_pct / 100.0) * config.leverage


def plan(state: MarketState, config: StrategyConfig) -> StrategyPlan:
    p = StrategyPlan()
    if state.mark_price <= 0 or state.balance <= 0:
        p.note("No market/balance data; nothing to do")
        return p

    target = target_notional(state, config)
    buying_power = state.balance * config.leverage
    growth = 1 + config.dca_add_pct / 100.0
    step = config.dca_step_pct / 100.0

    in_position = state.position_size > 0 and state.avg_entry_price > 0
    if in_position:
        # Position is open: spread the grid — averaging ladder + excess unload
        # + break-even + take-profit exits.
        _plan_dca_ladder(p, state, config, target, buying_power, growth, step)
        covered = _plan_scalp(p, state, config, target, step)
        _plan_rebalance(p, state, config, target, growth, covered)
        _plan_take_profit(p, state, config, target)
    else:
        # Flat: place only the single entry order and wait for it to fill.
        _plan_entry(p, state, config, target, step)

    return p


def _plan_entry(
    p: StrategyPlan,
    state: MarketState,
    config: StrategyConfig,
    target: float,
    step: float,
) -> None:
    sign, open_side, _ = _direction(config)
    price = (
        config.entry_price
        if config.entry_price > 0
        else state.mark_price * (1 - sign * step)
    )
    if price <= 0:
        return
    notional = target * (config.dca_add_pct / 100.0)  # first chunk
    p.add(
        DesiredOrder(
            role="entry",
            side=open_side,
            price=price,
            quantity=notional / price,
            reduce_only=False,
            client_order_id="ab-entry",
        )
    )
    p.note(f"Waiting for entry fill at {price:.2f}")


def _plan_dca_ladder(
    p: StrategyPlan,
    state: MarketState,
    config: StrategyConfig,
    target: float,
    buying_power: float,
    growth: float,
    step: float,
) -> None:
    sign, open_side, _ = _direction(config)

    # Ladder away from the market in the losing direction (LONG: below;
    # SHORT: above). When holding, anchor on the far side of our cost basis
    # so every rung deepens the average.
    anchor = state.mark_price
    if state.position_size > 0 and state.avg_entry_price > 0:
        anchor = (
            min(state.mark_price, state.avg_entry_price)
            if sign > 0
            else max(state.mark_price, state.avg_entry_price)
        )

    base = target * (config.dca_add_pct / 100.0)  # first rung notional
    deployed = state.position_notional

    for k in range(1, config.max_dca_orders + 1):
        price = anchor * (1 - sign * step * k)
        if price <= 0:
            break
        notional = base * (growth ** (k - 1))
        if deployed + notional > buying_power:
            p.note(f"DCA ladder stopped at rung {k}: buying power exhausted")
            break
        p.add(
            DesiredOrder(
                role="dca",
                side=open_side,
                price=price,
                quantity=notional / price,
                reduce_only=False,
                client_order_id=f"ab-dca-{k}",
            )
        )
        deployed += notional


def _plan_scalp(
    p: StrategyPlan,
    state: MarketState,
    config: StrategyConfig,
    target: float,
    step: float,
) -> float:
    """Unload what was bought beyond target: each chunk is offered one DCA
    step above its own fill price (SHORT: below), so every round trip banks a
    profit no matter where the position average sits. Chunks too small for the
    exchange minimum are batched together, anchored on the batch's most
    expensive buy so no member is sold below its own cost; a remainder still
    below the minimum is left to the break-even trim. Returns the quantity
    covered by the planned unload orders.
    """
    sign, _, close_side = _direction(config)
    if not state.excess_chunks or state.avg_entry_price <= 0:
        return 0.0
    # Never unload more than the real excess over target: chunks are runner
    # bookkeeping and can lag reality across restarts or missed fills.
    available = max(0.0, (state.position_notional - target) / state.avg_entry_price)
    if available <= 1e-12:
        return 0.0

    chunks = sorted(state.excess_chunks, key=lambda c: c[0], reverse=sign < 0)
    covered = 0.0
    batch: list[tuple[float, float]] = []
    batch_notional = 0.0

    def flush() -> None:
        nonlocal covered, batch, batch_notional
        if not batch:
            return
        prices = [pr for pr, _ in batch]
        anchor = max(prices) if sign > 0 else min(prices)
        qty = sum(q for _, q in batch)
        p.add(
            DesiredOrder(
                role="scalp",
                side=close_side,
                price=anchor * (1 + sign * step),
                quantity=qty,
                reduce_only=True,
                client_order_id=f"ab-scalp-{price_key(anchor)}",
            )
        )
        covered += qty
        batch, batch_notional = [], 0.0

    for price, qty in chunks:
        take = min(qty, available)
        if take <= 1e-12:
            break
        available -= take
        batch.append((price, take))
        batch_notional += price * take
        if state.min_order_notional <= 0 or batch_notional >= state.min_order_notional:
            flush()
    # Anything left in `batch` is below min notional — break-even trim covers it.
    if covered:
        p.note(f"Unloading {covered:.6f} bought beyond target")
    return covered


def _plan_rebalance(
    p: StrategyPlan,
    state: MarketState,
    config: StrategyConfig,
    target: float,
    growth: float,
    covered: float = 0.0,
) -> None:
    sign, open_side, close_side = _direction(config)
    notional = state.position_notional

    # Over target by a full averaging step → trim back to target (reduce-only),
    # minus whatever the scalp unload orders already cover.
    if notional > target * growth:
        excess_qty = (notional - target) / state.avg_entry_price - covered
        if excess_qty > 1e-12:
            p.add(
                DesiredOrder(
                    role="rebalance",
                    side=close_side,
                    price=state.avg_entry_price,
                    quantity=excess_qty,
                    reduce_only=True,
                    client_order_id="ab-rebal",
                )
            )
            p.note(
                f"Rebalance: trim {excess_qty:.6f} at break-even "
                f"{state.avg_entry_price:.2f}"
            )
        return

    # After take-profits sell into a pump, top the position back up to target
    # at the average so the freed capital is recycled: sell high → refill to
    # target at the average → repeat.
    on_profit_side = (
        state.mark_price > state.avg_entry_price if sign > 0
        else state.mark_price < state.avg_entry_price
    )
    # The check: target is the capital we want held IN the position; the rest
    # stays as grid. If the position already holds >= target, don't add — let
    # take-profits de-risk (over-target excess is trimmed by the branch above).
    # If it holds < target, refill UP TO target at the average; the remaining
    # buying power stays in the grid (DCA ladder).
    if notional < target and on_profit_side:
        qty = (target - notional) / state.avg_entry_price
        p.add(
            DesiredOrder(
                role="reaccumulate",
                side=open_side,
                price=state.avg_entry_price,
                quantity=qty,
                reduce_only=False,
                client_order_id="ab-reacc",
            )
        )
        p.note(
            f"Re-accumulate {qty:.6f} to target at average "
            f"{state.avg_entry_price:.2f}"
        )


def _take_profit_prices(
    state: MarketState, config: StrategyConfig, n_levels: int
) -> list[float]:
    """Exit prices for the N take-profit levels.

    Primary model: the distance between entry and liquidation defines the
    "100%" risk unit; we mirror it on the profit side of entry (LONG: above,
    SHORT: below), top level at the +100% point, the rest at equal fractions
    (k/N). As averaging moves entry and liquidation, these targets follow.

    Fallback (liquidation unknown, e.g. freshly opened): fixed take_profit_pct%
    steps on the profit side of entry.
    """
    sign, _, _ = _direction(config)
    entry = state.avg_entry_price
    liq = state.liquidation_price
    # Valid liquidation sits on the losing side: below entry for LONG, above
    # for SHORT.
    liq_valid = liq > 0 and ((liq < entry) if sign > 0 else (liq > entry))
    if liq_valid:
        # Mirror the entry→liquidation distance to the profit side, scaled by
        # tp_width_pct (100% = exactly that distance, higher = wider/farther).
        unit = abs(entry - liq) * (config.tp_width_pct / 100.0)
        return [entry + sign * (k / n_levels) * unit for k in range(1, n_levels + 1)]
    tp_pct = config.take_profit_pct / 100.0
    return [entry * (1 + sign * tp_pct * k) for k in range(1, n_levels + 1)]


def _plan_take_profit(
    p: StrategyPlan,
    state: MarketState,
    config: StrategyConfig,
    target: float,
) -> None:
    sign, _, close_side = _direction(config)
    close_frac = config.take_profit_close_pct / 100.0
    if close_frac <= 0:
        return

    # Take profit on the portion we keep; any excess above target is handled
    # by the break-even rebalance order.
    base_qty = state.position_size
    if state.position_notional > target:
        base_qty = min(state.position_size, target / state.avg_entry_price)

    # e.g. 33% -> 3 levels
    n_levels = min(6, max(1, round(1 / close_frac)))
    prices = _take_profit_prices(state, config, n_levels)

    # Only keep levels the market hasn't reached yet (LONG: above mark; SHORT:
    # below). A level already passed by price would be a reduce-only order on
    # the wrong side of the market and fill instantly every tick — bleeding the
    # position out near current price ("cascade"). The remaining position is
    # spread across the levels still ahead, which naturally gives the
    # "1/3 -> 1/2 of the rest -> all" ladder as price climbs.
    ahead = [pr for pr in prices if (pr > state.mark_price if sign > 0 else pr < state.mark_price)]
    if not ahead:
        # Price is already past every target → close the remainder at the top.
        ahead = [prices[-1]]

    # A tiny position can't be split into N orders that each clear the
    # exchange minimum notional — then none get placed and the position is
    # stuck. Cap the level count to how many min-notional orders it affords,
    # taking the nearest levels (they fill soonest).
    if state.min_order_notional > 0 and state.mark_price > 0:
        affordable = int((base_qty * state.mark_price) // state.min_order_notional)
        ahead = ahead[: max(1, min(len(ahead), affordable))]

    n = len(ahead)
    remaining = base_qty
    for k, price in enumerate(ahead, start=1):
        if remaining <= 1e-12:
            break
        # Even split across the levels ahead; the last one sweeps the remainder.
        qty = remaining if k == n else min(base_qty / n, remaining)
        p.add(
            DesiredOrder(
                role="take_profit",
                side=close_side,
                price=price,
                quantity=qty,
                reduce_only=True,
                client_order_id=f"ab-tp-{k}",
            )
        )
        remaining -= qty
