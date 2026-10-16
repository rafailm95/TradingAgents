"""Replay the old strategy and test one frozen 50% entry-allocation variant."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tradingagents.strategy_backtest import PROTOCOL_SHA256, load_daily, simulate  # noqa: E402

EXPOSURE_PROTOCOL_SHA256 = "c9d05e121e0b4f34c4b7a648f02050dd6bc201bafa0c26a588364921239362d4"


def assert_equal(left, right):
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        if right is None or not math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-7):
            raise AssertionError(f"Numeric replay mismatch: {left} != {right}")
    elif left != right:
        raise AssertionError("Replay mismatch")


def run(csv_path, prior_dir, output_dir):
    old_bytes = (REPO / "docs/TREND_BACKTEST_PROTOCOL.json").read_bytes()
    new_bytes = (REPO / "docs/EXPOSURE_EXPERIMENT_PROTOCOL.json").read_bytes()
    if hashlib.sha256(old_bytes).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Original protocol hash mismatch")
    if hashlib.sha256(new_bytes).hexdigest() != EXPOSURE_PROTOCOL_SHA256:
        raise ValueError("Exposure protocol hash mismatch")
    old_protocol, protocol = json.loads(old_bytes), json.loads(new_bytes)
    if hashlib.sha256(Path(csv_path).read_bytes()).hexdigest() != protocol["csv_sha256"]:
        raise ValueError("Frozen dataset hash mismatch")
    prior_dir, output = Path(prior_dir), Path(output_dir)
    previous = json.loads((prior_dir / "summary.json").read_text())
    if previous["csv_sha256"] != protocol["csv_sha256"] or previous["protocol_sha256"] != PROTOCOL_SHA256:
        raise ValueError("Prior run provenance mismatch")
    output.mkdir(parents=True, exist_ok=False)
    (output / "protocol.json").write_bytes(new_bytes)
    frame = load_daily(csv_path)
    results, audits = [], []
    for window in old_protocol["windows"]:
        for cost in old_protocol["cost_scenarios_bps_per_side"]:
            for strategy in ("trend", "buy_hold"):
                prefix = f"{window['name']}_{cost['name']}_{strategy}"
                baseline = next(row["metrics"] for row in previous["results"]
                    if row["window"] == window["name"] and row["cost"] == cost["name"]
                    and row["metrics"]["strategy"] == strategy)
                old_curve = json.loads((prior_dir / f"{prefix}_curve.json").read_text())
                old_fills = json.loads((prior_dir / f"{prefix}_fills.json").read_text())
                for fraction in protocol["entry_allocation_fractions"]:
                    outcome = simulate(frame, window["start"], window["end"], strategy=strategy,
                        fee_bps=cost["fee"], slippage_bps=cost["slippage"], initial=10000,
                        allocation_fraction=fraction)
                    if fraction == 1:
                        for key, value in baseline.items():
                            assert_equal(value, outcome["metrics"][key])
                        if len(old_curve) != len(outcome["curve"]):
                            raise AssertionError("Replay curve length differs")
                        for old_row, new_row in zip(old_curve, outcome["curve"], strict=True):
                            for key, value in old_row.items():
                                assert_equal(value, new_row[key])
                        audits.append({"case": prefix, "type": "original_replay", "days": len(old_curve), "status": "PASS"})
                    else:
                        if [(f["date"], f["side"]) for f in old_fills] != [(f["date"], f["side"]) for f in outcome["fills"]]:
                            raise AssertionError("Position sizing changed trade signals")
                        # Independent closed-trade wealth recurrence using the
                        # OLD immutable fill references, not new quantity/cash.
                        wealth, maximum_error = 10000., 0.
                        fee, slip = cost["fee"] / 10000, cost["slippage"] / 10000
                        for i, trade in enumerate(outcome["trades"]):
                            buy, sell = old_fills[2 * i:2 * i + 2]
                            multiple = (sell["reference"] * (1 - slip) * (1 - fee)
                                        / (buy["reference"] * (1 + slip) * (1 + fee)))
                            wealth *= (1 - fraction) + fraction * multiple
                            maximum_error = max(maximum_error, abs(wealth - trade["exit_cash"]))
                            assert_equal(wealth, trade["exit_cash"])
                        assert_equal(wealth, outcome["metrics"]["final_usd"])
                        audits.append({"case": prefix, "type": "independent_50pct_trade_recurrence",
                                       "trades": len(outcome["trades"]), "max_usd_error": maximum_error, "status": "PASS"})
                    for name in ("curve", "fills", "trades"):
                        target = output / f"{prefix}_pct{int(fraction * 100)}_{name}.json"
                        target.write_text(json.dumps(outcome[name], indent=2, allow_nan=False))
                    results.append({"window": window["name"], "cost": cost["name"], "metrics": outcome["metrics"]})

    def get(window, cost, fraction, strategy="trend"):
        return next(r["metrics"] for r in results if r["window"] == window and r["cost"] == cost
                    and r["metrics"]["entry_allocation_fraction"] == fraction and r["metrics"]["strategy"] == strategy)

    full, old = get("full", "base_assumption", .5), get("full", "base_assumption", 1)
    validation, stress = get("validation", "base_assumption", .5), get("validation", "stress", .5)
    checks = {"full_base_drawdown_at_most_35pct": full["max_close_drawdown_pct"] <= 35,
              "full_base_drawdown_improves_vs_100pct": full["max_close_drawdown_pct"] < old["max_close_drawdown_pct"],
              "validation_base_profit_after_operating_positive": validation["profit_after_external_operating_cost_usd"] > 0,
              "validation_stress_profit_after_operating_positive": stress["profit_after_external_operating_cost_usd"] > 0}
    summary = {"experiment": protocol["experiment"], "protocol_sha256": EXPOSURE_PROTOCOL_SHA256,
               "csv_sha256": protocol["csv_sha256"], "results": results, "audits": audits,
               "checks": checks, "status": "HISTORICAL_RISK_CANDIDATE" if all(checks.values()) else "REJECTED_BY_EXPOSURE_SCREEN",
               "out_of_sample_evidence": False, "live_trading_authorized": False, "llm_calls": 0, "orders": 0,
               "limitations": [protocol["data_reuse"], protocol["allocation_semantics"], protocol["benchmark"], protocol["costs"]]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False))
    pd.DataFrame([{**r["metrics"], "window": r["window"], "cost": r["cost"]} for r in results]).to_csv(output / "metrics.csv", index=False)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--prior-results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.csv, args.prior_results, args.output)
    print(json.dumps({"status": result["status"], "checks": result["checks"], "audit_cases": len(result["audits"])}, indent=2))
