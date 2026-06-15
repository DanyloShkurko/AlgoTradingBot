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
        # Position is open: spread the grid — averaging ladder + break-even +
        # take-profit exits.
        _plan_dca_ladder(p, state, config, target, buying_power, growth, step)
        _plan_rebalance(p, state, config, target, growth)
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


def _plan_rebalance(
    p: StrategyPlan,
    state: MarketState,
    config: StrategyConfig,
    target: float,
    growth: float,
) -> None:
    _, _, close_side = _direction(config)
    # Only trim once the position exceeds target by a full averaging step.
    if state.position_notional <= target * growth:
        return
    excess_qty = (state.position_notional - target) / state.avg_entry_price
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
        unit = abs(entry - liq)
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
