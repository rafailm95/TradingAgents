# BTC strategy research 003 — bounded 16-candidate comparison

## Result and decision

Completed the preregistered matrix: 8 signal families × 2 entry sizing methods ×
4 friction assumptions × 5 chronological windows = **400 matrix runs**. An
additional 160 training calculations and 10 annual evaluations implement the
predeclared historical walk-forward selector. No candidate or parameter was
added after seeing the outcomes. The original failed experiments are preserved.

One candidate passes this study's historical screen:
`sma200_band__vol15_cap50`. It remains **exploratory**, because it was identified
after comparing the reused 2024–2026 history. It is not the train-only winner.

The train-only winner is `breakout20__vol15_cap50`, selected and written to
`selection_before_evaluation.json` before evaluation. It earns +7.18% after
operating expense in 2024–2026 under base friction, but **−0.21% under stress**.
Thus, historical selection did not produce a robust confirmed winner.

## Exploratory SMA200 candidate

Enter at next open when the completed close exceeds 1.01 × SMA200. Exit at next
open when the completed close is below 0.99 × SMA200. At entry spend
`min(0.5, 0.15 / annualized_sample_vol60)` of available cash, including fees.
Volatility uses 60 completed daily simple returns and sqrt(365.25).
Zero observed volatility uses 50%. No leverage, shorts or rebalancing.

The 15% reference is **not** a promised portfolio volatility or maximum loss.
Exposure can drift above entry allocation as the held asset rises.

Each window starts flat with hypothetical USD10,000. Returns below deduct
transaction costs and an external USD120/year prorated operating assumption,
before tax. Drawdowns use the trading equity at daily closes before the external
operating deduction; intraday losses may be larger.

| Window | Base return after operating | Stress return after operating | Base close DD | Stress close DD | Trades |
|---|---:|---:|---:|---:|---:|
| 2020–2026-10-15 | +93.13% | +76.48% | 27.85% | 29.41% | 20 |
| 2024–2025 | +11.65% | +7.62% | 14.91% | 16.40% | 8 |
| 2026 through Oct 15 | +3.71% | +3.00% | 3.15% | 3.13% | **1** |
| 2024–2026-10-15 | +16.01% | +11.01% | 14.91% | 16.40% | 9 |

2026 base profit is USD370.51 after operating; stress profit is USD300.21.
This period has only one completed trade. Annual income, a repeatable edge,
prospective paper performance and future profit are not established.

The initially 50%-invested buy-and-hold benchmark earns +45.76% in 2024–2026
with 39.57% closing drawdown, versus the exploratory candidate's +16.01% and
14.91%. Benchmark operating expense is zero; both pay transaction friction.
The allocation/risk paths differ: this is not a risk-matched alpha comparison.

## Walk-forward and multiplicity diagnostics

For each year 2022–2026, the predefined selector uses 2020 through the preceding
December only. It selects `breakout20__vol15_cap50` each year. Positions are
liquidated at year end; equity after annual operating debit carries forward.
Across the complete 2022–2026 replay the net returns are +13.43% base and +2.24%
stress, with closing drawdowns after those debits of 16.86% and 20.54%.
The replay has losing years (including 2025); it is not a steady-income system.

Exploratory centered circular-block maximum-mean tests across all 16 candidates
used 2,000 shared-date resamples and block lengths 10, 30 and 60. For base-case
2024–2026 daily arithmetic returns, no candidate has positive average excess
return over buy-and-hold50 (reported p=1). Versus zero-yield cash, exploratory
family-adjusted p-values are 0.245, 0.277 and 0.274. This diagnostic does not
establish statistical significance, account for past research decisions, or
include the operating expense. No predictive confidence is inferred.

## Validation and provenance

- Same 2,845-row Coinbase BTC-USD snapshot, 2019-01-01 through 2026-10-15.
- Dataset SHA256: `cd11ea3edba7d5531b716aad3f9bb783ba2439631bf08e3edbe287725a19161c`.
- Protocol SHA256: `848a6696b9899a9d7817f1997001bf7a5996688b77b2d54c699b20c08127ed97`.
- Protocol was committed locally before result generation.
- 64 focused numerical tests passed with `--noconftest`. The repository's full
  application fixture suite was not run: it imports unrelated provider
  dependencies absent from this runtime. This is not a full-repository CI pass.
- Direct-slice and EMA-recurrence signal oracles, future-prefix isolation,
  next-open timing, lagged sizing, accounting conservation, timed exits,
  cost monotonicity and selector constraints were exercised.
- 410 separate wealth-recurrence checks cover **481,818 daily points**; maximum
  numerical discrepancy USD0.00000000175. This is a second arithmetic method,
  not independent human/agent review.
- 20 original-strategy window/cost curves were replayed against the existing
  simulator. No broker credentials, LLM calls, orders or paid service calls.
- First launcher attempt lacked python-dotenv and stopped before simulation;
  the isolated dependency path resolved it. No results-driven rule changes.

Base = 60 bps fee + 10 bps adverse execution per side. Stress = 120 + 25 bps.
Low-cost and frictionless scenarios are retained as sensitivities, not used to
declare a winner. These are assumptions, not verified account fees.
No fresh cross-venue verification, order-book/volume model, execution delay,
partial fills, outage simulation, taxes or cash interest.

## Next bounded step

Freeze two clearly labeled prospective signal observers: the train-selected
breakout candidate and the exploratory SMA200 candidate. Preserve their
different selection provenance. New observations must be after 2026-10-16;
the previously established first candle is 2026-10-17, available from
2026-10-18 00:00 UTC. Do not backfill historical observations as if collected
live. No prospective records, scheduler, paper fills or 24/7 service were
created by this experiment. The old `signal_journal` still implements only the
previous fixed-50% breakout rules and must not be mislabeled as this study.

## Reproduction

Use a virtual environment with numpy, pandas, python-dotenv and pytest. Core
research modules do not need LLM provider packages. On Windows substitute
`.venv\Scripts\python.exe` for python. Use a new output directory each time.

```bash
python scripts/run_strategy_lab.py --csv /path/to/btc_coinbase_daily.csv --output /path/to/new-results
python -m pytest --noconftest tests/test_strategy_lab.py tests/test_strategy_backtest.py tests/test_entry_allocation.py -q
```

`all_runs.json.gz` holds all 400 daily curves, fills and trades.
`walk_forward.json.gz` retains each fold's training metrics, choices, fills,
curves before the explicit operating debit, and the debit record.
`metrics.csv`, `summary.json`, `audits.json` and `experiment_register.json`
support the report. Each independent matrix window resets USD10,000; overlapping
windows must not be summed or treated as independent samples.

## Primary references checked 2026-10-16

- Coinbase Advanced fees: https://help.coinbase.com/en-gb/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees
- Bailey et al., The Probability of Backtest Overfitting: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf

The fee source explains fee-tier/product dependence; it does not validate the
assumed rates used here. The paper motivates retaining the entire experiment
family and separating selection from evaluation; it is not evidence that
these trading rules are profitable.
