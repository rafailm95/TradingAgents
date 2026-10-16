"""Cash conservation, adverse execution, chronology and independent recurrence."""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradingagents.strategy_backtest import features, load_daily, run_experiment, simulate


def frame_for(closes, opens=None):
    opens = closes if opens is None else opens
    return pd.DataFrame({"Date": pd.date_range("2020-01-01", periods=len(closes), tz="UTC"),
        "Open": opens, "High": np.maximum(opens, closes) + 1,
        "Low": np.minimum(opens, closes) - 1, "Close": closes, "Volume": 100.0})


def bounds(frame, first=200):
    return frame.Date.iloc[first].strftime("%Y-%m-%d"), frame.Date.iloc[-1].strftime("%Y-%m-%d")


def test_signal_waits_until_next_open_and_gap_is_not_ignored():
    frame = frame_for([100.] * 200 + [110., 115., 80., 75., 76.],
                      [100.] * 200 + [100., 120., 115., 70., 75.])
    result = simulate(frame, *bounds(frame), fee_bps=0, slippage_bps=0)
    trade = result["trades"][0]
    assert trade["entry_signal_date"] == frame.Date.iloc[200].strftime("%Y-%m-%d")
    assert trade["entry_date"] == frame.Date.iloc[201].strftime("%Y-%m-%d")
    assert trade["entry_fill"] == 120
    assert trade["exit_fill"] == 70
    assert trade["exit_reason"] == "signal"
    assert result["metrics"]["final_usd"] == pytest.approx(10000 * 70 / 120)


def test_breakout_excludes_current_high_and_uses_20_prior_days():
    frame = frame_for([100.] * 200 + [110.])
    frame.loc[200, "High"] = 1000
    computed = features(frame)
    assert computed.prior_high20.iloc[-1] == 101
    assert bool(computed.entry.iloc[-1])


def test_buy_hold_hand_calculated_two_sided_costs_and_terminal_exit():
    frame = frame_for([100.] * 200 + [105., 110.], [100.] * 202)
    result = simulate(frame, *bounds(frame), strategy="buy_hold", fee_bps=100, slippage_bps=100)
    expected_quantity = 10000 / (100 * 1.01 * 1.01)
    expected_proceeds = expected_quantity * 110 * .99 * .99
    assert result["metrics"]["final_usd"] == pytest.approx(expected_proceeds)
    assert result["fills"][0]["quantity"] == pytest.approx(expected_quantity)
    assert result["metrics"]["terminal_exits"] == 1
    assert result["curve"][-1]["btc"] == 0
    assert result["curve"][-1]["cash"] == pytest.approx(expected_proceeds)
    assert result["metrics"]["net_profit_usd"] == pytest.approx(sum(t["pnl_usd"] for t in result["trades"]))


def test_flat_market_costs_create_drawdown_from_initial_balance():
    frame = frame_for([100.] * 203)
    result = simulate(frame, *bounds(frame), strategy="buy_hold", fee_bps=100, slippage_bps=0)
    expected_loss = 100 * (1 - .99 / 1.01)
    assert result["metrics"]["max_close_drawdown_pct"] == pytest.approx(expected_loss)
    assert result["metrics"]["net_return_pct"] == pytest.approx(-expected_loss)


def test_future_prices_do_not_change_a_fixed_period():
    frame = frame_for([100.] * 200 + [110., 115., 120., 125., 130.])
    start, end = bounds(frame)
    before = simulate(frame, start, end)
    future = frame.iloc[-1:].copy()
    future.Date += pd.Timedelta(days=1)
    future[["Open", "High", "Low", "Close"]] = 1_000_000
    after = simulate(pd.concat([frame, future], ignore_index=True), start, end)
    assert before == after


def test_cash_stays_cash_and_has_no_trades_or_fees():
    frame = frame_for([100.] * 200 + [150., 50., 250.])
    result = simulate(frame, *bounds(frame), strategy="cash")
    assert result["fills"] == result["trades"] == []
    assert result["metrics"]["final_usd"] == 10000
    assert result["metrics"]["fees_paid_usd"] == 0


def test_warmup_cannot_be_included_in_performance():
    frame = frame_for([100.] * 202)
    with pytest.raises(ValueError, match="200 completed"):
        simulate(frame, *bounds(frame, 199))
    assert len(simulate(frame, *bounds(frame))["curve"]) == 2


@pytest.mark.parametrize("cost", [-1, math.nan, math.inf, 10000])
def test_invalid_cost_rejected(cost):
    frame = frame_for([100.] * 203)
    with pytest.raises(ValueError):
        simulate(frame, *bounds(frame), fee_bps=cost)


@pytest.mark.parametrize("bad", ["gap", "duplicate", "nonfinite", "invalid_high", "negative_volume"])
def test_bad_candles_rejected(tmp_path, bad):
    frame = frame_for([100.] * 203)
    if bad == "gap":
        frame = frame.drop(10)
    elif bad == "duplicate":
        frame.loc[10, "Date"] = frame.loc[9, "Date"]
    elif bad == "nonfinite":
        frame.loc[10, "Close"] = math.inf
    elif bad == "invalid_high":
        frame.loc[10, "High"] = 50
    else:
        frame.loc[10, "Volume"] = -1
    path = tmp_path / "data.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_daily(path)


def test_cash_ledger_matches_independent_return_recurrence():
    rng = np.random.default_rng(103)
    closes = 100 * np.exp(np.cumsum(rng.normal(.001, .025, 900)))
    opens = np.r_[closes[0], closes[:-1]] * np.exp(rng.normal(0, .003, 900))
    frame = frame_for(closes, opens)
    result = simulate(frame, *bounds(frame), fee_bps=60, slippage_bps=10)
    assert len(result["trades"]) >= 3
    fee, slip = .006, .001
    wealth, holding = 10000., False
    reference_curve = []
    # Independent scalar wealth accounting and direct trailing slices. This
    # does not reuse the production features or quantity/cash transaction code.
    for i in range(200, len(frame)):
        j = i - 1
        mean200 = float(np.mean(closes[j - 199:j + 1]))
        enter = closes[j] > mean200 and closes[j] > float(frame.High.iloc[j - 20:j].max())
        leave = closes[j] < mean200 or closes[j] < float(frame.Low.iloc[j - 10:j].min())
        if holding:
            wealth *= opens[i] / closes[i - 1]
        if holding and leave:
            wealth *= (1 - slip) * (1 - fee)
            holding = False
        elif not holding and enter:
            wealth /= (1 + slip) * (1 + fee)
            holding = True
        if holding:
            wealth *= closes[i] / opens[i]
        if i == len(frame) - 1 and holding:
            wealth *= (1 - slip) * (1 - fee)
        reference_curve.append(wealth)
    np.testing.assert_allclose([p["equity"] for p in result["curve"]], reference_curve, rtol=1e-11)


def test_higher_cost_reduces_return_without_changing_signals():
    closes = 100 * np.exp(np.cumsum(np.random.default_rng(19).normal(.002, .03, 800)))
    frame = frame_for(closes)
    zero = simulate(frame, *bounds(frame), fee_bps=0, slippage_bps=0)
    costly = simulate(frame, *bounds(frame), fee_bps=120, slippage_bps=25)
    assert zero["metrics"]["final_usd"] > costly["metrics"]["final_usd"]
    assert [(f["date"], f["side"]) for f in zero["fills"]] == [(f["date"], f["side"]) for f in costly["fills"]]


def test_changed_rule_description_cannot_mislabel_implemented_strategy(tmp_path):
    original = Path(__file__).parents[1] / "docs/TREND_BACKTEST_PROTOCOL.json"
    altered = tmp_path / "altered.json"
    altered.write_text(original.read_text().replace("SMA200", "SMA50"))
    with pytest.raises(ValueError, match="frozen implemented"):
        run_experiment(tmp_path / "unused.csv", altered, tmp_path / "rejected")
