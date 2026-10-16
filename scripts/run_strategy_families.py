"""Run experiment007 once on the fixed historical dataset; no network or orders."""
import argparse
import gzip
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tradingagents.strategy_backtest import load_daily
from tradingagents import strategy_lab as old
from tradingagents import strategy_families as new

PROTOCOL_SHA256 = "4fef47213a6b362739bf17c28fbeab9c321382072f566c259005692a7fa75a3b"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def returns_of(result):
    a = np.array([result["metrics"]["initial_usd"]] + [p["equity"] for p in result["curve"]])
    return a[1:]/a[:-1]-1


def audit(frame, outcome, cost, label, audits):
    audits.append({"id":label, **old.audit_wealth(frame, outcome,
        outcome["metrics"]["initial_usd"], cost["fee"], cost["slippage"])})


def run(csv_path, output_dir):
    raw = (REPO/"docs/STRATEGY_FAMILIES_PROTOCOL.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Frozen experiment007 protocol changed")
    protocol = json.loads(raw)
    if tuple(protocol["families"]) != new.FAMILIES or tuple(protocol["sizing"]) != new.SIZINGS:
        raise ValueError("Universe mismatch")
    if hashlib.sha256(Path(csv_path).read_bytes()).hexdigest() != protocol["csv_sha256"]:
        raise ValueError("Research data changed")
    frozen = json.loads((REPO/"docs/PAPER_AUTOMATION_RUNTIME.json").read_bytes())
    for name, expected in frozen["source_files"].items():
        if hashlib.sha256((REPO/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen paper source changed: {name}")
    frame = load_daily(csv_path)
    if len(frame) != 2845 or str(frame.Date.iloc[0].date()) != protocol["data_start"] or str(frame.Date.iloc[-1].date()) != protocol["data_end"]:
        raise ValueError("Data coverage mismatch")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    (out/"protocol.json").write_bytes(raw)
    sources = ["tradingagents/strategy_families.py", "scripts/run_strategy_families.py", "tests/test_strategy_families.py"]
    write_json(out/"run_manifest.json", {"started_utc":datetime.now(timezone.utc).isoformat(),
        "protocol_sha256":PROTOCOL_SHA256, "csv_sha256":protocol["csv_sha256"],
        "source_sha256":{name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in sources},
        "frozen_paper_sources_verified":len(frozen["source_files"]),
        "python":platform.python_version(), "numpy":np.__version__, "pandas":pd.__version__,
        "unseen_evidence":False, "orders":0, "llm_calls":0})
    z = new.indicators(frame)
    features = {f:new.signals(frame, f, prepared_indicators=z) for f in new.FAMILIES}
    old_features = {f:old.signals(frame, f) for f in old.FAMILIES}
    universe = (*new.CANDIDATES, *old.CANDIDATES, *protocol["benchmarks"])
    results, audits, metrics, training = {}, [], [], {}
    for window in protocol["windows"]:
        for cost in protocol["costs"]:
            for item in universe:
                is_new, is_old = isinstance(item, new.Candidate), isinstance(item, old.Candidate)
                name = item.id if is_new or is_old else item
                kwargs = dict(fee_bps=cost["fee"], slippage_bps=cost["slippage"],
                    operating_per_year=120 if is_new or is_old or item == "original_trend100" else 0)
                if is_new:
                    outcome = new.simulate(frame, window["start"], window["end"], item,
                        prepared=features[item.family], **kwargs)
                else:
                    outcome = old.simulate(frame, window["start"], window["end"], item if is_old else None,
                        benchmark=None if is_old else item,
                        prepared=old_features[item.family if is_old else "breakout20"], **kwargs)
                key = f"{window['name']}__{cost['name']}__{name}"
                results[key] = outcome
                metrics.append({"window":window["name"], "cost":cost["name"], "id":name,
                    "cohort":"new24" if is_new else "legacy16" if is_old else "benchmark", **outcome["metrics"]})
                audit(frame, outcome, cost, key, audits)
                if window["name"] == "train" and is_new:
                    training.setdefault(name, {})[cost["name"]] = outcome["metrics"]
            print(f"Completed matrix {window['name']} / {cost['name']}", flush=True)
        if window["name"] == "train":
            selection = new.select_candidate(training)
            write_json(out/"selection_before_evaluation.json", selection)
            print(f"New24 train-only selection: {selection['selected']}", flush=True)

    delays, delay_metrics = {}, []
    for lag in (1, 2):
        for cost in protocol["costs"][2:]:
            for candidate in new.CANDIDATES:
                outcome = new.simulate(frame, "2024-01-01", protocol["data_end"], candidate,
                    extra_signal_lag=lag, prepared=features[candidate.family],
                    fee_bps=cost["fee"], slippage_bps=cost["slippage"])
                key = f"lag{lag}__{cost['name']}__{candidate.id}"
                delays[key] = outcome
                delay_metrics.append({"lag":lag, "cost":cost["name"], "id":candidate.id, **outcome["metrics"]})
                audit(frame, outcome, cost, key, audits)
            print(f"Completed signal-lag sensitivity {lag} / {cost['name']}", flush=True)

    assessments, diagnostics = [], []
    for candidate in new.CANDIDATES:
        checks, delayed_checks = {}, {}
        for cost in ("base", "stress"):
            for window in ("full", "validation", "recent"):
                m = results[f"{window}__{cost}__{candidate.id}"]["metrics"]
                checks[f"{window}_{cost}_positive_after_operating"] = m["profit_after_operating_usd"] > 0
                if window == "full":
                    checks[f"full_{cost}_dd_at_most_35"] = m["max_close_drawdown_pct"] <= 35
                    checks[f"full_{cost}_20_trades"] = m["closed_trades"] >= 20
                elif window == "validation":
                    checks[f"validation_{cost}_5_trades"] = m["closed_trades"] >= 5
            for lag in (1, 2):
                m = delays[f"lag{lag}__{cost}__{candidate.id}"]["metrics"]
                delayed_checks[f"lag{lag}_{cost}_positive_after_operating"] = m["profit_after_operating_usd"] > 0
                delayed_checks[f"lag{lag}_{cost}_dd_at_most_35"] = m["max_close_drawdown_pct"] <= 35
            result = results[f"full__{cost}__{candidate.id}"]
            positive = sorted([t["pnl_usd"] for t in result["trades"] if t["pnl_usd"] > 0], reverse=True)
            annual = []
            previous = 10000.
            for year in range(2020, 2027):
                points = [p for p in result["curve"] if p["Date"].startswith(str(year))]
                final = points[-1]["equity"]
                annual.append({"year":year, "days":len(points), "return_pct_before_external_operating":100*(final/previous-1)})
                previous = final
            diagnostics.append({"id":candidate.id, "cost":cost, "annual_mark_returns":annual,
                "positive_trade_count":len(positive), "largest_positive_trade_usd":positive[0] if positive else 0,
                "top3_share_of_positive_trade_pnl":sum(positive[:3])/sum(positive) if positive else None,
                "net_profit_after_opex_less_largest_winner_attribution_only":result["metrics"]["profit_after_operating_usd"]-(positive[0] if positive else 0)})
        assessments.append({"id":candidate.id, "historical_screen_pass":all(checks.values()),
            "delay_robust_screen_pass":all(checks.values()) and all(delayed_checks.values()),
            "checks":checks, "delay_checks":delayed_checks,
            "failed":[k for k,v in checks.items() if not v],
            "delay_failed":[k for k,v in delayed_checks.items() if not v], "adopted_into_paper":False})

    all_candidates = (*new.CANDIDATES, *old.CANDIDATES)
    panel = np.column_stack([returns_of(results[f"evaluation__base__{c.id}"]) for c in all_candidates])
    multiplicity = []
    for baseline in ("cash", "buy_hold50"):
        for block in (10, 30, 60):
            multiplicity.append({"benchmark":baseline, "candidate_count":40,
                **old.bootstrap_max_mean(panel, returns_of(results[f"evaluation__base__{baseline}"]), block=block)})
    print("Completed exploratory multiplicity diagnostic across40 candidates", flush=True)

    walk_forward, wf_training = [], {}
    balances = {"base":10000., "stress":10000.}
    combined = {"base":[], "stress":[]}
    for year in range(2022, 2027):
        train_end = f"{year-1}-12-31"
        train_metrics = {}
        for candidate in new.CANDIDATES:
            train_metrics[candidate.id] = {}
            for cost in protocol["costs"][2:]:
                result = new.simulate(frame, "2020-01-01", train_end, candidate,
                    prepared=features[candidate.family], fee_bps=cost["fee"], slippage_bps=cost["slippage"])
                key = f"wf_train_{year}__{cost['name']}__{candidate.id}"
                wf_training[key] = result
                train_metrics[candidate.id][cost["name"]] = result["metrics"]
                audit(frame, result, cost, key, audits)
        chosen = new.select_candidate(train_metrics)
        candidate = next((c for c in new.CANDIDATES if c.id == chosen["selected"]), None)
        end = f"{year}-12-31" if year < 2026 else protocol["data_end"]
        fold = {"year":year, "train_end":train_end, "selection":chosen, "training_metrics":train_metrics, "results":{}}
        for cost in protocol["costs"][2:]:
            name, previous = cost["name"], balances[cost["name"]]
            if previous <= 0:
                raise ArithmeticError("Research bot insolvent")
            kwargs = dict(initial=previous, fee_bps=cost["fee"], slippage_bps=cost["slippage"], operating_per_year=120)
            if candidate:
                result = new.simulate(frame, f"{year}-01-01", end, candidate, prepared=features[candidate.family], **kwargs)
            else:
                result = old.simulate(frame, f"{year}-01-01", end, benchmark="cash", **kwargs)
            audit(frame, result, cost, f"wf_{year}_{name}", audits)
            balances[name] = result["metrics"]["final_usd"]-result["metrics"]["operating_cost_usd"]
            net_curve = [dict(point) for point in result["curve"]]
            net_curve[-1]["equity"] = balances[name]
            net_curve[-1]["cash"] = balances[name]
            combined[name].extend(net_curve)
            result["operating_debit"] = {"date":end, "amount_usd":result["metrics"]["operating_cost_usd"], "cash_after":balances[name]}
            fold["results"][name] = result
        walk_forward.append(fold)
        print(f"Completed expanding-window fold {year}: {chosen['selected']}", flush=True)
    wf_summary = {}
    for cost, curve in combined.items():
        values = np.array([10000.] + [p["equity"] for p in curve])
        wf_summary[cost] = {"start":"2022-01-01", "end":protocol["data_end"],
            "final_after_operating_usd":balances[cost], "net_return_after_operating_pct":100*(balances[cost]/10000-1),
            "max_close_drawdown_after_operating_pct":100*float((1-values/np.maximum.accumulate(values)).max())}
    summary = {"experiment":protocol["experiment"], "completed_utc":datetime.now(timezone.utc).isoformat(),
        "protocol_sha256":PROTOCOL_SHA256, "csv_sha256":protocol["csv_sha256"], "data_rows":len(frame),
        "new_candidate_count":24, "legacy_candidate_count":16, "matrix_runs":len(results),
        "delay_runs":len(delays), "walk_forward_training_runs":len(wf_training), "walk_forward_fold_runs":10,
        "metrics":metrics, "delay_metrics":delay_metrics, "selection":selection, "assessments":assessments,
        "diagnostics":diagnostics, "multiplicity":multiplicity, "walk_forward_summary":wf_summary,
        "walk_forward_choices":[{"year":f["year"], "selected":f["selection"]["selected"],
            **{cost+"_return_after_operating_pct":f["results"][cost]["metrics"]["return_after_operating_pct"] for cost in ("base", "stress")}} for f in walk_forward],
        "audit_cases":len(audits), "audit_days":sum(a["days"] for a in audits),
        "max_audit_usd_error":max(a["max_usd_error"] for a in audits),
        "signal_counts":{f:{k:int(features[f][k].sum()) for k in ("entry","exit")} for f in new.FAMILIES},
        "orders":0, "llm_calls":0, "unseen_evidence":False, "paper_campaign_changes":False,
        "limitations":[protocol["data_reuse"], protocol["cost_note"], protocol["allocation"],
            protocol["execution"], protocol["delay_stress"], protocol["multiplicity"],
            "Only BTC/USD on one exchange. No other asset, intraday interval or forward validation.",
            "Close drawdown excludes intraday lows and is not guaranteed worst loss.",
            "No real profit or recurring income has been demonstrated."]}
    write_json(out/"summary.json", summary)
    write_json(out/"audits.json", audits)
    pd.DataFrame(metrics).to_csv(out/"metrics.csv", index=False)
    pd.DataFrame(delay_metrics).to_csv(out/"delay_metrics.csv", index=False)
    for name, value in (("all_runs",results), ("delays",delays), ("walk_forward",walk_forward), ("walk_forward_training",wf_training)):
        with gzip.open(out/f"{name}.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(value, stream, allow_nan=False)
    write_json(out/"evidence_inventory.json", {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()})
    print(json.dumps({"selection":selection, "historical_pass":[a["id"] for a in assessments if a["historical_screen_pass"]],
        "delay_robust_pass":[a["id"] for a in assessments if a["delay_robust_screen_pass"]],
        "walk_forward":wf_summary, "audit_cases":len(audits)}, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.csv, args.output)
