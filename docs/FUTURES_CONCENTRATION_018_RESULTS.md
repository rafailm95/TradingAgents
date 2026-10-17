# Futures018 contribution-concentration diagnostics

Descriptive analysis of existing Binance ETHUSDT outputs for 2024–2025, not new simulations or strategy rules. Initial capital: 10,000 USDT per original path. Fixed-size contribution removals are not causal missing-fill counterfactuals. All original gates and the 2023 cash selection remain unchanged. No new walk-forward run was performed; calendar attribution is not walk-forward validation.

| Candidate | Original baseline | Baseline without best trade | Worst12 without best trade | Worst12 without top two | Base signal exits | Descriptive passes |
|---|---|---|---|---|---|---|
| Aroon | +3.77% / +377.36 USDT | -18.40% / -1,839.70 USDT | -19.34% / -1,934.19 USDT | -29.45% / -2,945.49 USDT | 10 | 0/12 |
| CCI | +15.91% / +1,591.48 USDT | +9.26% / +926.42 USDT | -16.21% / -1,620.77 USDT | -19.64% / -1,964.09 USDT | 16 | 8/12 |
| Keltner | +19.94% / +1,993.99 USDT | +7.13% / +713.04 USDT | -7.88% / -788.45 USDT | -15.36% / -1,535.70 USDT | 7 | 4/12 |
| OBV | +20.20% / +2,019.82 USDT | -0.99% / -98.73 USDT | -2.03% / -203.44 USDT | -16.56% / -1,656.46 USDT | 8 | 8/12 |
| Regression | +5.06% / +506.10 USDT | -4.97% / -496.93 USDT | -5.76% / -576.24 USDT | -14.62% / -1,461.54 USDT | 7 | 8/12 |
| SMA200 / vol15 | -2.58% / -257.83 USDT | -7.31% / -731.33 USDT | -13.96% / -1,396.01 USDT | -17.44% / -1,743.85 USDT | 7 | 0/12 |

All12 descriptive passes: 0/6. Original historical gates: 0/6. All 72 candidate paths and five benchmarks retained. The descriptive filter requires original positive net, positive static remainder after the best profitable trade, and both calendar years positive. Top-two removals are a separate diagnostic, not an adjusted gate.

Costs: 5.5 fee + 2 slippage bps/side baseline; 10 + 10 stress; 120 USDT/year operating expense. Preserve 0/1/2-day feed lags and both funding valuations. Funding rates are observed; settlement marks and execution rules are modeled. No order book, historical fill, personal-fee or liquidation validation. All six compatible native-futures variants are retained; 40 other variants lack comparable native Binance outputs. No p-values or independence claim. Zero new strategies; 46 variants, 23 families; 7,427 design runs plus two prior recovery replays, unchanged.

Pre-analysis freeze commit: 9f7873d8d73a4bb509a19dd6e6c03c869c892e61; freeze SHA256: 6324e9822fbfc01733c9384bf46d4d2048f12adbcabf9aefae2e4e415a0591b8. Primary methodological context: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf . This is not an implementation of PBO. Data/derived analysis CC BY-NC-SA 4.0.
