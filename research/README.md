# Persistent research continuation

Start with registry.json and docs/RESEARCH_CONTINUATION_POLICY.json. Each run completes at most one preregistered batch and records every outcome, including failures. No arbitrary parameter search until green. Preserve immutable original and expanded forward campaigns on their separate branches.

Experiment009 data are frozen exact public daily candles under research/data/{ETH-USD,LTC-USD}. BTC seed for the next batch is data/paper-expanded/btc_seed_20190101_20261015.csv. Validate manifest hashes before use. Raw HTTP responses and complete audited curves are in the accompanying evidence archive; hashes of every full result are committed under experiments/009/result_file_hashes.json. CSV metrics, all gate failures, lag metrics, selections, WFA results and multiplicity diagnostics are retained here. Do not rely on prior scratch paths.

Reproduce009 only for a specified defect/audit, not to repeat an identical search:

```bash
python -m pip install -r requirements-research.txt
python scripts/run_cross_asset_lab.py --data-root research/data --output /tmp/cross-asset-reproduction-009
```

Use a fresh nonexistent output directory. The runner refuses existing output. Python3.12. No model providers or credentials. Costs and windows are in each frozen protocol. Read the current registry for the active batch; 011 and 015–017 are completed, not pending. Never modify old accepted outputs; corrections get a new attempt ID and an explanation.

018 addresses the concrete futures evidence gap of trade-profit concentration and calendar attribution using authenticated existing 017 results. It introduces no strategy variants or replay executions. Its descriptive arithmetic does not replace the original gates or create walk-forward evidence. Bybit013 still awaits the one unified packet. See docs/FUTURES_CONCENTRATION_018.json and the independently published pre-analysis freeze.

No forward-profit milestone has been reached. User cancellation or a verified forward milestone ends the strategy search; continue frozen observation without real orders. Access, integrity or resource blockers are reported rather than bypassed.
