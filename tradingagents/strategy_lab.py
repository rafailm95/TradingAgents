"""Bounded BTC strategy research. Pure calculation; no credentials or order APIs."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

FAMILIES = ("breakout20", "breakout55", "sma200_band", "sma50_200",
            "momentum90", "rsi2_pullback", "bollinger20", "macd_trend")
SIZINGS = ("fixed50", "vol15_cap50")


@dataclass(frozen=True)
class Candidate:
    family: str
    sizing: str

    def __post_init__(self):
        if self.family not in FAMILIES or self.sizing not in SIZINGS:
            raise ValueError("Unsupported frozen candidate")

    @property
    def id(self):
        return f"{self.family}__{self.sizing}"


CANDIDATES = tuple(Candidate(f, s) for f in FAMILIES for s in SIZINGS)


def signals(frame, family):
    """All row t features consume only observations at or before t."""
    if family not in FAMILIES:
        raise ValueError("Unknown family")
    c = frame.Close
    sma200 = c.rolling(200, min_periods=200).mean()
    sma20 = c.rolling(20, min_periods=20).mean()
    vol = c.pct_change(fill_method=None).rolling(60, min_periods=60).std(ddof=1) * math.sqrt(365.25)
    max_hold = 0
    if family in {"breakout20", "breakout55"}:
        high_n, low_n = (20, 10) if family == "breakout20" else (55, 20)
        enter = (c > sma200) & (c > frame.High.rolling(high_n).max().shift(1))
        leave = (c < sma200) | (c < frame.Low.rolling(low_n).min().shift(1))
    elif family == "sma200_band":
        enter, leave = c > 1.01 * sma200, c < .99 * sma200
    elif family == "sma50_200":
        mean50 = c.rolling(50, min_periods=50).mean()
        enter, leave = mean50 > sma200, mean50 < sma200
    elif family == "momentum90":
        enter, leave = c > c.shift(90), c < c.shift(90)
    elif family == "rsi2_pullback":
        change = c.diff()
        up = change.clip(lower=0).rolling(2, min_periods=2).mean()
        down = (-change.clip(upper=0)).rolling(2, min_periods=2).mean()
        total = up + down
        rsi = (100 * up / total).where(total != 0, 50)
        enter = (c > sma200) & (rsi < 10)
        leave = (c > c.rolling(5).mean()) | (c < sma200)
        max_hold = 10
    elif family == "bollinger20":
        enter = c < sma20 - 2 * c.rolling(20).std(ddof=0)
        leave = c >= sma20
        max_hold = 20
    else:
        macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        enter = (macd > macd_signal) & (c > sma200)
        leave = (macd < macd_signal) | (c < sma200)
    return pd.DataFrame({"entry": enter.fillna(False), "exit": leave.fillna(False),
                         "vol60": vol, "max_hold": max_hold})


def allocation(sizing, vol):
    if sizing == "fixed50":
        return .5
    if sizing != "vol15_cap50" or not math.isfinite(vol) or vol < 0:
        raise ValueError("Missing or invalid sizing volatility")
    return min(.5, .15 / vol) if vol > 0 else .5


def performance(curve, initial, fills, trades, operating_per_year=120):
    equity = np.array([initial] + [r["equity"] for r in curve], dtype=float)
    returns = equity[1:] / equity[:-1] - 1
    dd = 1 - equity / np.maximum.accumulate(equity)
    days = len(curve)
    operating = operating_per_year * days / 365.25
    final = float(equity[-1])
    after = final - operating
    return {
        "initial_usd": initial, "days": days, "final_usd": final,
        "net_return_pct": 100 * (final / initial - 1),
        "net_profit_usd": final - initial,
        "annualized_return_pct": 100 * ((final / initial) ** (365.25 / days) - 1),
        "max_close_drawdown_pct": 100 * float(dd.max()),
        "operating_cost_usd": operating,
        "profit_after_operating_usd": after - initial,
        "return_after_operating_pct": 100 * (after / initial - 1),
        "annualized_after_operating_pct": 100 * ((after / initial) ** (365.25 / days) - 1) if after > 0 else -100.,
        "daily_sharpe_rf_zero": float(returns.mean() / returns.std(ddof=1) * math.sqrt(365.25)) if len(returns) > 1 and returns.std(ddof=1) > 0 else None,
        "closed_trades": len(trades),
        "signal_exits": sum(t["reason"] != "terminal_liquidation" for t in trades),
        "fees_paid_usd": sum(f["fee"] for f in fills),
        "exposure_days_pct": 100 * sum(r["exposed"] for r in curve) / days,
        "max_close_weight_pct": 100 * max(r["weight"] for r in curve),
    }


def simulate(frame, start, end, candidate=None, *, benchmark=None, fee_bps=60,
             slippage_bps=10, initial=10000, operating_per_year=120, prepared=None):
    """Flat start; next-open fills; entry-only sizing; terminal close liquidation.

    frame must come from strategy_backtest.load_daily. prepared is an internal
    optional causal feature cache used only by the bounded research runner.
    """
    if (candidate is None) == (benchmark is None):
        raise ValueError("Supply exactly one candidate or benchmark")
    if candidate is not None and not isinstance(candidate, Candidate):
        raise ValueError("Invalid candidate")
    if benchmark not in {None, "buy_hold50", "buy_hold100", "cash", "original_trend100"}:
        raise ValueError("Unknown benchmark")
    if not math.isfinite(initial) or initial <= 0 or not math.isfinite(operating_per_year) or operating_per_year < 0:
        raise ValueError("Invalid balance or operating cost")
    if any(not math.isfinite(x) or not 0 <= x < 10000 for x in (fee_bps, slippage_bps)):
        raise ValueError("Invalid friction")
    dates = frame.Date
    start_ts, end_ts = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    starts, ends = np.where(dates == start_ts)[0], np.where(dates == end_ts)[0]
    if len(starts) != 1 or len(ends) != 1 or starts[0] > ends[0]:
        raise ValueError("Missing or reversed evaluation bounds")
    first, last = int(starts[0]), int(ends[0])
    if first < 200:
        raise ValueError("Need 200 prior completed candles")
    family = candidate.family if candidate else "breakout20"
    sig = signals(frame.iloc[:last+1], family) if prepared is None else prepared.iloc[:last+1]
    enter, leave = sig.entry.to_numpy(), sig.exit.to_numpy()
    vols, max_holds = sig.vol60.to_numpy(), sig.max_hold.to_numpy()
    opens, closes = frame.Open.to_numpy(), frame.Close.to_numpy()
    day = dates.dt.strftime("%Y-%m-%d").to_numpy()
    fee, slip = fee_bps / 10000, slippage_bps / 10000
    cash, qty, opened, entry_spend = float(initial), 0., -1, 0.
    curve, fills, trades = [], [], []
    entry_date, entry_fraction = None, None

    def buy(i, fraction, signal_date):
        nonlocal cash, qty, opened, entry_spend, entry_date, entry_fraction
        entry_spend = cash * fraction
        price = float(opens[i]) * (1 + slip)
        qty = entry_spend / (price * (1 + fee))
        charge = qty * price * fee
        cash -= entry_spend
        opened, entry_date, entry_fraction = i, day[i], fraction
        fills.append({"date": day[i], "side": "buy", "reference": float(opens[i]),
                      "price": price, "quantity": qty, "fee": charge,
                      "signal_date": signal_date, "fraction": fraction, "cash_after": cash,
                      "reason": "entry"})

    def sell(i, reference, reason, signal_date):
        nonlocal cash, qty
        price = float(reference) * (1 - slip)
        charge = qty * price * fee
        proceeds = qty * price - charge
        cash += proceeds
        fills.append({"date": day[i], "side": "sell", "reference": float(reference),
                      "price": price, "quantity": qty, "fee": charge,
                      "signal_date": signal_date, "cash_after": cash, "reason": reason})
        trades.append({"entry_date": entry_date, "exit_date": day[i],
                       "entry_fraction": entry_fraction, "pnl_usd": proceeds - entry_spend,
                       "exit_cash": cash, "reason": reason})
        qty = 0.

    for i in range(first, last + 1):
        j = i - 1
        if candidate is not None or benchmark == "original_trend100":
            timed = bool(qty > 0 and max_holds[j] > 0 and i - opened >= max_holds[j])
            if qty > 0 and (leave[j] or timed):
                sell(i, opens[i], "time_exit" if timed else "signal", day[j])
            elif qty == 0 and enter[j]:
                fraction = allocation(candidate.sizing, float(vols[j])) if candidate else 1.
                buy(i, fraction, day[j])
        elif benchmark.startswith("buy_hold") and i == first:
            buy(i, .5 if benchmark == "buy_hold50" else 1., None)
        exposed = qty > 0
        if i == last and qty > 0:
            sell(i, closes[i], "terminal_liquidation", None)
        equity = cash + qty * float(closes[i])
        if not math.isfinite(equity) or equity <= 0 or cash < -1e-8 or qty < 0:
            raise ArithmeticError("Invalid portfolio ledger")
        curve.append({"Date": day[i], "equity": equity, "cash": cash, "btc": qty,
                      "weight": qty * float(closes[i]) / equity, "exposed": exposed})
    return {"metrics": performance(curve, initial, fills, trades, operating_per_year),
            "curve": curve, "fills": fills, "trades": trades}


def select_candidate(training):
    """Input is only train results; this function never reads evaluation results."""
    ranked = []
    for candidate in CANDIDATES:
        pair = [training[candidate.id][cost] for cost in ("base", "stress")]
        if all(m["profit_after_operating_usd"] > 0 and m["max_close_drawdown_pct"] <= 35
               and m["closed_trades"] >= 10 for m in pair):
            stress = pair[1]
            score = stress["annualized_after_operating_pct"] / max(stress["max_close_drawdown_pct"], 1.)
            ranked.append({"id": candidate.id, "score": score})
    ranked.sort(key=lambda r: (-r["score"], r["id"]))
    return {"selected": ranked[0]["id"] if ranked else "cash", "eligible": ranked}


def audit_wealth(frame, result, initial, fee_bps, slip_bps):
    """Separate wealth recurrence using prior close exposure, not cash/qty ledger."""
    indexed = frame.set_index(frame.Date.dt.strftime("%Y-%m-%d"))
    fills = {}
    for fill in result["fills"]:
        fills.setdefault(fill["date"], []).append(fill)
    wealth, weight, errors = float(initial), 0., []
    fee, slip = fee_bps / 10000, slip_bps / 10000
    previous_close = None
    for point in result["curve"]:
        row = indexed.loc[point["Date"]]
        cash_value, asset_value = wealth * (1 - weight), wealth * weight
        if previous_close is not None:
            asset_value *= row.Open / previous_close
        terminal = None
        for fill in fills.get(point["Date"], []):
            if fill["reason"] == "terminal_liquidation":
                terminal = fill
            elif fill["side"] == "sell":
                cash_value += asset_value * (1 - slip) * (1 - fee)
                asset_value = 0.
            else:
                spend = cash_value * fill["fraction"]
                cash_value -= spend
                asset_value = spend / ((1 + slip) * (1 + fee))
        asset_value *= row.Close / row.Open
        if terminal is not None:
            cash_value += asset_value * (1 - slip) * (1 - fee)
            asset_value = 0.
        wealth = cash_value + asset_value
        weight = asset_value / wealth
        previous_close = row.Close
        errors.append(abs(wealth - point["equity"]))
    maximum = max(errors, default=0.)
    if maximum > max(1e-7, initial * 1e-10):
        raise AssertionError(f"Wealth recurrence mismatch {maximum}")
    if not math.isclose(sum(t["pnl_usd"] for t in result["trades"]),
                        result["metrics"]["final_usd"] - initial, abs_tol=1e-7):
        raise AssertionError("Closed trade P&L does not reconcile")
    return {"days": len(errors), "max_usd_error": maximum, "status": "PASS"}


def bootstrap_max_mean(panel, benchmark, *, block=30, repeats=2000, seed=20261016):
    """Exploratory max-mean centered circular block test for this candidate set.

    Same date indices for every candidate; arithmetic returns; no studentization.
    Does not correct for previous research, design choices or regime shifts.
    """
    excess = np.asarray(panel) - np.asarray(benchmark)[:, None]
    if excess.ndim != 2 or len(excess) < block or not np.isfinite(excess).all():
        raise ValueError("Invalid aligned return panel")
    means = excess.mean(axis=0)
    observed = max(0., float(means.max()))
    centered = excess - means
    rng = np.random.default_rng(seed)
    n = len(excess)
    exceedances = 0
    for _ in range(repeats):
        starts = rng.integers(0, n, size=math.ceil(n / block))
        indices = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]
        statistic = max(0., float(centered[indices].mean(axis=0).max()))
        exceedances += statistic >= observed
    return {"block_days": block, "resamples": repeats, "seed": seed,
            "max_daily_mean_excess_bps": observed * 10000,
            "family_adjusted_p_exploratory": (1 + exceedances) / (repeats + 1),
            "transaction_costs_included": True, "operating_costs_included": False,
            "prior_research_selection_corrected": False}
