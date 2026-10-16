"""Reconcile real-data portfolio curves with independent return arithmetic."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tradingagents.strategy_backtest import load_daily  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--prior-csv", default="examples/verified_market/btc_coinbase.csv")
    args = parser.parse_args()
    root = Path(args.results)
    frame = load_daily(args.csv)
    report = json.loads((root / "summary.json").read_text())
    checks = []
    for scenario in ("frictionless", "low_cost", "base_assumption", "stress"):
        metrics = next(r["metrics"] for r in report["results"] if r["window"] == "full"
                       and r["cost"] == scenario and r["metrics"]["strategy"] == "trend")
        fee = metrics["fee_bps_per_side"] / 10000
        slip = metrics["slippage_bps_per_side"] / 10000
        dates = frame.Date.dt.strftime("%Y-%m-%d").tolist()
        first, last = dates.index(metrics["start"]), dates.index(metrics["end"])
        close, opening, high, low = (frame[c].to_numpy() for c in ("Close", "Open", "High", "Low"))
        wealth, holding, values = metrics["initial_usd"], False, []
        for i in range(first, last + 1):
            j = i - 1
            average = np.mean(close[j - 199:j + 1])
            enter = close[j] > average and close[j] > max(high[j - 20:j])
            leave = close[j] < average or close[j] < min(low[j - 10:j])
            if holding:
                wealth *= opening[i] / close[i - 1]
            if holding and leave:
                wealth *= (1 - slip) * (1 - fee)
                holding = False
            elif not holding and enter:
                wealth /= (1 + slip) * (1 + fee)
                holding = True
            if holding:
                wealth *= close[i] / opening[i]
            if i == last and holding:
                wealth *= (1 - slip) * (1 - fee)
            values.append(wealth)
        ledger = json.loads((root / f"full_{scenario}_trend_curve.json").read_text())
        expected = [row["equity"] for row in ledger]
        np.testing.assert_allclose(values, expected, rtol=1e-10, atol=1e-7)
        checks.append({"scenario": scenario, "days_checked": len(values), "status": "PASS",
                       "max_absolute_usd_difference": float(np.abs(np.array(values) - expected).max())})
    old, new = pd.read_csv(args.prior_csv), pd.read_csv(args.csv)
    overlap = new[new.Date.isin(old.Date)].reset_index(drop=True)
    pd.testing.assert_frame_equal(old, overlap, check_dtype=False)
    result = {"independent_real_data_accounting": checks,
              "previous_257_candles_match_fresh_download": True,
              "scope": "Independent scalar recurrence vs quantity/cash ledger; same single-exchange source, not independent venue verification."}
    (root / "independent_checks.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
