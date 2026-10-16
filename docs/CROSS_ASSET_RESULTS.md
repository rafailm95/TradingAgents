# Cross-asset experiment009 — all40 candidates on ETH and LTC

Frozen protocol before evaluation: `a53b6f3aa8305752680d88d55b8fd0475cf476c18e8f7ba002d88fee476501f9`. Input manifest and source hashes are in `research/experiments/009/run_manifest.json`.

Completed2026-10-16: **2020 simulations**, **2554500 daily conservation checks**, **291 targeted software tests passed**. No real orders or paid model calls. Four ETH variants pass the historical and1/2day extra-delay screens; none on LTC and none across both assets. These are post-hoc historical findings on correlated reused dates, not forward validation.

Each public Coinbase series has2845 daily candles2019-01-01..2026-10-15, twelve GET pages, no missing dates or retries. Data have not been independently cross-venue verified. Train2020–2023; validation2024–2025; recent2026throughOct15; evaluation2024throughOct15. Each window starts flat with10000USD. Base fee60bps plus slippage10bps per side; stress120bps plus25bps. Strategy returns below deduct120USD/year prorated external operating expense, before tax. Cash/buy-hold benchmarks have no bot operating expense. Entry allocation may drift above50% while held. Daily-close drawdowns exclude the external operating deduction; intraday losses can be larger. WFA drawdowns include the actual modeled year-end debit. Historical closed-trade counts can include terminal forced liquidation.

## ETH post-hoc screen passes

| Variant | Evaluation base net | Evaluation stress net | Worst delayed stress net | Stress close DD | Evaluation closed trades | Recent closed trades |
|---|---:|---:|---:|---:|---:|---:|
| aroon_trend__fixed50 | +11.66% | +3.29% | +6.25% | 31.51% | 10 | 1 |
| aroon_trend__vol15_cap50 | +5.60% | +1.55% | +2.64% | 18.03% | 10 | 1 |
| obv_breakout__fixed50 | +46.05% | +35.95% | +14.48% | 8.42% | 9 | 2 |
| obv_breakout__vol15_cap50 | +22.65% | +18.32% | +8.08% | 4.48% | 9 | 2 |

Returns are cumulative, not annualized. The1–2recent trades are a small sample. These four ETH candidates have NOT been enrolled in the BTC forward cohort.

## Train-only selection and chronological WFA

The ETH train-selected breakout20__fixed50 loses **−8.23%base /−15.68%stress** in evaluation. LTC selects cash because no variant is train-eligible; its0% cash benchmark is not a profitable operating bot. WFA includes120USD/year even when the selected strategy holds cash.

| Asset | WFA2022–2026 base net | WFA stress net |
|---|---:|---:|
| ETH-USD | +13.37% | -0.70% |
| LTC-USD | -26.94% | -29.06% |

The40-candidate block-bootstrap diagnostics are exploratory, exclude operating expense, and do not correct all previous research/asset choices. They are not proof of an edge. Every failed gate, all440matrix metrics and160delay metrics per asset, train selection and WFA choices are retained under research/experiments/009. Full curves and audit detail are preserved in the evidence archive.

## Forward continuation

Added the five previously identified BTC variants in a separate frozen exploratory cohort008: ADXfixed50, Aroonfixed50, Aroonvol15, CMOvol15 and squeeze-breakoutvol15. Their previous delay failures remain explicit. Together with the original two, seven distinct hypotheses will be observed in separate virtual accounts. No genuine forward observations exist at setup; first eligible record is2026-10-18T00:00Z. Read docs/EXPANDED_PAPER_AUTOMATION.md for pins, isolation, persistence and the180day/20exit forward milestone. The milestone is not statistical proof.

RESOLVED: New isolated cohort and complete frozen cross-asset experiment.
OPEN: No prospective profitability; train-selected ETH and both stress WFA results fail.
IMPLEMENTATION_READY: Public-data research and virtual accounting only.
MATERIAL_BLOCKER: Historical passes are post-hoc; no future evidence.
NEXT_IMPLEMENTATION_SLICE: First eligible paper observation; preregistered weekly-confirmation batch011.
DONE_CONDITION: Verified durable publication and enabled daily/weekly tasks; research remains ongoing.
EXECUTION_ENVIRONMENT: Python3.12, pinned requirements-research.txt, fresh dedicated checkout.
REQUIRED_MODE: Research and paper only; no real orders.
