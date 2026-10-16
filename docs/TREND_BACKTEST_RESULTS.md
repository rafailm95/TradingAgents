# BTC daily trend experiment 001 — rejected by its predeclared risk screen

This experiment implements a deterministic portfolio simulation separate from
`tradingagents.backtest`, which remains a rating-evaluation tool. No LLM, paid
API, order-placement integration or model-generated trading decision is used.

## Frozen rules and execution

The exact protocol is `docs/TREND_BACKTEST_PROTOCOL.json`, SHA-256
`9e6baf0fe5e1cae4857263677976eb684ad3f2f8550867df83b715b20b5964ba`.
The engine refuses a changed protocol. Rules were recorded before inspecting
the simulation results; there was no parameter search or tuning after results.

- Buy signal at a daily close above SMA200 and above the highest High of the
  previous 20 days (current day excluded from the breakout threshold).
- Sell signal at a daily close below SMA200 or below the lowest Low of the
  previous 10 days (current day excluded from the exit threshold).
- Signals execute at the next daily open with adverse slippage and fees on
  both sides. A remaining position is liquidated at the final close, with costs.
- Long or cash, no leverage, entire simulated balance per entry. This is an
  explicit research baseline, not a recommendation for real capital sizing.
- Starting USD10,000 is a normalization. Cash earns zero interest. Buy-and-hold
  uses the same start/end execution points and transaction costs.

## Data and assumptions

Coinbase Exchange BTC-USD daily candles, 2019-01-01 through 2026-10-15:
2,845 rows, including warmup; 2,480 evaluated days from 2020-01-01. Twelve bounded
public requests supplied a complete daily sequence. Raw responses, request URLs
and hashes were retained. The 257 candles from the earlier pilot exactly match
the overlap in the fresh download. This is not independent exchange verification.

CSV SHA-256: `cd11ea3edba7d5531b716aad3f9bb783ba2439631bf08e3edbe287725a19161c`.

Base costs assume **0.60% fee + 0.10% adverse execution per side**. Stress costs
assume **1.20% fee + 0.25% adverse execution per side**. These are sensitivity
assumptions, not the user's verified fee tier. Frictionless and low-cost
(0.10% fee + 0.05% adverse execution per side) scenarios are also retained.
The execution allowance is a simple combined friction assumption, not a
historical order-book replay. Taxes are excluded.

Sources:
- https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles
- https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees

## Results after assumed transaction costs, before operating expenses and tax

Each window below starts independently at USD10,000. These are chronological
checks, **not blind holdouts**; recent 2026 prices were already seen in the prior
pilot. No parameters were selected using the outcome of any window.

| Window | Trend final USD | Trend return | Trend max drawdown | Buy/hold return | Buy/hold max drawdown |
|---|---:|---:|---:|---:|---:|
| 2020-01-01–2026-10-15 | 49,769.31 | +397.69% | 52.27% | +1,030.24% | 76.67% |
| 2020–2023 | 34,455.00 | +244.55% | 52.27% | +481.94% | 76.67% |
| 2024–2025 | 13,386.54 | +33.87% | 29.50% | +104.03% | 32.10% |
| 2026-01-01–2026-10-15 | 10,005.26 | +0.05% | 14.08% | −7.44% | 39.64% |

Full-window trend: 28 closed trades, 42.86% profitable, net profit factor 1.82.
Win rate alone is not the success criterion. Under the stress cost assumption,
full-window return falls to +227.00% and drawdown rises to 58.30%; the 2024–2025
return falls to +13.50%, while 2026 returns −2.90% on just two trades.

The 2026 base-case profit is only **USD5.26 per simulated USD10,000** before
operating expenses and tax. Subtracting a hypothetical USD120/year, prorated to
288 days, produces **−USD89.36**. This external operating-expense deduction does
not change the simulated position sizes. It is a cost sensitivity, not a measured
cloud bill. The experiment itself incurred zero paid AI calls.

Full-period annual trend returns, with positions carried across years:
2020 +140.58%; 2021 +5.42%; 2022 0.00%; 2023 +36.80%; 2024 +57.01%;
2025 −8.69%; 2026 through 15 October +0.05%.
Annual carried-position results differ from independently restarted windows.

## Decision

**REJECTED_BY_PREDECLARED_SCREEN.** The full-period close-to-close drawdown of
52.27% exceeds the predeclared 35% research threshold. Positive aggregate
historical profit does not override that failure. Buy-and-hold earned more in
the full period and in 2024–2025, while experiencing greater drawdowns.

This does not establish a profitable, live-ready bot. Drawdown can be worse
intraday; signals have no guaranteed stop price. The limited trade sample, one
asset/venue, known historical data and approximate fills constrain inference.
No statistical significance, independent market validation or future returns
have been established. No live execution or persistent service was activated.

The next research question is whether an explicitly limited exposure or
volatility-based sizing rule can improve capital preservation. That must be a
separate preregistered experiment, retaining this failed result and acknowledging
reuse of historical data. It is not an automatic tweak until this test passes.

## Validation and reproduce

**77 focused tests passed**: the new simulator plus existing rating-backtest and
verified-market tests. Checks include delayed execution across adverse gaps,
two-sided hand-calculated fees, terminal liquidation, initial-equity drawdown,
future-data isolation, malformed candles, immutable protocol and independent
return arithmetic. An additional real-data reconciliation matched every daily
equity point across four cost scenarios (2,480 days each), with numerical
differences below USD0.000001. This was a separate calculation, not an independent
human or agent review.

```bash
git clone --branch codex/trend-backtest-20261016 https://github.com/rafailm95/TradingAgents.git
cd TradingAgents
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/fetch_trend_candles.py \
  --start 2019-01-01 --end-exclusive 2026-10-16 --output ../trend-data
.venv/bin/python -m tradingagents.strategy_backtest \
  --csv ../trend-data/btc_coinbase_daily.csv \
  --protocol docs/TREND_BACKTEST_PROTOCOL.json --output ../trend-results
.venv/bin/python scripts/audit_trend_results.py \
  --csv ../trend-data/btc_coinbase_daily.csv --results ../trend-results
.venv/bin/python -m pytest tests/test_strategy_backtest.py tests/test_backtest.py tests/test_verified_market.py -q
```

Use new output directories. The downloader does not automatically retry failed
requests. Frozen data, raw responses, the complete fill/trade/equity records,
metrics and checks are also in the delivered archive, so the original experiment
can be rerun offline without re-downloading market data. A fresh API download
may change if the exchange revises its history; compare hashes.
