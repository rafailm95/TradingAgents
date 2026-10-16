# Binance perpetual 017 results

Native ETHUSDT data for 2022–2025: 35,064 trade hours, 35,064 mark hours and 4,383 funding events. Verified 144 monthly and four daily official archives. Recovered 48 missing mark hours from official daily data; 48 overlapping hours agree exactly. BTC was blocked by network access and LTC had 120 missing trade hours; neither receives a return score.

Completed 89 runs: 12 training, 72 evaluation and five benchmarks. 0 of six variants pass all 12 historical scenarios. Training in 2023 selected cash because all six had fewer than 10 signal exits (1–8), despite positive profit under both costs. Evaluation covers 2024-01-01 through 2025-12-31. Each account starts with 10,000 USDT. Returns are for the whole period, not margin ROI or forecasts.

| Candidate | Base net % / USDT | Stress net % / USDT | Worst of 12 scenarios | Worst sampled DD % / actual USDT | Base signal exits | Historical pass |
|---|---|---|---|---|---|---|
| sma200_band__vol15_cap50 | -2.58% / -257.83 USDT | -2.96% / -296.32 USDT | -9.35% / -935.04 USDT | 25.88% / 3,077.05 USDT | 7 | False |
| regression_trend__fixed50 | +5.06% / +506.10 USDT | +4.12% / +411.80 USDT | +4.11% / +411.46 USDT | 34.36% / 4,657.26 USDT | 7 | False |
| keltner_breakout__fixed50 | +19.94% / +1,993.99 USDT | +18.86% / +1,885.84 USDT | +4.69% / +468.70 USDT | 15.81% / 1,786.38 USDT | 7 | False |
| obv_breakout__fixed50 | +20.20% / +2,019.82 USDT | +18.97% / +1,896.55 USDT | +16.49% / +1,649.34 USDT | 16.86% / 2,009.79 USDT | 8 | False |
| aroon_trend__fixed50 | +3.77% / +377.36 USDT | +2.46% / +245.61 USDT | +2.45% / +245.38 USDT | 30.43% / 3,694.15 USDT | 10 | False |
| cci_reversion__fixed50 | +15.91% / +1,591.48 USDT | +13.58% / +1,357.58 USDT | -12.52% / -1,251.72 USDT | 18.12% / 1,923.77 USDT | 16 | False |

The descriptive opportunity ranking preserves positive candidates even when a formal gate fails. It is computed after viewing results and does not replace the frozen training selection. All failures and every scenario remain in evaluation.json.

Cost assumptions per side: 5.5 bps fee plus 2 bps slippage in the baseline, and 10 plus 10 bps in stress; operating expense is 120 USDT/year. Funding uses actual archived rates and held quantity with an hourly mark-open proxy and a separate adverse 5 bps valuation. Timestamp offsets of 0–31 ms are retained and mapped to the nominal eight-hour boundary, without position changes there. Hypothetical fine-lot filters use 1e-8 precision; Binance exchangeInfo returned HTTP 451 and was not bypassed. Historical fills, order books and personal fees are unavailable. A fully cash-backed guard is used; it is not an exchange liquidation model. Signals are daily, long or flat; no shorts were tested.

Validation: 78 software tests passed, including 25 new tests; 7,706,153 independent wealth events checked with maximum error 0 USDT. All 89 result-file hashes were verified. Cumulative design executions: 7,427, plus two integrity replays (7,429 total executions), with 46 unique variants in 23 families. Correlated, overlapping tests are not independent evidence. Frozen sources were not changed after outcomes. Bybit 013 and both prospective cohorts remain unchanged.

Pre-outcome freeze: `59291edfbb05990fd32ebd0be369ac22be1c4c75842a2d6e0a85fd5b5797c807` at commit `4c788ab5861dc7bc10fcf5d42f74f80155298ef9`. Training selection published before evaluation at `6e6ee508e1cf244fa80d239ef47cab8b9805b31e`, selection SHA256 `5a60dfc9c11d3cb286adea86a62533be2231dbcf314598f9560791b763012895`.

Reproduction, from the repository root with the pinned runtime:

```bash
python scripts/run_binance_replay_017.py --input INPUT.json.gz --sha256 cccf3ff868465439ede973dd505c95d906c9e6eb9a9c31263c040fd053ccd00e --engine-freeze-sha256 59291edfbb05990fd32ebd0be369ac22be1c4c75842a2d6e0a85fd5b5797c807 --stage train --output NEW_TRAIN
python scripts/run_binance_replay_017.py --input INPUT.json.gz --sha256 cccf3ff868465439ede973dd505c95d906c9e6eb9a9c31263c040fd053ccd00e --engine-freeze-sha256 59291edfbb05990fd32ebd0be369ac22be1c4c75842a2d6e0a85fd5b5797c807 --stage evaluate --training-directory NEW_TRAIN --selection-sha256 5a60dfc9c11d3cb286adea86a62533be2231dbcf314598f9560791b763012895 --output NEW_EVALUATION
```

Source: [Binance Vision public archives](https://github.com/binance/binance-public-data). Dataset and derived analysis: CC BY-NC-SA 4.0, for personal, non-production research. No exchange endorsement is implied. Source code retains its repository license. No claim of Bybit profitability.
