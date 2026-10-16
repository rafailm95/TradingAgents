"""Experiment 007: twelve frozen families, using the unchanged research ledger.

No provider calls, credentials, order APIs or paper-campaign modifications.
Definitions and research limitations: docs/STRATEGY_FAMILIES_PROTOCOL.json.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from tradingagents import strategy_lab as legacy

FAMILIES = ("kama_trend", "keltner_breakout", "adx_directional", "ichimoku_trend",
            "aroon_trend", "regression_trend", "cmo_momentum", "stochastic_pullback",
            "cci_reversion", "squeeze_breakout", "obv_breakout", "cmf_trend")
SIZINGS = legacy.SIZINGS


@dataclass(frozen=True)
class Candidate:
    family: str
    sizing: str

    def __post_init__(self):
        if self.family not in FAMILIES or self.sizing not in SIZINGS:
            raise ValueError("Unsupported experiment007 candidate")

    @property
    def id(self):
        return f"{self.family}__{self.sizing}"


CANDIDATES = tuple(Candidate(f, s) for f in FAMILIES for s in SIZINGS)


def rma(series, n):
    """Wilder recursion; first n consecutive finite samples form the seed."""
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    seed, previous = [], math.nan
    for i, value in enumerate(values):
        if not math.isfinite(value):
            seed, previous = [], math.nan
        elif math.isfinite(previous):
            previous = (previous * (n - 1) + value) / n
            out[i] = previous
        else:
            seed.append(value)
            if len(seed) == n:
                previous = float(np.mean(seed))
                out[i] = previous
    return pd.Series(out, index=series.index)


def neutral_ratio(numerator, denominator, neutral):
    """Preserve warmup NaNs; use neutral only for an observed zero divisor."""
    return (numerator / denominator.replace(0, np.nan)).where(denominator != 0, neutral)


def indicators(frame):
    """Explicit causal indicator definitions; no backfilled or centered windows."""
    c, h, l, v = frame.Close, frame.High, frame.Low, frame.Volume
    diff = c.diff()
    sma200, sma100, sma50, sma20 = (c.rolling(n).mean() for n in (200, 100, 50, 20))
    ema20 = c.ewm(span=20, adjust=False).mean()
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr14, atr20 = rma(tr, 14), rma(tr, 20)
    er = neutral_ratio((c-c.shift(10)).abs(), diff.abs().rolling(10).sum(), 0.)
    sc = (er * (2/3 - 2/31) + 2/31) ** 2
    kama_values = np.full(len(c), np.nan)
    if len(c) >= 10:
        kama_values[9] = c.iloc[:10].mean()
    for i in range(10, len(c)):
        kama_values[i] = kama_values[i-1] + sc.iloc[i] * (c.iloc[i]-kama_values[i-1])
    kama = pd.Series(kama_values, index=c.index)
    up, down = h.diff(), -l.diff()
    plus = up.where((up > down) & (up > 0), 0.)
    minus = down.where((down > up) & (down > 0), 0.)
    plus_di = 100 * neutral_ratio(rma(plus, 14), atr14, 0.)
    minus_di = 100 * neutral_ratio(rma(minus, 14), atr14, 0.)
    dx = 100 * neutral_ratio((plus_di-minus_di).abs(), plus_di+minus_di, 0.)
    adx = rma(dx, 14)
    tenkan = (h.rolling(9).max()+l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max()+l.rolling(26).min()) / 2
    cloud_a = ((tenkan+kijun)/2).shift(26)
    cloud_b = ((h.rolling(52).max()+l.rolling(52).min())/2).shift(26)
    # Reverse the window so ties select the most recent extremum.
    aroon_up = h.rolling(26).apply(lambda a: 100*(25-np.argmax(a[::-1]))/25, raw=True)
    aroon_down = l.rolling(26).apply(lambda a: 100*(25-np.argmin(a[::-1]))/25, raw=True)
    x = np.arange(60, dtype=float) - 29.5
    xx = float(x @ x)

    def slope(a):
        return float(x @ (a-a.mean()) / xx)

    def r_squared(a):
        y = a-a.mean()
        yy = float(y @ y)
        return min(1., max(0., float((x@y)**2 / (xx*yy)))) if yy > 1e-25 else 0.

    logc = np.log(c)
    log_slope = logc.rolling(60).apply(slope, raw=True)
    log_r2 = logc.rolling(60).apply(r_squared, raw=True)
    gains, losses = diff.clip(lower=0).rolling(20).sum(), (-diff.clip(upper=0)).rolling(20).sum()
    cmo = 100 * neutral_ratio(gains-losses, gains+losses, 0.)
    high14, low14 = h.rolling(14).max(), l.rolling(14).min()
    raw_k = neutral_ratio(100*(c-low14), high14-low14, 50.)
    slow_k = raw_k.rolling(3).mean()
    stoch_d = slow_k.rolling(3).mean()
    typical = (h+l+c)/3
    mad = typical.rolling(20).apply(lambda a: np.abs(a-a.mean()).mean(), raw=True)
    cci = neutral_ratio(typical-typical.rolling(20).mean(), .015*mad, 0.)
    width = 4*c.rolling(20).std(ddof=0)/sma20
    compressed = width <= width.shift().rolling(120).median()
    recent_compression = compressed.shift().rolling(5).max() == 1
    obv = (np.sign(diff).fillna(0)*v).cumsum()
    multiplier = neutral_ratio(2*c-h-l, h-l, 0.)
    cmf = neutral_ratio((multiplier*v).rolling(20).sum(), v.rolling(20).sum(), 0.)
    return pd.DataFrame({"sma200":sma200, "sma100":sma100, "sma50":sma50, "sma20":sma20,
        "ema20":ema20, "atr20":atr20, "kama":kama, "adx":adx, "plus_di":plus_di,
        "minus_di":minus_di, "tenkan":tenkan, "kijun":kijun, "cloud_a":cloud_a,
        "cloud_b":cloud_b, "aroon_up":aroon_up, "aroon_down":aroon_down,
        "log_slope":log_slope, "log_r2":log_r2, "cmo":cmo, "slow_k":slow_k,
        "stoch_d":stoch_d, "cci":cci, "recent_compression":recent_compression,
        "obv":obv, "cmf":cmf,
        "vol60":c.pct_change(fill_method=None).rolling(60).std(ddof=1)*math.sqrt(365.25)})


def signals(frame, family, *, prepared_indicators=None):
    if family not in FAMILIES:
        raise ValueError("Unknown experiment007 family")
    z = indicators(frame) if prepared_indicators is None else prepared_indicators
    if not z.index.equals(frame.index) or len(z) != len(frame):
        raise ValueError("Indicator index mismatch")
    c = frame.Close
    trend = c > z.sma200
    downtrend = c < z.sma200
    max_hold = 0
    if family == "kama_trend":
        enter = (c > z.kama) & (z.kama > z.kama.shift(5)) & trend
        leave = (c < z.kama) | downtrend
    elif family == "keltner_breakout":
        enter = (c > z.ema20+2*z.atr20) & trend
        leave = (c < z.ema20) | downtrend
    elif family == "adx_directional":
        enter = (z.adx > 25) & (z.plus_di > z.minus_di) & trend
        leave = (z.plus_di < z.minus_di) | (z.adx < 20) | downtrend
    elif family == "ichimoku_trend":
        top = np.maximum(z.cloud_a, z.cloud_b)
        bottom = np.minimum(z.cloud_a, z.cloud_b)
        enter = (c > top) & (z.tenkan > z.kijun)
        leave = (c < bottom) | (z.tenkan < z.kijun)
    elif family == "aroon_trend":
        enter = (z.aroon_up > 70) & (z.aroon_down < 30) & trend
        leave = (z.aroon_up < z.aroon_down) | downtrend
    elif family == "regression_trend":
        enter = (z.log_slope > 0) & (z.log_r2 >= .30) & trend
        leave = (z.log_slope <= 0) | (c < z.sma100)
    elif family == "cmo_momentum":
        enter = (z.cmo > 30) & trend
        leave = (z.cmo < 0) | downtrend
    elif family == "stochastic_pullback":
        enter = (z.slow_k > z.stoch_d) & (z.slow_k.shift() <= z.stoch_d.shift()) & (z.slow_k < 30) & trend
        leave = (z.slow_k > 80) | downtrend
        max_hold = 10
    elif family == "cci_reversion":
        enter = (z.cci < -100) & trend
        leave = (z.cci >= 0) | downtrend
        max_hold = 20
    elif family == "squeeze_breakout":
        enter = z.recent_compression & (c > frame.High.rolling(20).max().shift()) & trend
        leave = (c < z.sma20) | downtrend
    elif family == "obv_breakout":
        enter = (z.obv > z.obv.rolling(20).max().shift()) & (c > c.rolling(20).max().shift()) & trend
        leave = (z.obv < z.obv.rolling(20).mean()) | downtrend
    else:
        enter = (z.cmf > .10) & (c > z.sma50) & trend
        leave = (z.cmf < 0) | (c < z.sma50) | downtrend
    return pd.DataFrame({"entry":enter.fillna(False) & ~leave.fillna(False),
        "exit":leave.fillna(False), "vol60":z.vol60, "max_hold":max_hold})


def simulate(frame, start, end, candidate, *, extra_signal_lag=0, prepared=None, **kwargs):
    """Adapt fully prepared features to the frozen ledger; legacy family is unused.

    Lag affects signal conditions and sizing inputs; scheduled holding-time and
    terminal exits keep their original clock. This is not an order queue model.
    """
    if not isinstance(candidate, Candidate):
        raise ValueError("Expected experiment007 Candidate")
    if type(extra_signal_lag) is not int or extra_signal_lag not in (0, 1, 2):
        raise ValueError("Frozen extra signal lags are 0,1,2")
    sig = signals(frame, candidate.family) if prepared is None else prepared.copy()
    if not sig.index.equals(frame.index) or len(sig) != len(frame):
        raise ValueError("Signal index mismatch")
    if list(sig.columns) != ["entry", "exit", "vol60", "max_hold"]:
        raise ValueError("Unexpected signal columns")
    if any(sig[k].dtype != bool or sig[k].isna().any() for k in ("entry", "exit")):
        raise ValueError("Signals must be complete booleans")
    if (sig.entry & sig.exit).any():
        raise ValueError("Conflicting entry/exit conditions")
    if not np.isfinite(sig.max_hold).all() or not sig.max_hold.isin([0, 10, 20]).all():
        raise ValueError("Invalid holding limit")
    if extra_signal_lag:
        for key in ("entry", "exit"):
            sig[key] = sig[key].shift(extra_signal_lag, fill_value=False)
        sig["vol60"] = sig.vol60.shift(extra_signal_lag)
    carrier = legacy.Candidate("breakout20", candidate.sizing)
    result = legacy.simulate(frame, start, end, carrier, prepared=sig, **kwargs)
    for fill in result["fills"]:
        if fill["reason"] in {"entry", "signal"}:
            original = pd.Timestamp(fill["signal_date"]) - pd.Timedelta(days=extra_signal_lag)
            fill["signal_date"] = original.strftime("%Y-%m-%d")
        elif fill["reason"] == "time_exit":
            fill["signal_date"] = None
    result["candidate_id"] = candidate.id
    result["extra_signal_lag"] = extra_signal_lag
    return result


def select_candidate(training):
    ranked = []
    if set(training) != {c.id for c in CANDIDATES}:
        raise ValueError("Training universe must contain all24 frozen candidates")
    for candidate in CANDIDATES:
        pair = [training[candidate.id][cost] for cost in ("base", "stress")]
        if all(m["profit_after_operating_usd"] > 0 and m["max_close_drawdown_pct"] <= 35
               and m["closed_trades"] >= 10 for m in pair):
            m = pair[1]
            ranked.append({"id":candidate.id, "score":m["annualized_after_operating_pct"] / max(m["max_close_drawdown_pct"], 1.)})
    ranked.sort(key=lambda row: (-row["score"], row["id"]))
    return {"selected":ranked[0]["id"] if ranked else "cash", "eligible":ranked}
