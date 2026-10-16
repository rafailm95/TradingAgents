"""Deterministic long/cash portfolio experiment, separate from rating backtests.

Frozen SMA200 / prior-20-day-high entry / prior-10-day-low exit rules.
No model calls, optimization, credentials or order placement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

PROTOCOL_SHA256 = "9e6baf0fe5e1cae4857263677976eb684ad3f2f8550867df83b715b20b5964ba"


def load_daily(path):
    frame = pd.read_csv(path)
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    if any(column not in frame for column in required):
        raise ValueError("Missing daily OHLCV columns")
    frame = frame[required].copy()
    frame.Date = pd.to_datetime(frame.Date, utc=True, errors="raise")
    if (frame.empty or frame.Date.isna().any() or not frame.Date.is_unique
            or not frame.Date.is_monotonic_increasing):
        raise ValueError("Dates must be nonempty, sorted, unique and valid")
    if (frame.Date != frame.Date.dt.normalize()).any():
        raise ValueError("Expected midnight UTC dates")
    if not frame.Date.diff().dropna().eq(pd.Timedelta(days=1)).all():
        raise ValueError("Missing daily candles; no gap filling allowed")
    for column in required[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not frame[column].map(math.isfinite).all():
            raise ValueError("Non-finite candle value")
    if not (frame[["Open", "High", "Low", "Close"]] > 0).all().all() or (frame.Volume < 0).any():
        raise ValueError("Invalid price or volume")
    if ((frame.High < frame[["Open", "Close", "Low"]].max(axis=1)).any()
            or (frame.Low > frame[["Open", "Close", "High"]].min(axis=1)).any()):
        raise ValueError("Incoherent OHLC candle")
    return frame.reset_index(drop=True)


def features(frame):
    out = frame.copy()
    out["sma200"] = out.Close.rolling(200, min_periods=200).mean()
    out["prior_high20"] = out.High.rolling(20, min_periods=20).max().shift(1)
    out["prior_low10"] = out.Low.rolling(10, min_periods=10).min().shift(1)
    out["entry"] = (out.Close > out.sma200) & (out.Close > out.prior_high20)
    out["exit"] = (out.Close < out.sma200) | (out.Close < out.prior_low10)
    return out


def simulate(frame, start, end, *, strategy="trend", fee_bps=60, slippage_bps=10,
             initial=10000, allocation_fraction=1.0):
    if strategy not in {"trend", "buy_hold", "cash"}:
        raise ValueError("Unknown strategy")
    if not math.isfinite(initial) or initial <= 0:
        raise ValueError("Invalid initial balance")
    if not math.isfinite(allocation_fraction) or not 0 < allocation_fraction <= 1:
        raise ValueError("Entry allocation must be in (0, 1]")
    if any(not math.isfinite(v) or not 0 <= v < 10000 for v in (fee_bps, slippage_bps)):
        raise ValueError("Invalid transaction costs")
    start_ts, end_ts = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    if start_ts > end_ts or start_ts not in set(frame.Date) or end_ts not in set(frame.Date):
        raise ValueError("Evaluation endpoints must be present and ordered")
    data = features(frame.loc[frame.Date <= end_ts].reset_index(drop=True))
    selected = data.index[data.Date >= start_ts].tolist()
    first = selected[0]
    if strategy == "trend" and (first < 200 or pd.isna(data.iloc[first - 1].sma200)):
        raise ValueError("Need 200 completed candles before the first evaluated open")
    fee, slip = fee_bps / 10000, slippage_bps / 10000
    cash, quantity, entry = float(initial), 0.0, None
    fills, trades, curve = [], [], []
    fees_paid = 0.0

    def buy(row, signal_date):
        nonlocal cash, quantity, entry, fees_paid
        reference = float(row.Open)
        price = reference * (1 + slip)
        committed = cash * allocation_fraction
        quantity = committed / (price * (1 + fee))
        charge = quantity * price * fee
        cash -= committed
        fees_paid += charge
        entry = {"entry_date": row.Date.strftime("%Y-%m-%d"), "entry_signal_date": signal_date,
                 "entry_fill": price, "quantity": quantity, "entry_cash": committed,
                 "entry_fee": charge}
        fills.append({"date": entry["entry_date"], "signal_date": signal_date, "side": "buy",
                      "reference": reference, "price": price, "quantity": quantity, "fee": charge,
                      "cash_after": cash, "reason": "entry"})

    def sell(row, reference, reason, signal_date):
        nonlocal cash, quantity, entry, fees_paid
        price = float(reference) * (1 - slip)
        charge = quantity * price * fee
        proceeds = quantity * price - charge
        cash += proceeds
        fees_paid += charge
        exit_date = row.Date.strftime("%Y-%m-%d")
        fills.append({"date": exit_date, "signal_date": signal_date, "side": "sell",
                      "reference": float(reference), "price": price, "quantity": quantity,
                      "fee": charge, "cash_after": cash, "reason": reason})
        trades.append({**entry, "exit_date": exit_date, "exit_signal_date": signal_date,
                       "exit_fill": price, "exit_fee": charge, "exit_cash": cash,
                       "exit_position_proceeds": proceeds,
                       "pnl_usd": proceeds - entry["entry_cash"],
                       "return_pct": 100 * (proceeds / entry["entry_cash"] - 1), "exit_reason": reason})
        quantity, entry = 0.0, None

    for i in selected:
        row = data.iloc[i]
        previous = data.iloc[i - 1] if i else None
        signal_date = previous.Date.strftime("%Y-%m-%d") if previous is not None else None
        if strategy == "buy_hold" and i == first:
            buy(row, None)  # Predetermined benchmark allocation, not a price signal.
        elif strategy == "trend":
            if quantity > 0 and previous["exit"]:
                sell(row, row.Open, "signal", signal_date)
            elif quantity == 0 and previous["entry"]:
                buy(row, signal_date)
        exposed = quantity > 0
        if i == selected[-1] and quantity > 0:
            sell(row, row.Close, "terminal_liquidation", None)
        equity = cash + quantity * float(row.Close)
        if not math.isfinite(equity) or equity <= 0 or cash < -1e-8 or quantity < 0:
            raise ArithmeticError("Invalid cash/position ledger")
        curve.append({"Date": row.Date.strftime("%Y-%m-%d"), "equity": equity,
                      "cash": cash, "btc": quantity, "exposed_during_day": exposed,
                      "close_position_weight": quantity * float(row.Close) / equity})

    equity = pd.Series([initial] + [point["equity"] for point in curve], dtype=float)
    returns = equity.pct_change().dropna()
    drawdowns = equity / equity.cummax() - 1
    pnl = [trade["pnl_usd"] for trade in trades]
    gains, losses = sum(max(v, 0) for v in pnl), sum(max(-v, 0) for v in pnl)
    days = len(curve)
    end_equity = curve[-1]["equity"]
    operating = 120 * days / 365.25
    metrics = {
        "strategy": strategy, "start": start, "end": end, "days": days,
        "entry_allocation_fraction": allocation_fraction,
        "initial_usd": initial, "fee_bps_per_side": fee_bps, "slippage_bps_per_side": slippage_bps,
        "final_usd": end_equity, "net_profit_usd": end_equity - initial,
        "net_return_pct": 100 * (end_equity / initial - 1),
        "annualized_return_pct": 100 * ((end_equity / initial) ** (365.25 / days) - 1),
        "max_close_drawdown_pct": -100 * float(drawdowns.min()),
        "daily_sharpe_rf_zero": float(returns.mean() / returns.std(ddof=1) * math.sqrt(365.25))
            if len(returns) > 1 and returns.std(ddof=1) > 0 else None,
        "closed_trades": len(trades), "signal_exits": sum(t["exit_reason"] == "signal" for t in trades),
        "terminal_exits": sum(t["exit_reason"] == "terminal_liquidation" for t in trades),
        "win_rate_pct": 100 * sum(value > 0 for value in pnl) / len(pnl) if pnl else None,
        "profit_factor": gains / losses if losses > 0 else None,
        "fees_paid_usd": fees_paid, "exposure_pct": 100 * sum(p["exposed_during_day"] for p in curve) / days,
        "max_close_position_weight_pct": 100 * max(p["close_position_weight"] for p in curve),
        "external_operating_cost_120_per_year_usd": operating,
        "profit_after_external_operating_cost_usd": end_equity - initial - operating,
    }
    return {"metrics": metrics, "curve": curve, "fills": fills, "trades": trades}


def assess(results):
    def get(window, cost, strategy):
        return next(item["metrics"] for item in results
                    if item["window"] == window and item["cost"] == cost and item["metrics"]["strategy"] == strategy)
    full = get("full", "base_assumption", "trend")
    hold = get("full", "base_assumption", "buy_hold")
    validation = get("validation", "base_assumption", "trend")
    stress = get("validation", "stress", "trend")
    checks = {
        "full_base_net_profit_positive": full["net_profit_usd"] > 0,
        "validation_base_net_profit_positive": validation["net_profit_usd"] > 0,
        "validation_stress_net_profit_positive": stress["net_profit_usd"] > 0,
        "full_base_drawdown_at_most_35pct": full["max_close_drawdown_pct"] <= 35,
        "full_base_drawdown_below_buy_hold": full["max_close_drawdown_pct"] < hold["max_close_drawdown_pct"],
    }
    sample = {"full_at_least_20_closed_trades": full["closed_trades"] >= 20,
              "validation_at_least_5_closed_trades": validation["closed_trades"] >= 5}
    status = "REJECTED_BY_PREDECLARED_SCREEN" if not all(checks.values()) else (
        "INSUFFICIENT_TRADE_SAMPLE" if not all(sample.values()) else "PAPER_OBSERVATION_CANDIDATE")
    return {"status": status, "performance_checks": checks, "sample_checks": sample,
            "live_trading_authorized": False, "statistical_significance_established": False}


def run_experiment(csv_path, protocol_path, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    protocol_bytes = Path(protocol_path).read_bytes()
    if hashlib.sha256(protocol_bytes).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Protocol differs from the frozen implemented experiment")
    protocol = json.loads(protocol_bytes)
    # This version implements exactly one frozen research protocol, not arbitrary
    # natural-language strategy instructions read from a JSON file.
    if protocol["experiment"] != "btc_daily_trend_001":
        raise ValueError("Unsupported experiment")
    (output / "protocol.json").write_bytes(protocol_bytes)
    frame = load_daily(csv_path)
    expected_last = pd.Timestamp(protocol["data_end_exclusive"], tz="UTC") - pd.Timedelta(days=1)
    if (frame.Date.iloc[0] != pd.Timestamp(protocol["data_start"], tz="UTC")
            or frame.Date.iloc[-1] != expected_last):
        raise ValueError("Dataset does not match the frozen protocol date range")
    results, annual = [], []
    for window in protocol["windows"]:
        for cost in protocol["cost_scenarios_bps_per_side"]:
            for strategy in ("trend", "buy_hold", "cash"):
                outcome = simulate(frame, window["start"], window["end"], strategy=strategy,
                                   fee_bps=cost["fee"], slippage_bps=cost["slippage"],
                                   initial=protocol["rules"]["initial_balance_usd"])
                prefix = f"{window['name']}_{cost['name']}_{strategy}"
                for name in ("curve", "fills", "trades"):
                    records = outcome[name]
                    (output / f"{prefix}_{name}.json").write_text(json.dumps(records, indent=2, allow_nan=False))
                results.append({"window": window["name"], "cost": cost["name"], "metrics": outcome["metrics"]})
                if window["name"] == "full" and cost["name"] == "base_assumption":
                    curve = pd.DataFrame(outcome["curve"])
                    previous = outcome["metrics"]["initial_usd"]
                    for year, group in curve.groupby(curve.Date.str[:4], sort=True):
                        last = float(group.equity.iloc[-1])
                        annual.append({"year": year, "strategy": strategy,
                                       "return_pct": 100 * (last / previous - 1), "ending_usd": last})
                        previous = last
    report = {"protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
              "csv_sha256": hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
              "data_rows": len(frame), "results": results, "annual_full_base": annual,
              "assessment": assess(results), "llm_calls": 0, "orders": 0,
              "limitations": ["Historical simulation, not live P&L or a profit guarantee.",
                  "Chronological splits, no blind holdout and no parameter optimization.",
                  "One exchange, daily candles, no order-book liquidity simulation.",
                  "Drawdown measured at daily closes and final liquidation; intraday losses can be larger.",
                  "Costs are assumptions, not verified user account fees; taxes excluded.",
                  "USD120/year operating expense is an external deduction and does not change position sizes.",
                  "Full simulated balance is exposed while long; no leverage, hard stop or guaranteed exit price."]}
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    pd.DataFrame([{**r["metrics"], "window": r["window"], "cost": r["cost"]} for r in results]).to_csv(output / "metrics.csv", index=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run_experiment(args.csv, args.protocol, args.output)
    print(json.dumps(report["assessment"], indent=2))


if __name__ == "__main__":
    main()
