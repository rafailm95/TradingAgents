# Weekly confirmation experiment011 — completed, no new screen pass

Added one causal signal family with two sizes. The42-candidate comparative run covers BTC, ETH and LTC. **3174 simulations**, **4015638 daily wealth checks**, **322 targeted software tests passed**. The40 references were recomputed for a common42-candidate selector and multiple-comparison panel; they are not3174 new strategies. Each asset has460matrix runs,168delay runs,420training runs and10WFA folds.

The exact code, inputs and protocol were published at `159ba06b11ec3b71ee6b70392fc809c8a14cd014` before evaluation. Freeze SHA256: `e9391b9f0bcfa46045e58ddd982c5e495ad488d5181aeb272a41184df46fd16d`. No after-result retuning or historical rerun. All440reference matrix rows per asset match the earlier metrics exactly; see reference_parity.json. The original two and expanded five paper campaigns retain their source pins and branches.

## New variants — evaluation2024-01-01..2026-10-15

All returns below are cumulative after per-side transaction costs andUSD120/year prorated modeled operating expense, before tax. Initial equityUSD10000 per independent book. Basefee60bps/slippage10bps; stress120bps/25bps. Daily close drawdown excludes the external operating deduction. Closed trades can include terminal forced liquidation.

| Asset | Variant | Base net | Stress net | Stress close DD | Closed trades | All gates |
|---|---|---:|---:|---:|---:|---|
| BTC-USD | fixed50 | +8.05% | -1.56% | 23.34% | 12 | FAIL |
| BTC-USD | vol15_cap50 | +1.54% | -4.76% | 16.82% | 12 | FAIL |
| ETH-USD | fixed50 | -16.56% | -22.11% | 30.61% | 9 | FAIL |
| ETH-USD | vol15_cap50 | -8.10% | -11.07% | 16.16% | 9 | FAIL |
| LTC-USD | fixed50 | -39.26% | -43.21% | 40.04% | 9 | FAIL |
| LTC-USD | vol15_cap50 | -16.27% | -18.58% | 21.77% | 9 | FAIL |

Both variants failed the full historical/delay screen on every asset. BTC had some positive base-cost returns but recent-period and stressed-delay weaknesses. ETH and LTC failed broadly. LTC train-only selection chose the newvol15variant; its subsequent evaluation loses18.58%stress. These candidates are research additions only, not added to the seven prospective paper books.

## All42 chronological selection

| Asset | Train-only winner | Evaluation base / stress | WFA2022..2026 base / stress |
|---|---|---|---|
| BTC-USD | cmf_trend__vol15_cap50 | +10.98% / -0.82% | +31.77% / +15.06% |
| ETH-USD | breakout20__fixed50 | -8.23% / -15.68% | +13.37% / -0.70% |
| LTC-USD | weekly_confirmed_breakout20__vol15_cap50 | -16.27% / -18.58% | -29.49% / -32.39% |

BTC WFA is historically positive; its chosen single evaluation strategy is stress-negative. Different selection windows and annual resetting explain why these measures differ. WFA includes year-end operating debits, even for cash. The positive BTC WFA is not a new weekly-family success or forward proof.

Full42 robust historical passes: BTC1(SMA200bandvol15), ETH4(Aroonfixed/vol andOBVfixed/vol), LTC0. None passes across all3assets. These are reused historical findings; many trials, correlated assets and short recent samples remain limitations. Bootstrap diagnostics include all42 under blocks30/60,2000resamples, seed20261016; they exclude operating expenses and do not correct the whole prior research process.

## Execution realism

The standalone depth diagnostic and31new targeted tests were added. Its three public product-metadata requests failed with runtime-tunnel403Forbidden. No book snapshots or actual depth measurements exist. No automatic retry or real orders. Official fee/product/book documentation was reviewed; the actual user venue, fee tier, capital and risk tolerance remain unknown. See EXECUTION_REALISM_REVIEW.md and research/realism_backlog.json. Existing scheduled tasks remain enabled but future API availability is not established.

## Reproduce

```bash
python scripts/run_weekly_confirmation_lab.py --output /tmp/new-weekly-reproduction --freeze-sha e9391b9f0bcfa46045e58ddd982c5e495ad488d5181aeb272a41184df46fd16d
```

UsePython3.12 and requirements-research.txt, a fresh nonexistent output path, all committed inputs and unchanged freeze. Reproduction should resolve a concrete audit/defect, not repeat unchanged results seeking profit. Full curves and audits are delivered separately; their hashes are committed. All metrics/failures, selection and WFA tables are durable here.

RESOLVED: Frozen batch011 and tested standalone execution-depth diagnostics.
OPEN: No new robust candidate; no live depth capture or prospective profitability.
IMPLEMENTATION_READY: Offline research YES; public depth capture blocked in this environment.
MATERIAL_BLOCKER: Runtime API tunnel403; user-specific venue/capital/fees unknown.
NEXT_IMPLEMENTATION_SLICE: Next bounded preregistered family, plus venue/capital calibration.
DONE_CONDITION: Results durably published and automation reads latest registry without repeating011.
EXECUTION_ENVIRONMENT: Python3.12, pinned research dependencies.
REQUIRED_MODE: Research/virtual accounting; zero real orders.
