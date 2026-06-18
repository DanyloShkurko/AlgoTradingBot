"""Unit tests for the DCA strategy planner."""
from app.schemas.strategy import StrategyConfig
from app.strategy.engine import plan, target_notional
from app.strategy.models import MarketState


def cfg(**overrides) -> StrategyConfig:
    base = dict(
        symbol="BTCUSDT",
        leverage=10,
        target_position_pct=15.0,
        dca_step_pct=2.0,
        dca_add_pct=20.0,
        take_profit_pct=20.0,
        take_profit_close_pct=33.0,
        max_dca_orders=8,
        enabled=True,
    )
    base.update(overrides)
    return StrategyConfig(**base)


def roles(p):
    return [o.role for o in p.orders]


def by_role(p, role):
    return [o for o in p.orders if o.role == role]


# -- target sizing --------------------------------------------------------

def test_target_notional_is_margin_times_leverage():
    state = MarketState(balance=1000, mark_price=30000)
    assert target_notional(state, cfg()) == 1500.0  # 1000 * 15% * 10


# -- flat: a single entry order, no grid ----------------------------------

def test_flat_emits_single_entry_order():
    state = MarketState(balance=1000, mark_price=30000)
    p = plan(state, cfg())
    assert roles(p) == ["entry"]
    o = p.orders[0]
    assert o.side == "BUY" and not o.reduce_only


def test_entry_uses_configured_price():
    state = MarketState(balance=1000, mark_price=30306)
    o = plan(state, cfg(entry_price=30063)).orders[0]
    assert o.role == "entry"
    assert o.price == 30063


def test_entry_auto_price_one_step_from_mark_when_unset():
    state = MarketState(balance=1000, mark_price=30000)
    o = plan(state, cfg(entry_price=0)).orders[0]
    assert o.price == 30000 * (1 - 0.02)  # one DCA step below mark for long


def test_short_flat_emits_single_sell_entry_above_mark():
    state = MarketState(balance=1000, mark_price=30000)
    o = plan(state, cfg(direction="SHORT")).orders[0]
    assert o.role == "entry" and o.side == "SELL" and not o.reduce_only
    assert o.price == 30000 * (1 + 0.02)  # one step above mark for short


# -- in position: the grid is spread --------------------------------------

def small_long(**kw) -> MarketState:
    base = dict(balance=1000, mark_price=30000, position_size=0.001,
                avg_entry_price=30000)
    base.update(kw)
    return MarketState(**base)


def test_dca_rungs_are_below_price_and_spaced():
    dca = by_role(plan(small_long(), cfg()), "dca")
    assert all(o.price < 30000 for o in dca)
    assert dca[0].price == 30000 * (1 - 0.02 * 1)
    assert dca[1].price == 30000 * (1 - 0.02 * 2)


def test_dca_sizing_is_geometric():
    dca = by_role(plan(small_long(), cfg()), "dca")
    n0 = dca[0].quantity * dca[0].price
    n1 = dca[1].quantity * dca[1].price
    assert round(n1 / n0, 4) == 1.20  # grows by dca_add_pct = 20%


def test_dca_capped_by_max_orders():
    assert len(by_role(plan(small_long(), cfg(max_dca_orders=3)), "dca")) == 3


def test_dca_capped_by_buying_power():
    state = small_long(balance=100, position_size=0.001)
    p = plan(state, cfg(max_dca_orders=50))
    deployed = sum(o.quantity * o.price for o in by_role(p, "dca"))
    assert deployed <= 100 * 10  # balance * leverage
    assert any("buying power" in n for n in p.notes)


def test_short_dca_ladder_above_when_in_position():
    state = MarketState(balance=1000, mark_price=30000, position_size=0.001,
                        avg_entry_price=30000)
    dca = by_role(plan(state, cfg(direction="SHORT")), "dca")
    assert all(o.side == "SELL" and o.price > 30000 for o in dca)


def test_in_position_under_target_has_tp_no_rebalance():
    state = MarketState(balance=1000, mark_price=31000,
                        position_size=0.01, avg_entry_price=30000)
    p = plan(state, cfg())
    assert "take_profit" in roles(p)
    assert "rebalance" not in roles(p)


def test_take_profit_prices_above_entry_and_reduce_only():
    state = MarketState(balance=1000, mark_price=31000,
                        position_size=0.01, avg_entry_price=30000)
    tp = by_role(plan(state, cfg()), "take_profit")
    assert tp
    assert all(o.price > 30000 for o in tp)
    assert all(o.side == "SELL" and o.reduce_only for o in tp)
    assert len(tp) == 3  # 33% close -> round(1/0.33) = 3 levels


def test_take_profit_uses_liquidation_distance():
    # mark below all TP levels so every level is still "ahead".
    state = MarketState(balance=1000, mark_price=30500, position_size=0.03,
                        avg_entry_price=30000, liquidation_price=27000)
    tp = sorted(by_role(plan(state, cfg()), "take_profit"), key=lambda o: o.price)
    assert len(tp) == 3
    assert round(tp[0].price) == 31000
    assert round(tp[1].price) == 32000
    assert round(tp[2].price) == 33000  # mirror of liquidation


def test_take_profit_quantity_sweeps_full_position():
    state = MarketState(balance=1000, mark_price=30500, position_size=0.03,
                        avg_entry_price=30000, liquidation_price=27000)
    tp = by_role(plan(state, cfg()), "take_profit")
    assert sum(o.quantity for o in tp) == 0.03
    assert all(o.reduce_only for o in tp)


def test_take_profit_skips_levels_already_passed():
    # Price ran up past the first TP (31000): it must NOT be re-armed, or it
    # would sell at market every tick. Only levels above mark remain.
    state = MarketState(balance=1000, mark_price=31500, position_size=0.024,
                        avg_entry_price=30000, liquidation_price=27000)
    tp = by_role(plan(state, cfg()), "take_profit")
    assert tp, "expected remaining take-profit levels"
    assert all(o.price > 31500 for o in tp)  # nothing at/below current price
    assert len(tp) == 2                       # 31000 dropped, 32000 + 33000 left
    assert round(sum(o.quantity for o in tp), 6) == 0.024  # whole remainder


def test_take_profit_caps_levels_to_min_notional():
    # Position ~$46; min notional $20 → can't make 3 orders each >= $20, so
    # the ladder is capped to 2 (otherwise none would be placed).
    state = MarketState(balance=1000, mark_price=1773, position_size=0.026,
                        avg_entry_price=1720, liquidation_price=1555,
                        min_order_notional=20)
    tp = by_role(plan(state, cfg()), "take_profit")
    assert len(tp) == 2
    assert all(o.quantity * o.price >= 20 for o in tp)  # each clears the minimum
    assert round(sum(o.quantity for o in tp), 6) == 0.026  # whole position


def test_take_profit_closes_all_when_past_every_target():
    # Mark above the top target → close the full remainder at the top level.
    state = MarketState(balance=1000, mark_price=40000, position_size=0.024,
                        avg_entry_price=30000, liquidation_price=27000)
    tp = by_role(plan(state, cfg()), "take_profit")
    assert len(tp) == 1
    assert round(tp[0].quantity, 6) == 0.024


def test_over_target_emits_breakeven_rebalance():
    state = MarketState(balance=1000, mark_price=29000,
                        position_size=0.1, avg_entry_price=30000)
    rebal = by_role(plan(state, cfg()), "rebalance")
    assert len(rebal) == 1
    o = rebal[0]
    assert o.side == "SELL" and o.reduce_only
    assert o.price == 30000  # break-even
    assert round(o.quantity, 6) == 0.05  # (3000 - 1500) / 30000


# -- SHORT in-position (mirror image) -------------------------------------

def test_short_take_profit_below_entry_buys_to_close():
    # mark above all (lower) short TP levels so every level is still ahead.
    state = MarketState(balance=1000, mark_price=29500, position_size=0.03,
                        avg_entry_price=30000, liquidation_price=33000)
    tp = sorted(by_role(plan(state, cfg(direction="SHORT")), "take_profit"),
                key=lambda o: o.price, reverse=True)
    assert len(tp) == 3
    assert all(o.side == "BUY" and o.reduce_only for o in tp)
    assert round(tp[0].price) == 29000
    assert round(tp[2].price) == 27000  # mirror of liquidation


def test_short_rebalance_buys_at_break_even():
    state = MarketState(balance=1000, mark_price=31000, position_size=0.1,
                        avg_entry_price=30000, liquidation_price=33000)
    rebal = by_role(plan(state, cfg(direction="SHORT")), "rebalance")
    assert len(rebal) == 1
    assert rebal[0].side == "BUY" and rebal[0].reduce_only
    assert rebal[0].price == 30000


# -- guards ---------------------------------------------------------------

def test_no_data_returns_empty_plan():
    assert plan(MarketState(balance=0, mark_price=0), cfg()).orders == []
