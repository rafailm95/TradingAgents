# Entry allocation study 002 and prospective signal journal

## Decision

Allocating 50% at entry reduced the base-case historical drawdown from 52.27%
to 33.45%, while retaining a positive historical return. The predefined study
screen therefore reports **HISTORICAL_RISK_CANDIDATE**, not a live-ready or
proven profitable bot. The stress case still reaches **37.79% drawdown**, above
35%, and the 2026 result after the operating-cost assumption remains negative.

These are reused historical data, not an unseen holdout. One explicit sizing
change was tested, with no sweep over fractions or changes to entry/exit rules.
The original failed experiment and its evidence remain intact.

## Sizing semantics

At each entry, 50% of available cash is spent, including entry fees. The other
half remains idle at zero interest. No rebalancing occurs while a position is
held. On exit, sale proceeds are added to the existing reserve, and trade P&L
excludes that reserve. Subsequent entries use half of the then-current cash.

**This is not a continuous 50% exposure cap.** In the full base scenario, the
position grew to 84.32% of closing portfolio value during an extended rise.
The initially 50%-invested buy-and-hold benchmark drifted to 94.53%.
Equal initial allocation does not mean equal time-varying risk or volatility.

The engine's default remains 100% for reproducibility. The frozen study runner
explicitly passes `allocation_fraction=0.5` for the new variant.

## Results

Initial USD10,000, no leverage, same daily SMA200/High20/Low10 signals, next-open
execution, and final-close liquidation. Base costs are an assumed 0.60% fee and
0.10% adverse execution per side, not verified account rates. Returns below are
after transaction costs, before operating expense and tax. Every time window
resets to cash independently.

| Period | Trend 100% return | Trend 50% return | Trend 100% drawdown | Trend 50% drawdown | Buy/hold initial 50% return | Buy/hold initial 50% drawdown |
|---|---:|---:|---:|---:|---:|---:|
| 2020-01-01–2026-10-15 | +397.69% | +209.79% | 52.27% | 33.45% | +515.12% | 69.27% |
| 2020–2023 | +244.55% | +149.07% | 52.27% | 33.45% | +240.97% | 69.27% |
| 2024–2025 | +33.87% | +19.88% | 29.50% | 17.40% | +52.02% | 23.93% |
| 2026 through 15 October | +0.05% | +0.16% | 14.08% | 7.45% | −3.72% | 20.77% |

The 50% variant ends the full window at USD30,978.63. Under the stress assumption
(1.20% fee + 0.25% adverse execution per side), it ends at USD25,001.76, a
150.02% return with 37.79% drawdown. The 2024–2025 stress return is 10.30%.

For 2026, the base-case profit is only USD15.79 per hypothetical USD10,000;
subtracting USD120/year prorated over 288 days makes it **−USD78.83**. With
stress transaction costs and the same operating expense it is **−USD227.42**.
The operating expense is an external sensitivity, not a measured bill; it does
not change position sizes. No paid inference or actual orders occurred.

## Validation

**92 focused tests passed.** Cash-reserve tests cover a hand-calculated round
trip, multiple successive entries, fee accounting, profit reconciliation,
invalid allocations and forward-price isolation. Existing simulator,
rating-backtest and verified-market tests were included.

The runner checked **64 cases**:

- 32 original 100% cases: every original metric and every original daily
  curve field matches the saved first experiment within floating-point tolerance.
- 32 new 50% cases: unchanged fill dates/directions, plus independent trade-return
  recurrence using old immutable reference prices reconciles every trade's final
  balance and the final portfolio value.

This is independent arithmetic, not independent analyst review. Drawdowns are
at daily closes; intraday losses can be larger. Only one asset and exchange,
approximate fills, known historical periods and few trades limit inference.

## Prospective journal — implemented, not scheduled

`python -m tradingagents.signal_journal` records daily indicators and conditions
from newly completed UTC candles. It is a signal journal, **not a portfolio,
paper-fill engine, broker integration or scheduler**. No forward P&L is claimed.

The first permitted candle is 2026-10-17. Its earliest recording time is
2026-10-18 00:00 UTC (03:00 Cyprus on that date), once the completed candle is
available. The real readiness invocation on 2026-10-16 returned
`WAITING_FOR_NEW_CANDLES`; no forward observation was created. Date-gate tests
use synthetic fixtures and a mocked clock, not actual future market data.

Only yesterday's completed UTC candle can be recorded on a given day. The
journal refuses historical backfills, stale input, conflicting duplicate
observations and incomplete prior records. Repeated identical observations are
reported as already recorded without overwriting the original. Each accepted
record retains observation time, input hash, used-row hash and rule version.
This local journal is not a tamper-proof or independently timestamped ledger.

## Reproduce the sizing study

Install the full repository dependencies with `python -m pip install -e .`.
Use the frozen CSV and original results from experiment 001's archive, or
recreate experiment 001 before running this study. New output directories are
required. The runner verifies protocol and data hashes before proceeding.

```bash
python scripts/run_exposure_experiment.py \
  --csv /path/to/data/btc_coinbase_daily.csv \
  --prior-results /path/to/original/results \
  --output /path/to/new/exposure-results
python -m pytest tests/test_entry_allocation.py tests/test_signal_journal.py \
  tests/test_strategy_backtest.py tests/test_backtest.py tests/test_verified_market.py -q
```

## On-demand observation on Windows

From a clone of branch `codex/exposure-study-20261016`, with dependencies in
`.venv`, run the following only when a new completed day is available. The
downloader makes public requests without credentials; each download uses a new
directory and does not automatically retry. The journal location stays fixed.

```powershell
$observationUtc = (Get-Date).ToUniversalTime()
$observationEnd = $observationUtc.ToString('yyyy-MM-dd')
$observationFolder = '..\paper-data-' + $observationUtc.ToString('yyyyMMdd-HHmmss')
.\.venv\Scripts\python.exe scripts\fetch_trend_candles.py --start 2019-01-01 --end-exclusive $observationEnd --output $observationFolder
if ($LASTEXITCODE -ne 0) { throw 'Data download failed; observation not recorded.' }
.\.venv\Scripts\python.exe -m tradingagents.signal_journal --csv "$observationFolder\btc_coinbase_daily.csv" --journal '..\prospective-signal-journal'
if ($LASTEXITCODE -ne 0) { throw 'Signal observation failed; inspect the error.' }
```

There is no automatic daily execution or 24/7 deployment. A permanent execution
environment and a scheduling decision would be separate work. Future observations
must be collected before prospective performance can be evaluated.
