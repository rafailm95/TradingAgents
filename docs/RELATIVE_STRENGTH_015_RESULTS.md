# Relative-strength015 results

Completed the preregistered original attempt:174new historical spot simulations,2new variants,3assets. No new candidate passed the full historical/delay screen. All previous frozen studies and both forward cohorts remain unchanged.

Evaluation:2024-01-01..2026-10-15. Each independent account starts10000USD. Base fee60bps+slippage10bps per side; stress120+25bps.120USD/year operating expense included in net results. Coinbase USD spot; no Bybit/funding validation.

| Asset | Sizing | Base net% / USD | Stress net% / USD | Worst of6cost/lag scenarios% / USD | Worst sampled DD% / USD |
|---|---|---:|---:|---:|---:|
| BTC | Σταθερή θέση 50% | -24.64% / -2,463.95 USD | -49.07% / -4,907.28 USD | -49.07% / -4,907.28 USD | 52.08% / 5,534.86 USD |
| BTC | Θέση βάσει μεταβλητότητας | -16.52% / -1,651.68 USD | -35.08% / -3,507.98 USD | -35.08% / -3,507.98 USD | 37.60% / 3,912.10 USD |
| ETH | Σταθερή θέση 50% | -2.36% / -235.68 USD | -26.73% / -2,673.48 USD | -30.33% / -3,032.75 USD | 41.24% / 4,279.76 USD |
| ETH | Θέση βάσει μεταβλητότητας | -1.37% / -136.63 USD | -13.79% / -1,379.39 USD | -13.84% / -1,383.54 USD | 23.21% / 2,378.54 USD |
| LTC | Σταθερή θέση 50% | -48.19% / -4,818.99 USD | -58.39% / -5,839.08 USD | -58.39% / -5,839.08 USD | 62.58% / 6,458.09 USD |
| LTC | Θέση βάσει μεταβλητότητας | -21.20% / -2,119.87 USD | -28.12% / -2,811.84 USD | -28.12% / -2,811.84 USD | 31.77% / 3,191.96 USD |

The best new evaluation pair was ETH volatility sizing, but it still lost1.3663% at base costs and13.7939% at stress costs. All six asset/variant pairs failed. The training-only main selector chose cash forBTC/LTC and volatility sizing forETH; the latter subsequently lost in evaluation.

Annual expanding walk-forward2022..2026-10-15 net results:
- BTC-USD: base -16.3319% (-1633.19USD);stress -21.3195% (-2131.95USD).
- ETH-USD: base -0.6274% (-62.74USD);stress -22.9433% (-2294.33USD).
- LTC-USD: base -5.7462% (-574.62USD);stress -5.7462% (-574.62USD).

LTC walk-forward remained cash in every fold; its574.62USD loss is the explicitly modeled managed-research operating expense. Passive idle cash benchmark has zero expense. WFA results and fixed evaluation windows are different experiments and must not be combined.

The descriptive comparison retains all44variants per asset. Prior ETH OBV fixed50 remains a more promising exploratory family: its minimum net return across the six old cost/lag evaluation scenarios is14.4789% (+1447.89USD). This is reused historical evidence, not a new Bybit result, untouched validation or forecast. Other retained strengths and every failed gate are in per-asset assessment.json.

The44candidate conditional bootstrap produces exploratory p-values about0.206..0.394 versus cash and0.544..1.000 versus50%buy-and-hold. This does not establish significance after the whole search history; expense is excluded from this inherited diagnostic. All signals remain correlated and the three surviving assets are a constrained universe.

Accounting:174independent wealth audits;194,382daily audit points;maximum discrepancy4.91127138957e-11USD.145preflight software tests passed,24new.

Historical simulation execution count6990+174=7164;44unique sizing variants,22families. Overlapping histories/cost/lag/WFA runs are not independent hypotheses.

Protocol:docs/RELATIVE_STRENGTH_015.json. Freeze SHA256:05cb88bdf7569c5ee8bf0f71a38df1cb9fda6ac6195907ff0dd68a626305a9d7. Published before execution atremote commit eb954e4fd9f90695ce48275ad15718aa3bd9d7f1.

Rules, parameters and sources were not changed after seeing results. No new forward cohort, real orders or paid services. Await the already-requested single BYBIT_SEND_THIS.zip for the separately frozen013Bybit transfer.

Primary rationale: https://economics.yale.edu/research/common-risk-factors-cryptocurrency (relative momentum motivation, not a replication of the paper).
