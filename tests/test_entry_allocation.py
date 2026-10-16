"""Cash reserve conservation and sizing semantics, not just output snapshots."""

import math

import pandas as pd
import pytest

from tradingagents.strategy_backtest import simulate


def candles(prices):
    return pd.DataFrame({"Date": pd.date_range("2020-01-01", periods=len(prices), tz="UTC"),
                         "Open": prices, "High": [p + 1 for p in prices],
                         "Low": [p - 1 for p in prices], "Close": prices, "Volume": 100})


def dates(frame):
    return frame.Date.iloc[200].strftime("%Y-%m-%d"), frame.Date.iloc[-1].strftime("%Y-%m-%d")


def test_cash_reserve_survives_buy_and_terminal_sale_with_costs():
    frame = candles([100.] * 201 + [110.])
    result = simulate(frame, *dates(frame), strategy="buy_hold", allocation_fraction=.5,
                      fee_bps=100, slippage_bps=100)
    qty = 5000 / (100 * 1.01 * 1.01)
    proceeds = qty * 110 * .99 * .99
    assert result["fills"][0]["cash_after"] == 5000
    assert result["fills"][0]["quantity"] == pytest.approx(qty)
    assert result["metrics"]["final_usd"] == pytest.approx(5000 + proceeds)
    assert result["trades"][0]["pnl_usd"] == pytest.approx(proceeds - 5000)
    assert result["trades"][0]["exit_position_proceeds"] == pytest.approx(proceeds)
    assert result["curve"][-1]["btc"] == 0


def test_initial_50pct_is_not_a_continuous_exposure_cap():
    frame = candles([100.] * 201 + [200., 300.])
    result = simulate(frame, *dates(frame), strategy="buy_hold", allocation_fraction=.5,
                      fee_bps=0, slippage_bps=0)
    assert result["curve"][0]["close_position_weight"] == .5
    assert result["curve"][1]["close_position_weight"] == pytest.approx(2 / 3)
    assert result["metrics"]["final_usd"] == 20000


def test_each_new_entry_uses_half_current_cash_and_pnl_reconciles():
    prices = [100.] * 200 + [110., 120., 80., 70.] + [70.] * 22 + [130., 140., 60., 50.]
    frame = candles(prices)
    result = simulate(frame, *dates(frame), allocation_fraction=.5, fee_bps=60, slippage_bps=10)
    assert len(result["trades"]) >= 2
    wealth = 10000
    for trade in result["trades"]:
        assert trade["entry_cash"] == pytest.approx(wealth * .5)
        wealth += trade["pnl_usd"]
        assert trade["exit_cash"] == pytest.approx(wealth)
    assert sum(t["pnl_usd"] for t in result["trades"]) == pytest.approx(result["metrics"]["final_usd"] - 10000)
    assert all(p["cash"] >= 0 for p in result["curve"])


@pytest.mark.parametrize("fraction", [0, -1, 1.001, math.inf, math.nan])
def test_invalid_allocations_rejected(fraction):
    frame = candles([100.] * 202)
    with pytest.raises(ValueError, match="allocation"):
        simulate(frame, *dates(frame), allocation_fraction=fraction)


def test_future_row_cannot_change_50pct_fixed_window():
    frame = candles([100.] * 200 + [110., 120., 130.])
    start, end = dates(frame)
    original = simulate(frame, start, end, allocation_fraction=.5)
    more = candles([100.] * 200 + [110., 120., 130., 100000.])
    assert simulate(more, start, end, allocation_fraction=.5) == original
