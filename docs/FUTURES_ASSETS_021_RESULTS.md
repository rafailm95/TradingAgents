# Batch021: BTC / SOL / XRP native futures extension

Binance USD-M perpetual. Data2022-01-01..2025-12-31; maintrain2023, expandingtrain2023–2024, fixed evaluation2024-01-01..2025-12-31. Independent10000USDT accounts perasset/candidate, not a combinedportfolio.

0new strategy variants;50total/25families. 250new executions, 7777cumulative design+7prior integrity replays=7784known executions. 0/12fullasset-candidatepasses; 0/144individualscenario passes. Crossassetfullpasses: [].

|Asset/candidate|Base net|Stress net|Worst12 net|Maxsampled DD / actualcash|Base signal exits|Fullpass|Failed gate counts outof12|
|---|---:|---:|---:|---:|---:|---|---|

Excluded before PnL: {"SOLUSDT": {"reason": "Πραγματική αλλαγή funding σε 4 και 2 ώρες τον Νοέμβριο 2022· ο παγωμένος έλεγχος απαιτεί 8 ώρες. Διατηρούνται 4.458 πραγματικά γεγονότα, χωρίς προσομοίωση SOL.", "raw_error": "ValueError: Changed funding cadence or malformed row", "status": "EXCLUDED_BEFORE_PNL", "verified_monthly_archives": 144, "verified_daily_archives": 10}}

|BTCUSDT / sma200_band__vol15_cap50|+8.64% / +863.59 USDT|+7.97% / +796.97 USDT|-1.82% / -182.26 USDT|21.87% / 2,684.42 USDT|8|False|FEWER_THAN_20_SIGNAL_EXITS:12/12, NONPOSITIVE_NET:4/12|
|BTCUSDT / regression_trend__fixed50|+29.03% / +2,902.92 USDT|+28.18% / +2,817.58 USDT|+28.17% / +2,817.15 USDT|14.37% / 1,709.85 USDT|5|False|FEWER_THAN_20_SIGNAL_EXITS:12/12|
|BTCUSDT / keltner_breakout__fixed50|+17.04% / +1,703.95 USDT|+15.70% / +1,569.56 USDT|+15.69% / +1,569.32 USDT|16.91% / 2,125.91 USDT|9|False|FEWER_THAN_20_SIGNAL_EXITS:12/12|
|BTCUSDT / obv_breakout__fixed50|+14.69% / +1,469.11 USDT|+12.52% / +1,251.93 USDT|+12.52% / +1,251.71 USDT|15.15% / 1,908.82 USDT|15|False|FEWER_THAN_20_SIGNAL_EXITS:12/12|
|BTCUSDT / aroon_trend__fixed50|+24.19% / +2,418.57 USDT|+22.29% / +2,228.57 USDT|+9.17% / +916.99 USDT|28.16% / 3,498.09 USDT|12|False|FEWER_THAN_20_SIGNAL_EXITS:12/12|
|BTCUSDT / cci_reversion__fixed50|+7.05% / +705.03 USDT|+5.03% / +503.00 USDT|-3.55% / -354.55 USDT|14.86% / 1,569.39 USDT|15|False|FEWER_THAN_20_SIGNAL_EXITS:12/12, NONPOSITIVE_NET:4/12|

BTCUSDT mainselector=cash:base +0.00% / +0.00 USDT,stress +0.00% / +0.00 USDT; nextselector=obv_breakout__fixed50. WFA base -5.43% / -542.88 USDT,stress -6.14% / -613.87 USDT,passes 0/12.

|XRPUSDT / sma200_band__vol15_cap50|+39.43% / +3,942.91 USDT|+38.41% / +3,841.21 USDT|+34.87% / +3,487.43 USDT|38.06% / 8,335.81 USDT|11|False|DRAWDOWN_OVER_35PCT:12/12, FEWER_THAN_20_SIGNAL_EXITS:12/12|
|XRPUSDT / regression_trend__fixed50|-18.97% / -1,897.18 USDT|-19.68% / -1,967.96 USDT|-23.14% / -2,314.05 USDT|37.59% / 5,141.39 USDT|7|False|NONPOSITIVE_NET:12/12, FEWER_THAN_20_SIGNAL_EXITS:12/12, DRAWDOWN_OVER_35PCT:8/12|
|XRPUSDT / keltner_breakout__fixed50|+126.11% / +12,610.54 USDT|+124.30% / +12,429.59 USDT|+65.21% / +6,520.95 USDT|33.58% / 8,536.49 USDT|6|False|FEWER_THAN_20_SIGNAL_EXITS:12/12|
|XRPUSDT / obv_breakout__fixed50|+125.40% / +12,540.36 USDT|+122.77% / +12,276.67 USDT|+105.81% / +10,580.83 USDT|33.42% / 9,607.39 USDT|9|False|FEWER_THAN_20_SIGNAL_EXITS:12/12|
|XRPUSDT / aroon_trend__fixed50|+103.47% / +10,346.93 USDT|+101.33% / +10,133.30 USDT|+43.42% / +4,341.91 USDT|30.20% / 5,682.12 USDT|8|False|FEWER_THAN_20_SIGNAL_EXITS:12/12|
|XRPUSDT / cci_reversion__fixed50|+33.40% / +3,339.61 USDT|+31.19% / +3,119.05 USDT|+12.30% / +1,230.05 USDT|18.19% / 2,235.89 USDT|13|False|FEWER_THAN_20_SIGNAL_EXITS:12/12|

XRPUSDT mainselector=cash:base +0.00% / +0.00 USDT,stress +0.00% / +0.00 USDT; nextselector=obv_breakout__fixed50. WFA base -6.52% / -651.53 USDT,stress -7.10% / -710.01 USDT,passes 0/12.


Costs per side:5.5bpsfee+2bpsslippage baseline;10+10stress.120USDT/year expense. Actualheld-position funding, hour-open mark proxy and adverse5bpsvaluation. Fullycash-backed longflat,50%entrycap, hypotheticalfine-lotfilters. Personalfees/historicalrules/margin unverified; noexchangeliquidationmodel or historicaldepth/fill evidence.
All12scenarios neednet>0,DD<=35%,>=20signal/timeexits andcompleteaudits. Traineligibility>=10exits,bothcostpositive,DD<=35%. Terminalforcedclosesexcluded. WFA annualflatwithcostandexactcashcarry; managedcashpays120/year; idlecashbenchmark0expense. Hold50paysfunding/fees/expense. DDamount=observedpeak-troughatmaximumpercentageDD; maximumcashDDretainedseparately.
Sixfrozen017variants fullytestedperasset includingoldstrengthsandfailures. FourothernativeETHvariants019/020and40spot-onlyvariants nottestedhere; allpriorresultsretained. Conditionalmultiple-comparison diagnostics covertested6perasset/jointup-to18, shared30dayblocks,2000resamples,actualopex. They do notcorrectprior50variantsearch/design selection. Samehistoricaldates andcrossassetcorrelations are notindependentconfirmation.
128softwaretests17new;125syntheticmatrixexecutionsnotcountedasmarketresearch. 19869554newwealthevents,zeroDecimalerror. FrozenBybit013/014andsevenprospectivecandidates untouched.
Source: https://github.com/binance/binance-public-data . Exactdata/source/testpins and reproduciblecommands in research/experiments/021. Fullcurves/fills/funding/events persistedwithartifactreceipts. No realorders or keys. Next: oneBybitpacket audit; otherwise separatelyfrozen actualSOLfundingcadence support withunchangedstrategy/gates.

Positive-discovery count:9of12testedasset-candidatepairs remainnetpositiveinall12cost/lag/fundingscenarios, but0of12passallcriteria. Conditionalbootstrap pabout0.147–0.196vscash and1vshold50 concernsarithmeticmeandailyreturns,notterminalcompoundwealth; itdoesnotcorrecttheprior50variantsearch. Dailyreturncompoundreconciliationerror<=2.44e-10USDT.
