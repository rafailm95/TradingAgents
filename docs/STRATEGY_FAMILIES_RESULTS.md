# Strategy families experiment007 — completed

Added12 families ×2 entry sizes =24 variants; compared against legacy16 and4 benchmarks. One fixed historical run; no result-driven tuning. All historical dates had already been inspected, so chronological evaluation is not a blind holdout.

- 880 matrix +96 signal-delay +240 WFA training +10 annual ledgers =1,226 audited simulations.
- 1,504,362 daily audit points; maximum reconciliation error 1.75e-09 USD.
- 266 focused tests passed (54new); 400 legacy ledgers reproduced exactly. Full application CI not claimed.
- Train2020–2023 selected `cmf_trend__vol15_cap50`: evaluation2024–2026-10-15 after operating expense +10.98% base / -0.82% stress.
- Five historical screen passes: `adx_directional__fixed50`, `aroon_trend__fixed50`, `aroon_trend__vol15_cap50`, `cmo_momentum__vol15_cap50`, `squeeze_breakout__vol15_cap50`. All fail at least one delay case;0 complete passes.
- WFA2022–2026-10-15 net after annual expense: +31.77% base / +15.06% stress. Negative2022,2025,2026.
- Conditional40-candidate bootstrap p versuscash0.174–0.204; no positive arithmetic-mean excess overbuy_hold50. Not full prior-search correction, not risk matching, and excludes operating expense.
- No new paper candidates, real orders, paid models, or scheduled campaign changes.

## All24 results

Returns include transaction costs and external operating assumption120USD/year on initial10000USD. Matrix drawdown is close-only, before external expense. All returns are cumulative, not annualized.

| Candidate |2024–26 base|2024–26 stress|Worst delayed stress|Initial screen|
|---|---:|---:|---:|---|
|kama_trend__fixed50|-5.51%|-29.67%|-43.89%|FAIL|
|kama_trend__vol15_cap50|-1.76%|-19.95%|-31.91%|FAIL|
|keltner_breakout__fixed50|+15.18%|+5.71%|+7.63%|FAIL|
|keltner_breakout__vol15_cap50|+6.68%|-0.03%|+0.36%|FAIL|
|adx_directional__fixed50|+13.10%|+5.41%|-4.54%|PASS|
|adx_directional__vol15_cap50|+4.88%|-0.07%|-6.57%|FAIL|
|ichimoku_trend__fixed50|+2.86%|-11.20%|-14.40%|FAIL|
|ichimoku_trend__vol15_cap50|+1.25%|-8.57%|-13.25%|FAIL|
|aroon_trend__fixed50|+19.79%|+8.24%|-11.60%|PASS|
|aroon_trend__vol15_cap50|+14.63%|+6.66%|-7.95%|PASS|
|regression_trend__fixed50|+45.67%|+38.74%|+31.22%|FAIL|
|regression_trend__vol15_cap50|+30.02%|+25.66%|+19.13%|FAIL|
|cmo_momentum__fixed50|+17.90%|+6.55%|-4.76%|FAIL|
|cmo_momentum__vol15_cap50|+10.40%|+3.04%|-6.39%|PASS|
|stochastic_pullback__fixed50|-7.60%|-17.72%|-21.36%|FAIL|
|stochastic_pullback__vol15_cap50|-5.17%|-12.92%|-13.58%|FAIL|
|cci_reversion__fixed50|-3.12%|-15.07%|-21.12%|FAIL|
|cci_reversion__vol15_cap50|-3.38%|-12.07%|-15.87%|FAIL|
|squeeze_breakout__fixed50|+18.20%|+4.38%|-1.64%|FAIL|
|squeeze_breakout__vol15_cap50|+10.67%|+1.45%|-4.29%|PASS|
|obv_breakout__fixed50|+11.14%|-3.34%|+4.06%|FAIL|
|obv_breakout__vol15_cap50|+6.83%|-2.88%|-0.04%|FAIL|
|cmf_trend__fixed50|+19.20%|+2.06%|-4.42%|FAIL|
|cmf_trend__vol15_cap50|+10.98%|-0.82%|-4.97%|FAIL|

## Reproduce

```bash
python -m pip install -r requirements-research.txt
python scripts/run_strategy_families.py --csv /absolute/path/btc_coinbase_daily.csv --output /absolute/path/new-result-directory
python -m pytest --noconftest tests/test_strategy_families.py tests/test_strategy_lab.py -q
```

The runner requires the exact CSV and protocol hashes. Existing output directories are rejected. It verifies all14 pinned paper-campaign sources unchanged. No network calls in the runner. The separate HTML reporting script additionally requires matplotlib, a completed experiment register and the test log; it is not part of the scheduled runtime.

RESOLVED: Frozen12-family experiment, complete failure retention and ledger audits.
OPEN: Independent future evidence for new families.
IMPLEMENTATION_READY: Historical research reproduction only.
MATERIAL_BLOCKER: No new candidate passes every frozen criterion.
NEXT_IMPLEMENTATION_SLICE: Preserve and continue existing two-candidate scheduled observation.
DONE_CONDITION: Reproducible results, tests, report and evidence delivered.
EXECUTION_ENVIRONMENT: Python3.12.14, numpy2.3.5, pandas2.2.3.
REQUIRED_MODE: Research and frozen paper observation; no orders.
