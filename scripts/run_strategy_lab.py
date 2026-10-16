"""Run the fixed research matrix. No network calls, models, or orders."""
import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tradingagents.strategy_backtest import load_daily, simulate as original_simulate
from tradingagents.strategy_lab import (CANDIDATES, FAMILIES, SIZINGS, audit_wealth,
    bootstrap_max_mean, select_candidate, signals, simulate)

PROTOCOL_SHA256 = "848a6696b9899a9d7817f1997001bf7a5996688b77b2d54c699b20c08127ed97"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def returns_of(result, initial=10000):
    values = np.array([initial] + [p["equity"] for p in result["curve"]])
    return values[1:] / values[:-1] - 1


def run(csv_path, output_dir):
    raw = (REPO / "docs/STRATEGY_LAB_PROTOCOL.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Frozen research protocol changed")
    protocol = json.loads(raw)
    if tuple(protocol["families"]) != FAMILIES or tuple(protocol["sizing"]) != SIZINGS:
        raise ValueError("Implementation universe mismatch")
    if hashlib.sha256(Path(csv_path).read_bytes()).hexdigest() != protocol["csv_sha256"]:
        raise ValueError("Research dataset changed")
    frame = load_daily(csv_path)
    if str(frame.Date.iloc[0].date()) != protocol["data_start"] or str(frame.Date.iloc[-1].date()) != protocol["data_end"]:
        raise ValueError("Date range mismatch")
    output = Path(output_dir)
    output.mkdir(exist_ok=False, parents=True)
    (output / "protocol.json").write_bytes(raw)
    feature_cache = {f: signals(frame, f) for f in FAMILIES}
    results, audits, metrics = {}, [], []
    training, selected = {}, None
    for window in protocol["windows"]:
        for cost in protocol["costs"]:
            for item in (*CANDIDATES, *protocol["benchmarks"]):
                is_candidate = not isinstance(item, str)
                name = item.id if is_candidate else item
                outcome = simulate(frame, window["start"], window["end"],
                    candidate=item if is_candidate else None, benchmark=None if is_candidate else item,
                    fee_bps=cost["fee"], slippage_bps=cost["slippage"],
                    operating_per_year=120 if is_candidate or item == "original_trend100" else 0,
                    prepared=feature_cache[item.family if is_candidate else "breakout20"])
                key = f"{window['name']}__{cost['name']}__{name}"
                results[key] = outcome
                row = {"window": window["name"], "cost": cost["name"], "id": name, **outcome["metrics"]}
                metrics.append(row)
                audits.append({"id": key, **audit_wealth(frame, outcome, 10000, cost["fee"], cost["slippage"])})
                if window["name"] == "train" and is_candidate:
                    training.setdefault(name, {})[cost["name"]] = outcome["metrics"]
                if item == "original_trend100":
                    old = original_simulate(frame, window["start"], window["end"],
                        fee_bps=cost["fee"], slippage_bps=cost["slippage"])
                    np.testing.assert_allclose([r["equity"] for r in outcome["curve"]],
                        [r["equity"] for r in old["curve"]], rtol=1e-12)
            print(f"Completed {window['name']} / {cost['name']}", flush=True)
        if window["name"] == "train":
            selected = select_candidate(training)
            write_json(output / "selection_before_evaluation.json", selected)
            print(f"Train-only selection: {selected['selected']}", flush=True)
    assessment = []
    for candidate in CANDIDATES:
        checks = {}
        for cost in ("base", "stress"):
            for window in ("full", "validation", "recent"):
                m = results[f"{window}__{cost}__{candidate.id}"]["metrics"]
                checks[f"{window}_{cost}_positive_after_operating"] = m["profit_after_operating_usd"] > 0
                if window == "full":
                    checks[f"full_{cost}_dd_at_most_35"] = m["max_close_drawdown_pct"] <= 35
                    checks[f"full_{cost}_20_trades"] = m["closed_trades"] >= 20
                if window == "validation":
                    checks[f"validation_{cost}_5_trades"] = m["closed_trades"] >= 5
        assessment.append({"id": candidate.id, "status": "HISTORICAL_PAPER_CANDIDATE" if all(checks.values()) else "SCREEN_FAILED",
                           "checks": checks, "failed": [k for k,v in checks.items() if not v]})
    panel = np.column_stack([returns_of(results[f"evaluation__base__{c.id}"]) for c in CANDIDATES])
    multiplicity = []
    for baseline in ("buy_hold50", "cash"):
        reference = returns_of(results[f"evaluation__base__{baseline}"])
        for block in (10, 30, 60):
            multiplicity.append({"benchmark": baseline, **bootstrap_max_mean(panel, reference, block=block)})
    walk_forward = []
    balances = {"base": 10000., "stress": 10000.}
    combined = {"base": [], "stress": []}
    for year in range(2022, 2027):
        train_end = f"{year-1}-12-31"
        train_metrics = {}
        for candidate in CANDIDATES:
            train_metrics[candidate.id] = {}
            for cost in protocol["costs"][2:]:
                run_result = simulate(frame, "2020-01-01", train_end, candidate,
                    fee_bps=cost["fee"], slippage_bps=cost["slippage"], prepared=feature_cache[candidate.family])
                train_metrics[candidate.id][cost["name"]] = run_result["metrics"]
        selection = select_candidate(train_metrics)
        name = selection["selected"]
        candidate = next((c for c in CANDIDATES if c.id == name), None)
        end = f"{year}-12-31" if year < 2026 else "2026-10-15"
        fold = {"year": year, "train_end": train_end, "selection": selection,
                "training_metrics": train_metrics, "results": {}}
        for cost in protocol["costs"][2:]:
            cn = cost["name"]
            previous = balances[cn]
            if previous <= 0:
                raise ArithmeticError("Research bot insolvent")
            outcome = simulate(frame, f"{year}-01-01", end, candidate,
                benchmark="cash" if candidate is None else None, initial=previous,
                fee_bps=cost["fee"], slippage_bps=cost["slippage"],
                prepared=feature_cache[candidate.family if candidate else "breakout20"])
            audits.append({"id": f"walk_{year}_{cn}", **audit_wealth(frame, outcome, previous, cost["fee"], cost["slippage"])})
            # Operating expense is debited at each annual segment's end, unlike
            # the matrix's external period-end sensitivity. Carry net equity.
            balances[cn] = outcome["metrics"]["final_usd"] - outcome["metrics"]["operating_cost_usd"]
            net_curve = [dict(point) for point in outcome["curve"]]
            net_curve[-1]["equity"] = balances[cn]
            net_curve[-1]["cash"] = balances[cn]
            outcome["metrics"]["carried_end_after_operating_usd"] = balances[cn]
            outcome["operating_debit"] = {"date": end, "amount_usd": outcome["metrics"]["operating_cost_usd"],
                                           "cash_after": balances[cn]}
            combined[cn].extend(net_curve)
            fold["results"][cn] = outcome
        walk_forward.append(fold)
    wf_summary = {}
    for cost, curve in combined.items():
        values = np.array([10000.] + [p["equity"] for p in curve])
        wf_summary[cost] = {"start": "2022-01-01", "end": "2026-10-15",
            "final_after_operating_usd": balances[cost], "net_return_after_operating_pct": 100 * (balances[cost] / 10000 - 1),
            "max_close_drawdown_after_operating_pct": 100 * float((1-values / np.maximum.accumulate(values)).max())}
    summary = {"experiment": protocol["experiment"], "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": PROTOCOL_SHA256, "csv_sha256": protocol["csv_sha256"], "data_rows": len(frame),
        "candidate_count": len(CANDIDATES), "matrix_runs": len(results), "metrics": metrics,
        "selection": selected, "assessments": assessment, "multiplicity": multiplicity,
        "walk_forward_summary": wf_summary,
        "walk_forward_choices": [{"year": f["year"], "selected": f["selection"]["selected"],
            "base_profit_after_operating_usd": f["results"]["base"]["metrics"]["profit_after_operating_usd"],
            "base_return_after_operating_pct": f["results"]["base"]["metrics"]["return_after_operating_pct"]} for f in walk_forward],
        "audit_cases": len(audits), "audit_days": sum(a["days"] for a in audits),
        "max_audit_usd_error": max(a["max_usd_error"] for a in audits),
        "llm_calls": 0, "orders": 0, "unseen_evidence": False,
        "limitations": [protocol["data_reuse"], protocol["cost_note"],
            "Single exchange/daily bars; close drawdown excludes intraday extremes and outage risk.",
            "No delay, order-book, partial-fill or available-volume model; next-open fills idealized.",
            "Entry-only allocations can drift above 50%; vol15 is not an achieved risk target.",
            "Bootstrap is exploratory and conditional on these candidates, not all prior choices.",
            "No claimed annual income, future profit, paper fills or live deployment."]}
    write_json(output / "summary.json", summary)
    write_json(output / "audits.json", audits)
    pd.DataFrame(metrics).to_csv(output / "metrics.csv", index=False)
    for name, value in (("all_runs", results), ("walk_forward", walk_forward)):
        with gzip.open(output / f"{name}.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(value, stream, allow_nan=False)
    print(json.dumps({"selection": selected, "passing": [a["id"] for a in assessment if a["status"] != "SCREEN_FAILED"],
                      "walk_forward": wf_summary, "audit_cases": len(audits)}, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.csv, args.output)
