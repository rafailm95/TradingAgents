# Peer-relative reversion016 results

Completed all174preregistered simulations. One of6asset/variant pairs passes the historical gate: LTC peer_reversion60__vol15_cap50. None passes the complete historical-plus-delay gate. Preserve this positive but execution-sensitive idea; no retuning or promotion.

Evaluation2024-01-01..2026-10-15,independent10000USDspotaccounts. Basefee60bps+slippage10bps/side;stress120+25;opex120USD/year. Not Bybit fees or perpetual returns. Total-period returns,not annual.

| Asset | Sizing | Base net%/USD | Stress net%/USD | Worst6scenarios%/USD | Worst DD%/actualUSD |
|---|---|---|---|---|---|
| BTC | fixed50 | -6.14% / -614.44 USD | -9.69% / -968.81 USD | -9.69% / -968.81 USD | 16.69% / 1,726.32 USD |
| BTC | vol15_cap50 | -6.38% / -637.55 USD | -9.25% / -924.52 USD | -9.58% / -958.31 USD | 14.21% / 1,442.68 USD |
| ETH | fixed50 | -41.78% / -4,177.89 USD | -48.50% / -4,849.94 USD | -56.00% / -5,599.58 USD | 56.00% / 5,599.58 USD |
| ETH | vol15_cap50 | -25.52% / -2,552.19 USD | -29.66% / -2,966.00 USD | -34.58% / -3,457.93 USD | 34.58% / 3,457.93 USD |
| LTC | fixed50 | +11.71% / +1,171.42 USD | +0.22% / +22.13 USD | -18.68% / -1,868.13 USD | 34.86% / 3,993.57 USD |
| LTC | vol15_cap50 | +18.30% / +1,830.36 USD | +10.97% / +1,096.86 USD | -6.32% / -632.45 USD | 18.77% / 2,040.62 USD |

LTCvol:base+18.3036%/1830.36USD,stress+10.9686%/1096.86USD;14completed trades. Lag1stress-5.0691%/-506.91USD;lag2stress-6.3245%/-632.45USD;lag2base-0.2377%/-23.77USD. Full,validation,recent windows pass both costs, but3delayprofit gates fail. Main2020–2023selector chosevolforETH/LTC andcashforBTC. This selection and the historical windows are reused research history,not freshholdout.

Annual expanding WFA2022..2026-10-15:
- BTC-USD:base-5.746201% (-574.62USD);stress-5.746201% (-574.62USD).
- ETH-USD:base-27.018798% (-2701.88USD);stress-31.018115% (-3101.81USD).
- LTC-USD:base19.338881% (1933.89USD);stress7.535861% (753.59USD).

BTCWFA remainedcash everyyear;the loss is managedopex only. LTCvolselectedeveryfold. WFA overlapsfixedwindow;no addition/independenceclaim.

All46candidates perasset retained,including old stronger ideas and allfailedgates. Conditional46candidate blockbootstrap p~.206–.420vscash,.556–1.000vshold50. Operatingexpense excluded;priorsearchnotcorrected. Gates use originalbeforeexternalexpense closeDD;reportedcashDD usesdailyexpenseallocationdiagnostic.35%researchgate is not user risk approval.

174wealthaudits,194382auditpoints,maxerror5.09317032993e-11USD.170preflighttests,25new.7338historical scenario executions,46variants,23families;correlated repetitions,not independent evidence.

Freezeb215ddf0986511c619144ddca6202d115316bb34324e6a1beee2fc8974a70c49;publishedbeforeoutcomesatd38e671fee368f7118e1c884f1d126bf39fc1863. Sourcesunchangedafteroutcomes. Noorders,nocohortchanges.013Bybitstillawaitsonepacket.

Reproduce from repository root with the pinned Python3.12,numpy2.3.5,pandas2.2.3,dotenv1.2.4 environment:

```bash
python scripts/run_peer_reversion_lab.py --output NEW_OUTPUT_DIRECTORY --reference-root PATH_TO_011_FULL_RESULTS --reference-015-root PATH_TO_015_FULL_RESULTS --freeze-sha b215ddf0986511c619144ddca6202d115316bb34324e6a1beee2fc8974a70c49
```

Primary conceptual source:https://www.newyorkfed.org/research/staff_reports/sr187.html. Temporary versus permanent declines motivate competing effects;this is a custom long/flat crypto rule,not a replication or arbitrage/cointegration claim.
