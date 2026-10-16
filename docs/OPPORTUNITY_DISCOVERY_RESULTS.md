# Opportunity discovery012 and Bybit perpetual preparation

User confirmed Bybit Global and Futures/Perpetuals. New measurement assumptions:10,000USDT equity,1x research exposure,1,000/5,000USDT order-size scenarios. This does not establish the user's margin mode, fee tier or loss tolerance.

## Actual access result

Zero real Bybit order-book snapshots or funding events were obtained. Mainnet spot book and linear instrument probes returned HTTP200 with an HTML Site Unavailable page. Raw response, timestamps and hash are retained. No network restriction was bypassed. API credentials are unnecessary for these public endpoints and do not remedy this non-JSON response.

## Positive discovery result

All126 asset-candidate pairs (42 variants per asset) were ranked. No new strategy simulations or independent evidence were created. Pareto tiers compare worst net return and worst drawdown across six base/stress ×0/1/2-day delay scenarios. Original gate failures and original train selection remain visible. Up to three distinct positive families are shortlisted per asset. This is post-hoc discovery on Coinbase USD spot prices, NOT Bybit perpetual performance.

Period:2024-01-01 to2026-10-15, initial10,000USD per independent scenario. Base:60bps fee+10bps slippage each side; stress:120+25bps. Modeled expense120USD/year. Returns below are cumulative, not annual. Drawdowns additionally accrue expense daily and cash amounts are computed from their actual historical peaks.

| Asset / strategy | Base PnL | Stress PnL | Worst of6 | Stress drawdown / amount | Original all-gates pass |
|---|---:|---:|---:|---:|---|
| BTC-USD / sma200_band__vol15_cap50 | 16.01% / 1,601.23USD | 11.01% / 1,101.34USD | 0.21% / 20.89USD | 17.03% / 2,109.78USD | True |
| BTC-USD / regression_trend__fixed50 | 45.67% / 4,566.99USD | 38.74% / 3,873.69USD | 31.22% / 3,121.90USD | 14.06% / 1,664.12USD | False |
| BTC-USD / keltner_breakout__fixed50 | 15.18% / 1,518.25USD | 5.71% / 571.20USD | 5.71% / 571.20USD | 19.85% / 2,505.52USD | False |
| ETH-USD / obv_breakout__fixed50 | 46.05% / 4,605.06USD | 35.95% / 3,595.35USD | 14.48% / 1,447.89USD | 8.56% / 855.85USD | True |
| ETH-USD / aroon_trend__fixed50 | 11.66% / 1,165.56USD | 3.29% / 329.44USD | 3.29% / 329.44USD | 32.85% / 4,108.56USD | True |
| ETH-USD / breakout55__fixed50 | 31.18% / 3,117.92USD | 25.02% / 2,501.91USD | 20.87% / 2,086.71USD | 19.66% / 2,502.71USD | False |
| LTC-USD / regression_trend__vol15_cap50 | 5.36% / 536.29USD | 2.67% / 267.48USD | 2.67% / 267.48USD | 15.12% / 1,694.49USD | False |
| LTC-USD / cci_reversion__fixed50 | 9.67% / 966.72USD | 1.45% / 144.72USD | 1.45% / 144.72USD | 13.86% / 1,591.23USD | False |

BTC regression fixed50 remains positive at+31.219% /+3,121.90USD in its worst evaluation scenario, but failed original full-history drawdown/trade-count gates. ETH OBV fixed50 remains+14.479% /+1,447.89USD in its worst scenario and passes original historical screens. BTC SMA200 vol15 worst scenario is only+0.209% /+20.89USD. These observations justify further research, not deployment.

## Collector

Use scripts/collect_bybit_public_v2.py. It needs only Python standard library, public HTTPS GET, no keys. Defaults to12 rounds,10seconds between rounds, BTCUSDT/ETHUSDT/LTCUSDT,1000 displayed levels, latest200funding events per symbol, current mark/index/funding/open-interest ticker. Every raw payload is timestamped and hashed. Any request/format error stops the run and preserves evidence. No automatic retry, alternate domain, account or order call.

Outputs:spread; visible bid/ask notional within5/10/25/50bps of midpoint with band-coverage flags; quantity filters; buy/sell VWAP; same-snapshot round-trip cost in USDT, percentage of notional and percentage of10,000USDT. Fee assumptions5.5bps (published standard taker illustration) and10bps (stress), account fee unverified. Funding summary is constant-notional illustration over returned events, not strategy PnL. RPI liquidity, later book changes, latency slippage and liquidation are not measured. One short collection cannot establish historical capacity.

v1 portable launch failed because repository __init__ imports dotenv. No HTTP request was made in that failed launch. v2 imports the same pure stdlib module directly; all frozen012 source and ranking inputs remain unchanged. See collector_correction.json.

## Next bounded work

Obtain valid local public-data capture; then collect matching Bybit historical trade-price/mark-price/funding data, audit gaps and freeze a separate perpetual replay contract before testing shortlisted families. Include position-time funding and margin/mark rules, train-only selection and walk-forward. Do not relabel spot curves or silently migrate either frozen Coinbase paper cohort. No actual fills or future-profit claim.

## Reproduce

python scripts/rank_opportunities.py --source <verified011fullresults> --output <newdirectory> --freeze-sha 348e44e5cef56ceaa9becb8822fe58b4ada12403d015c9ebd816c040c8aca213.

python -S scripts/collect_bybit_public_v2.py --rounds 12.

Sources: https://bybit-exchange.github.io/docs/v5/market/orderbook ; https://bybit-exchange.github.io/docs/v5/market/instrument ; https://bybit-exchange.github.io/docs/v5/market/history-fund-rate ; https://bybit-exchange.github.io/docs/v5/market/tickers ; https://www.bybit.com/en/help-center/article/Futures-Contracts-Fees-Explained
