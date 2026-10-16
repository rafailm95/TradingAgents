"""Independent indicator oracles, adversarial causality and wealth conservation."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradingagents import strategy_families as lab
from tradingagents.strategy_lab import audit_wealth
from tests.test_strategy_backtest import frame_for, bounds


def sample(n=800):
    rng = np.random.default_rng(1707)
    close = 100*np.exp(np.cumsum(rng.normal(.0007, .035, n)))
    opens = np.r_[close[0],close[:-1]]*np.exp(rng.normal(0,.008,n))
    f = frame_for(close, opens)
    f["Volume"] = rng.integers(100, 10000, n).astype(float)
    return f


@pytest.fixture(scope="module")
def market():
    f = sample()
    z = lab.indicators(f)
    return f, {family:lab.signals(f, family, prepared_indicators=z) for family in lab.FAMILIES}


def test_indicators_future_prices_and_volume_cannot_rewrite_past():
    f = sample()
    baseline = lab.indicators(f.iloc[:470])
    mutated = f.copy()
    mutated.loc[470:, ["Open","High","Low","Close"]] *= 1000
    mutated.loc[470:, "Volume"] *= 100000
    pd.testing.assert_frame_equal(baseline, lab.indicators(mutated).iloc[:470])


@pytest.mark.parametrize("family", lab.FAMILIES)
def test_every_family_prefix_invariance_and_conflict_exclusion(family, market):
    f, cache = market
    short = lab.signals(f.iloc[:470], family)
    pd.testing.assert_frame_equal(short, cache[family].iloc[:470])
    assert not (cache[family].entry & cache[family].exit).any()


@pytest.mark.parametrize("candidate", lab.CANDIDATES, ids=lambda c:c.id)
def test_costs_and_wealth_and_rule_dates(candidate, market):
    f, cache = market
    cheap = lab.simulate(f, *bounds(f), candidate, prepared=cache[candidate.family], fee_bps=10, slippage_bps=5)
    expensive = lab.simulate(f, *bounds(f), candidate, prepared=cache[candidate.family], fee_bps=120, slippage_bps=25)
    assert cheap["metrics"]["final_usd"] >= expensive["metrics"]["final_usd"]
    assert [(x["date"],x["side"]) for x in cheap["fills"]] == [(x["date"],x["side"]) for x in expensive["fills"]]
    assert expensive["candidate_id"] == candidate.id
    audit_wealth(f, expensive, 10000, 120, 25)
    assert all(p["cash"] >= 0 and p["btc"] >= 0 for p in expensive["curve"])
    for fill in expensive["fills"]:
        if fill["signal_date"]:
            assert pd.Timestamp(fill["date"])-pd.Timestamp(fill["signal_date"]) == pd.Timedelta(days=1)
        if fill["side"] == "buy":
            assert 0 < fill["fraction"] <= .5


def test_wilder_seed_and_recursion_known_values():
    result = lab.rma(pd.Series([np.nan, 2., 4., 6., 9., 12.]), 3)
    np.testing.assert_allclose(result, [np.nan,np.nan,np.nan,4.,17/3,70/9], equal_nan=True)


def test_indicator_hand_oracles_for_linear_market():
    close = np.arange(1., 242.)
    f = frame_for(close, close)
    f["High"], f["Low"], f["Volume"] = close+1, close-.5, 100.
    z = lab.indicators(f)
    # TR is2 on later rows (H - previous close), first TR1.5.
    expected_atr = (1.5+19*2)/20
    for _ in range(20, len(f)):
        expected_atr = (19*expected_atr+2)/20
    assert z.atr20.iloc[-1] == pytest.approx(expected_atr)
    assert z.cmo.iloc[-1] == pytest.approx(100.)
    assert z.adx.iloc[-1] == pytest.approx(100.)
    assert z.aroon_up.iloc[-1] == 100
    assert z.aroon_down.iloc[-1] == 0
    # Current close minus20-bar typical-price mean =9.5; MAD=5.
    assert z.cci.iloc[-1] == pytest.approx(9.5/(.015*5))
    assert z.cmf.iloc[-1] == pytest.approx(-1/3)
    assert z.obv.iloc[-1] == 24000
    assert z.slow_k.iloc[-1] == pytest.approx(100*13.5/14.5)
    t = len(f)-1-26
    tenkan = ((close[t]+1)+(close[t-8]-.5))/2
    kijun = ((close[t]+1)+(close[t-25]-.5))/2
    assert z.cloud_a.iloc[-1] == pytest.approx((tenkan+kijun)/2)
    assert z.cloud_b.iloc[-1] == pytest.approx(((close[t]+1)+(close[t-51]-.5))/2)
    # With efficiency ratio1 and fast smoothing(2/3)^2, solve recursion directly.
    expected = 5.5
    for value in close[10:]:
        expected = (5/9)*expected+(4/9)*value
    assert z.kama.iloc[-1] == pytest.approx(expected)


def test_regression_matches_closed_form_exponential():
    c = 100*np.exp(.012*np.arange(240))
    z = lab.indicators(frame_for(c,c))
    assert z.log_slope.iloc[-1] == pytest.approx(.012)
    assert z.log_r2.iloc[-1] == pytest.approx(1.)


def test_cci_against_independent_window_values_and_volume_ties():
    f = sample()
    z = lab.indicators(f)
    for i in (230,451,799):
        window = f.iloc[i-19:i+1]
        typical = [(r.High+r.Low+r.Close)/3 for r in window.itertuples()]
        mean = sum(typical)/20
        mad = sum(abs(t-mean) for t in typical)/20
        assert z.cci.iloc[i] == pytest.approx((typical[-1]-mean)/(.015*mad))
        coefficient = np.polyfit(np.arange(60), np.log(f.Close.iloc[i-59:i+1]), 1)
        assert z.log_slope.iloc[i] == pytest.approx(coefficient[0], abs=1e-12)
    f.loc[400, "Close"] = f.loc[399,"Close"]
    f.loc[400,"High"] = max(f.loc[400,"High"], f.loc[400,"Close"])
    f.loc[400,"Low"] = min(f.loc[400,"Low"], f.loc[400,"Close"])
    modified = lab.indicators(f)
    assert modified.obv.iloc[400] == modified.obv.iloc[399]


def test_flat_zero_volume_market_is_finite_neutral_and_generates_no_entries():
    f = frame_for([100.]*260, [100.]*260)
    f[["High","Low"]] = 100.
    f["Volume"] = 0.
    z = lab.indicators(f)
    assert np.isfinite(z.iloc[200:].to_numpy(dtype=float)).all()
    for key in ("cmo","cci","cmf","adx","log_r2"):
        assert z[key].iloc[-1] == pytest.approx(0.)
    assert z.slow_k.iloc[-1] == 50
    assert z.aroon_up.iloc[-1] == z.aroon_down.iloc[-1] == 100
    for family in lab.FAMILIES:
        assert not lab.signals(f, family, prepared_indicators=z).entry.any()


@pytest.mark.parametrize("lag", [0,1,2])
def test_lag_moves_signal_price_and_sizing_together_with_hand_ledger(lag):
    close = np.array([100.]*200 + [105.,110.,115.,120.,125.,130.,135.,140.,145.,150.])
    f = frame_for(close, close)
    sig = pd.DataFrame({"entry":False,"exit":False,"vol60":3.,"max_hold":0}, index=f.index)
    sig.loc[200,"entry"], sig.loc[203,"exit"] = True, True
    sig.loc[200,"vol60"] = .6
    result = lab.simulate(f, *bounds(f), lab.Candidate("kama_trend","vol15_cap50"),
        prepared=sig, extra_signal_lag=lag, fee_bps=100, slippage_bps=100, operating_per_year=0)
    buy, sell = result["fills"]
    assert buy["fraction"] == pytest.approx(.25)
    assert buy["date"] == f.Date.iloc[201+lag].strftime("%Y-%m-%d")
    assert sell["date"] == f.Date.iloc[204+lag].strftime("%Y-%m-%d")
    assert buy["signal_date"] == f.Date.iloc[200].strftime("%Y-%m-%d")
    expected = 7500+2500/(close[201+lag]*1.01*1.01)*close[204+lag]*.99*.99
    assert result["metrics"]["final_usd"] == pytest.approx(expected)
    audit_wealth(f, result, 10000, 100, 100)


def test_timed_exit_uses_actual_entry_clock_even_with_signal_lag():
    f = frame_for([100.]*240)
    sig = pd.DataFrame({"entry":False,"exit":False,"vol60":.6,"max_hold":10},index=f.index)
    sig.loc[200,"entry"] = True
    result = lab.simulate(f, *bounds(f),lab.Candidate("stochastic_pullback","fixed50"),prepared=sig,extra_signal_lag=2)
    buy,sell = result["fills"]
    assert pd.Timestamp(sell["date"])-pd.Timestamp(buy["date"]) == pd.Timedelta(days=10)
    assert sell["reason"] == "time_exit" and sell["signal_date"] is None


def test_held_terminal_position_liquidated_with_both_costs():
    f = frame_for([100.]*205)
    sig = pd.DataFrame({"entry":False,"exit":False,"vol60":.6,"max_hold":0},index=f.index)
    sig.loc[203,"entry"] = True
    result = lab.simulate(f, *bounds(f), lab.Candidate("kama_trend","fixed50"), prepared=sig, fee_bps=100, slippage_bps=100)
    assert result["fills"][-1]["reason"] == "terminal_liquidation"
    assert result["metrics"]["final_usd"] == pytest.approx(5000+5000*.99**2/1.01**2)


def test_selector_refuses_missing_universe_and_enforces_stress_trade_threshold():
    training = {c.id:{cost:{"profit_after_operating_usd":100.,"max_close_drawdown_pct":20.,
        "closed_trades":10,"annualized_after_operating_pct":5.} for cost in ("base","stress")} for c in lab.CANDIDATES}
    assert lab.select_candidate(training)["selected"] == min(training)
    for pair in training.values():
        pair["stress"]["closed_trades"] = 9
    assert lab.select_candidate(training)["selected"] == "cash"
    with pytest.raises(ValueError):
        lab.select_candidate({})


@pytest.mark.parametrize("lag", [-1,3,True,1.5])
def test_reject_unregistered_delays(lag,market):
    f,cache = market
    with pytest.raises(ValueError):
        lab.simulate(f,*bounds(f),lab.CANDIDATES[0],prepared=cache[lab.CANDIDATES[0].family],extra_signal_lag=lag)


def test_reject_bad_cached_signals(market):
    f,cache = market
    sig = cache[lab.CANDIDATES[0].family].copy()
    sig.loc[230,["entry","exit"]] = True
    with pytest.raises(ValueError):
        lab.simulate(f,*bounds(f),lab.CANDIDATES[0],prepared=sig)
    with pytest.raises(ValueError):
        lab.simulate(f,*bounds(f),lab.CANDIDATES[0],prepared=sig.iloc[1:])


def test_existing_campaign_sources_and_protocol_remain_frozen():
    repo = Path(__file__).resolve().parents[1]
    frozen = json.loads((repo/"docs/PAPER_AUTOMATION_RUNTIME.json").read_text())
    for name, expected in frozen["source_files"].items():
        assert hashlib.sha256((repo/name).read_bytes()).hexdigest() == expected
    from scripts.run_strategy_families import PROTOCOL_SHA256
    assert hashlib.sha256((repo/"docs/STRATEGY_FAMILIES_PROTOCOL.json").read_bytes()).hexdigest() == PROTOCOL_SHA256
