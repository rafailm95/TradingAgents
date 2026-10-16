# Validated local Bybit capture —2026-10-16

The user-provided ZIP contains78public market responses,36distinct books and600funding events. All78raw hashes match;144scenario outputs exactly reproduce;144separate cumulative-depth cash oracles agree. No private endpoint or order is present in the recorded request list. Five new validator tests plus22existing depth/collector/discovery tests pass (27total); an altered real-capture summary was also correctly rejected.

Capture:2026-10-16T17:01:16.759Z to17:04:15.149Z (20:01–20:04Asia/Nicosia),178.39seconds.12books per symbol. Assistant runtime access is unchanged; the user-local path succeeded. Input is internally reconciled user-uploaded API evidence, not independently signed venue data.

Hypothetical equity10,000USDT; target position5,000USDT, quantity floored to current contract increments. Median same-snapshot opening/closing costs below include spread, displayed-depth sweep and assumed taker fees5.5bps each side; stress fees10bps. No actual fills and no held-period funding in this table.

| Symbol | Actual median buy notionalUSDT | Median costUSDT | % of10k equity | Cost rangeUSDT | Stress medianUSDT |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 4,959.96 | 5.46 | 0.0546% | 5.46–5.46 | 9.93 |
| ETHUSDT | 4,997.49 | 5.52 | 0.0552% | 5.49–5.69 | 10.02 |
| LTCUSDT | 4,997.83 | 7.09 | 0.0709% | 6.34–7.85 | 11.58 |

BTC/ETH displayed liquidity near midpoint was much larger than LTC in this brief sample. All5bps and10bps bands were fully covered in12/12observations for all symbols. Some deeper25/50bps bands are incomplete; use coverage flags. RPI orders are excluded by the exchange's ordinary order-book API. Static observed impact is not latency slippage or proof of future executable liquidity. HTTP response durations range0.488–8.629seconds; book age at receipt BTC168–553ms,ETH196–1487ms,LTC151–446ms. These are client request/age observations, not order-execution latency.

Funding:200events per symbol from2026-08-11T08:00Z through2026-10-16T16:00Z,8h spacing and zero spacing anomalies in this returned window. On an assumed CONSTANT5,000USDT long notional at each event, net funding paid would be BTC43.2135USDT (0.432135% of10k),ETH41.23315USDT(0.4123315%),LTC46.0265USDT(0.460265%). Short receives the opposite net amount under the same assumed exposure; this is not strategy profit, ignores price PnL and is not an annualized forecast. Actual position funding requires notional/mark price at each funding timestamp.

The archive has no historical trade-price/mark-price candle series covering candidate evaluation. Do not run a realistic perpetual backtest by relabeling Coinbase spot data or extrapolating this short liquidity capture. Next research gate:matching Bybit candle/mark/funding coverage, audited timing, separate frozen perpetual accounting contract, then chronological strategy tests. Existing frozen spot campaigns and original costs remain unchanged.

Reproduce (offline,Pythonstdlib):
python -S scripts/audit_bybit_capture.py --input <ZIP> --sha256 f9291c2baa1954f99f84a7e810fe0f1344acc69663666bbc537dd28278cd77f9 --output <audit.json>

Primary documentation:https://bybit-exchange.github.io/docs/v5/market/orderbook ; https://bybit-exchange.github.io/docs/v5/market/history-fund-rate ; https://www.bybit.com/en/help-center/article/Futures-Contracts-Fees-Explained
