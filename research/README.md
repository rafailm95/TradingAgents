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

019 preregisters one funding-aware futures family with two existing sizings and an annual capital-continuous walk-forward selector over all eight comparable native-futures candidates. Exact rules, accounting delta, preflight failures and synthetic checks are frozen before new outcomes. All earlier accepted source/results and013/014 remain unchanged.

019 completed: 68 new scenarios, two new variants, no full robustness passes. Funding family has positive lag2 scenarios but negative lag0/1; main-selected and nominal walk-forward outcomes lose. Five integrity recoveries preserve four initial zero-byte files and a repeated truncation; all accepted decoded hashes match the original manifest. Full failures, recovery transport and68audited paths are in the durable evidence archive. Totals48variants/24families;7495designruns+7integrityreplays=7502.

## Batch020 preregistration —2026-10-17

One NR7 daily-close family, two unchanged sizings, ETHUSDT native Binance futures. All10 compatible candidates compared; prior outcomes reused with hashes.32core new simulations plus0..24conditional WFAfolds. Exact rules and freeze in `docs/NR7_FUTURES_020.json` and `research/experiments/020/freeze.json`;129synthetic tests passed. No new market outcome computed before remote checkpoint.013still awaits the single Bybitpacket.

## Batch020 completed —2026-10-17

32new native BinanceETHUSDT historical scenario executions;2new NR7 variants,50total in25families.0/2new and0/10compatible fullpasses;2/24new scenario passes.29signal exits each. Fixed50base+2.51754% (+251.75USDT),stress-1.31106% (-131.11),worst-23.48888% (-2348.89);maxDD35.11084%/3649.76actualUSDT. Volbase-0.94150% (-94.15),stress-2.63181% (-263.18),worst-13.48369% (-1348.37),maxDD19.03437%/1948.37. Train-only choices remain019funding→OBV;24identical WFAfolds reused,4/12scenario passes and fullfailure.129tests/2,786,608independentwealth events,zeroerror.7527design+7priorintegrityreplays=7534knownexecutions. Full results/failures in `docs/NR7_FUTURES_020_RESULTS.md` and `research/experiments/020`. No new prospective evidence or orders.
