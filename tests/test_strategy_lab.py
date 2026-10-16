"""Causality, ledger conservation, signal oracles and selection constraints."""
import math

import numpy as np
import pandas as pd
import pytest

from tradingagents.strategy_lab import (CANDIDATES, FAMILIES, Candidate, allocation,
    audit_wealth, bootstrap_max_mean, select_candidate, signals, simulate)
from tradingagents.strategy_backtest import simulate as original
from tests.test_strategy_backtest import frame_for, bounds


def sample():
    rng = np.random.default_rng(108)
    c = 100 * np.exp(np.cumsum(rng.normal(.0006, .035, 950)))
    o = np.r_[c[0], c[:-1]] * np.exp(rng.normal(0, .005, len(c)))
    return frame_for(c, o)


@pytest.mark.parametrize("family", FAMILIES)
def test_future_perturbation_does_not_change_signal_prefix(family):
    frame = sample()
    prefix = signals(frame.iloc[:500], family)
    mutated = frame.copy()
    mutated.loc[500:, ["Open", "High", "Low", "Close"]] *= 1000
    pd.testing.assert_frame_equal(prefix, signals(mutated, family).iloc[:500])


@pytest.mark.parametrize("candidate", CANDIDATES, ids=lambda c:c.id)
def test_portfolio_recurrence_all_families_and_cost_monotonicity(candidate):
    frame = sample()
    cheap = simulate(frame, *bounds(frame), candidate, fee_bps=10, slippage_bps=5)
    costly = simulate(frame, *bounds(frame), candidate, fee_bps=120, slippage_bps=25)
    audit_wealth(frame, costly, 10000, 120, 25)
    assert cheap["metrics"]["final_usd"] >= costly["metrics"]["final_usd"]
    assert [(f["date"], f["side"]) for f in cheap["fills"]] == [(f["date"], f["side"]) for f in costly["fills"]]
    for fill in costly["fills"]:
        if fill["signal_date"]:
            assert pd.Timestamp(fill["date"]) - pd.Timestamp(fill["signal_date"]) == pd.Timedelta(days=1)
        if fill["side"] == "buy":
            assert 0 < fill["fraction"] <= .5


def test_volatility_sizing_uses_signal_day_not_execution_day():
    frame = frame_for([100.] * 200 + [110., 115., 120.])
    modified = frame.copy()
    modified.loc[201, "Close"] = 1000
    modified.loc[201, "High"] = 1001
    c = Candidate("breakout20", "vol15_cap50")
    before, after = [simulate(f, *bounds(f), c) for f in (frame, modified)]
    assert before["fills"][0] == after["fills"][0]
    vol = np.std(np.diff(frame.Close.iloc[140:201]) / frame.Close.iloc[140:200], ddof=1) * math.sqrt(365.25)
    assert before["fills"][0]["fraction"] == pytest.approx(min(.5, .15 / vol))


def test_buy_hold_partial_position_costs_hand_oracle():
    frame = frame_for([100.] * 200 + [110., 130.], [100.] * 202)
    result = simulate(frame, *bounds(frame), benchmark="buy_hold50", fee_bps=100, slippage_bps=100)
    expected = 5000 + 5000 / (100 * 1.01 * 1.01) * 130 * .99 * .99
    assert result["metrics"]["final_usd"] == pytest.approx(expected)
    assert result["curve"][-1]["btc"] == 0


@pytest.mark.parametrize("fraction", [.5, 1.])
def test_legacy_strategy_daily_equity_parity(fraction):
    frame = sample()
    new = simulate(frame, *bounds(frame), Candidate("breakout20", "fixed50") if fraction == .5 else None,
                   benchmark="original_trend100" if fraction == 1 else None)
    old = original(frame, *bounds(frame), allocation_fraction=fraction)
    np.testing.assert_allclose([r["equity"] for r in new["curve"]], [r["equity"] for r in old["curve"]], rtol=1e-12)


def test_rsi_flat_market_is_neutral_and_time_exit_waits_full_bars():
    frame = frame_for([100.] * 230)
    assert not signals(frame, "rsi2_pullback").entry.any()
    prepared = signals(frame, "rsi2_pullback")
    prepared["entry"] = False
    prepared["exit"] = False
    prepared.loc[200, "entry"] = True
    result = simulate(frame, *bounds(frame), Candidate("rsi2_pullback", "fixed50"), prepared=prepared)
    assert result["trades"][0]["reason"] == "time_exit"
    assert pd.Timestamp(result["trades"][0]["exit_date"]) - pd.Timestamp(result["trades"][0]["entry_date"]) == pd.Timedelta(days=10)


def test_signal_conditions_against_direct_slices_and_ema_recursion():
    frame = sample()
    c, high, low = frame.Close.to_numpy(), frame.High.to_numpy(), frame.Low.to_numpy()
    ema12 = ema26 = c[0]
    signal = 0.
    cache = {f:signals(frame,f) for f in FAMILIES}
    for i in range(1, len(c)):
        ema12 += 2/13 * (c[i] - ema12)
        ema26 += 2/27 * (c[i] - ema26)
        macd = ema12 - ema26
        signal += .2 * (macd - signal)
        if i < 200:
            continue
        sma200, sma20 = c[i-199:i+1].mean(), c[i-19:i+1].mean()
        diff = np.diff(c[i-2:i+1])
        up, down = np.maximum(diff,0).sum(), np.maximum(-diff,0).sum()
        rsi = 100*up/(up+down) if up+down else 50
        expected = {
            "breakout20": (c[i]>sma200 and c[i]>high[i-20:i].max(), c[i]<sma200 or c[i]<low[i-10:i].min()),
            "breakout55": (c[i]>sma200 and c[i]>high[i-55:i].max(), c[i]<sma200 or c[i]<low[i-20:i].min()),
            "sma200_band": (c[i]>1.01*sma200, c[i]<.99*sma200),
            "sma50_200": (c[i-49:i+1].mean()>sma200, c[i-49:i+1].mean()<sma200),
            "momentum90": (c[i]>c[i-90], c[i]<c[i-90]),
            "rsi2_pullback": (c[i]>sma200 and rsi<10, c[i]>c[i-4:i+1].mean() or c[i]<sma200),
            "bollinger20": (c[i]<sma20-2*c[i-19:i+1].std(ddof=0), c[i]>=sma20),
            "macd_trend": (macd>signal and c[i]>sma200, macd<signal or c[i]<sma200)}
        for family, (enter, leave) in expected.items():
            assert bool(cache[family].entry.iloc[i]) == bool(enter)
            assert bool(cache[family].exit.iloc[i]) == bool(leave)


def training_fixture():
    return {c.id: {cost:{"profit_after_operating_usd":100., "max_close_drawdown_pct":20.,
                        "closed_trades":10,"annualized_after_operating_pct":5.} for cost in ("base","stress")} for c in CANDIDATES}


def test_selector_constraints_and_deterministic_tie():
    training = training_fixture()
    assert select_candidate(training)["selected"] == min(training)
    for pair in training.values():
        pair["stress"]["max_close_drawdown_pct"] = 36
    assert select_candidate(training)["selected"] == "cash"
    candidate = CANDIDATES[0].id
    training[candidate]["stress"]["max_close_drawdown_pct"] = 20
    training[candidate]["base"]["closed_trades"] = 9
    assert select_candidate(training)["selected"] == "cash"


def test_bootstrap_shared_date_resampling_null_and_clear_excess():
    zeros = np.zeros((100, 3))
    assert bootstrap_max_mean(zeros, np.zeros(100), repeats=100)["family_adjusted_p_exploratory"] == 1
    positive = np.full((100, 3), .001)
    assert bootstrap_max_mean(positive, np.zeros(100), repeats=100)["family_adjusted_p_exploratory"] == pytest.approx(1/101)


@pytest.mark.parametrize("vol", [math.nan, math.inf, -1])
def test_bad_volatility_fails_closed(vol):
    with pytest.raises(ValueError):
        allocation("vol15_cap50", vol)


def test_warmup_bounds_and_cost_guards():
    frame = sample()
    with pytest.raises(ValueError):
        simulate(frame, *bounds(frame, 199), CANDIDATES[0])
    with pytest.raises(ValueError):
        simulate(frame, *bounds(frame), CANDIDATES[0], fee_bps=-1)
    with pytest.raises(ValueError):
        simulate(frame, *bounds(frame), CANDIDATES[0], benchmark="cash")
