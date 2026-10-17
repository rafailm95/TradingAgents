# Batch020 — NR7 daily-close futures results

Native Binance ETHUSDT perpetual, evaluation2024-01-01..2025-12-31; warmup2022, maintraining2023, expandingtraining2023–2024. Historical reused data, not Bybit or forward validation.

New2variants / total50 /25families; 32new design executions; 7527cumulative design+7prior integrity replays=7534known executions. No new integrity replay. ReusedWFAfolds=24.

New full gates: 0/2 pass; individual scenarios 2/24 pass. All10compatible full gates: 0/10. WFA 4/12 scenario passes; fullpass=False.

|Candidate|Base net % / USDT|Stress net % / USDT|Worst12 net % / USDT|Base signal exits|Maximum sampled DD % / actual USDT|
|---|---:|---:|---:|---:|---:|
|sma200_band__vol15_cap50|-2.5783% / -257.83 USDT|-2.9632% / -296.32 USDT|-9.3504% / -935.04 USDT|7|25.8836% / 3077.05|
|regression_trend__fixed50|+5.0610% / +506.10 USDT|+4.1180% / +411.80 USDT|+4.1146% / +411.46 USDT|7|34.3630% / 4657.26|
|keltner_breakout__fixed50|+19.9399% / +1,993.99 USDT|+18.8584% / +1,885.84 USDT|+4.6870% / +468.70 USDT|7|15.8084% / 1786.38|
|obv_breakout__fixed50|+20.1982% / +2,019.82 USDT|+18.9655% / +1,896.55 USDT|+16.4934% / +1,649.34 USDT|8|16.8601% / 2009.79|
|aroon_trend__fixed50|+3.7736% / +377.36 USDT|+2.4561% / +245.61 USDT|+2.4538% / +245.38 USDT|10|30.4266% / 3694.15|
|cci_reversion__fixed50|+15.9148% / +1,591.48 USDT|+13.5758% / +1,357.58 USDT|-12.5172% / -1,251.72 USDT|16|18.1249% / 1923.77|
|funding_carry7_momentum28__fixed50|-2.7158% / -271.58 USDT|-6.8173% / -681.73 USDT|-19.7867% / -1,978.67 USDT|34|35.2354% / 3588.70|
|funding_carry7_momentum28__vol15_cap50|-2.7991% / -279.91 USDT|-4.7026% / -470.26 USDT|-12.8366% / -1,283.66 USDT|34|20.5513% / 2074.87|
|nr7_close10__fixed50|+2.5175% / +251.75 USDT|-1.3111% / -131.11 USDT|-23.4889% / -2,348.89 USDT|29|35.1108% / 3649.76|
|nr7_close10__vol15_cap50|-0.9415% / -94.15 USDT|-2.6318% / -263.18 USDT|-13.4837% / -1,348.37 USDT|29|19.0344% / 1948.37|

Main train-only selected: funding_carry7_momentum28__fixed50. Annual2024/2025 choices: funding_carry7_momentum28__fixed50 → obv_breakout__fixed50.
WFA uses exact capital carry, terminal flatten fees at eachyear boundary; identical019folds reused only after exact identity/capital/date/scenario check. Calendar/WFA periods overlap main evaluation.

Benchmarks over the same fixed evaluation window: benchmark_ETHUSDT_cash_venue_assumption_adverse0: +0.0000% / +0.00 USDT; benchmark_ETHUSDT_buy_hold50_venue_assumption_adverse0: -0.5094% / -50.94 USDT; benchmark_ETHUSDT_buy_hold50_venue_assumption_adverse1: -0.5161% / -51.61 USDT; benchmark_ETHUSDT_buy_hold50_stress_assumption_adverse0: -0.6541% / -65.41 USDT; benchmark_ETHUSDT_buy_hold50_stress_assumption_adverse1: -0.6607% / -66.07 USDT

Costs per side: base5.5bpsfee+2bpsslippage; stress10+10bps.120USDT/year expense included. Real4383funding events; nominal hour-open mark proxy plus adverse5bpsvaluation.35,064tradehours and35,064markhours cover2022–2025. No new data.50%entry cap, fullycash-backed long-or-flat guard. Hypotheticalfilters, unknownpersonal/historicalfees, nohistoricalbooks/fills and noexchangeliquidationmodel.
Cash benchmark0expense; perpetualhold50paysfunding/fees/opex. ManagedWFAcash pays120/year. Drawdowncash is observed peak minus trough at the maximum percentage drawdown, not DD% times initial10000. Maximum cash DD is also retained in CSV/JSON. Hourly sampled DD is not an intrabar execution guarantee.

All10compatible candidates enter centered30dayblock maxmean bootstrap,2000resamples,seed20261017,actualopex.40spot-only candidates excluded as incompatible; priorsearch and reuseddesign/history are not corrected. No statistical/forward confirmation.

129softwaretests (18new); 2,786,608independentwealth events, zeroDecimaldiscrepancy. Allsourcefreezes and523priorfiles preserved. Allnewresults hashverified and envelopepersisted. Allfailuregates retained in evaluation.json.

Next bounded step: audit the singleBybitpacket if available; otherwise preregister2026nativefutures dataextension for unchanged candidate rules, coverage first and PnL only after input/freeze publication. Do not tune020 or rerunidentical inputs toseekgreen. No new prospective cohort or real orders.

Preregistration: https://github.com/rafailm95/TradingAgents/commit/2ab77e2141b849faa9f3bc676e509f38a5969fc5
Rules/rationale: docs/NR7_FUTURES_020.json; https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/narrow-range-day-nr7
