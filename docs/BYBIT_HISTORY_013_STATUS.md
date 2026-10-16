# Bybit historical-data preparation — batch013

The portable collector, offline archive audit and Decimal USDT cash-flow kernel are implemented. **86 targeted tests passed, including34new tests. No actual historical Bybit strategy simulation ran in this batch.** The full causal hourly replay adapter remains to be implemented and separately frozen before evaluating real data.

## Collection scope

BTCUSDT, ETHUSDT and LTCUSDT linear USDT perpetuals;2021-01-01T00:00UTC through2026-10-16T00:00UTC exclusive. Per symbol:50,736hourly traded-price candles,50,736hourly mark-price candles,6,342expected eight-hour funding settlements plus a pre-start anchor. Approximately405public GET requests if the expected schedule/history is available. The exact collection specification is `docs/BYBIT_HISTORY_013.json`.

The eight-hour funding schedule is a validation assumption for this dataset. A historical cadence change or missing event stops replay pending documented review; the collector never invents a zero rate. Missing candle hours remain missing. Fixed non-overlapping request windows prevent short pages from silently truncating coverage. Current instrument metadata and order filters are collected but are not asserted to be historical rule snapshots.

Requests use the official mainnet host and public market paths only. No credentials, private endpoints, order endpoints, alternate domains, redirects or automatic retries. Every response is retained with a SHA256 and original receipt timestamp. Re-running the launcher reuses successful pages only after checking their bytes, exact queries, protocol and collector-source hashes. Failed attempts remain in the evidence. A blocked or interrupted collection also produces a ZIP.

The previous user's real snapshot capture remains valid:36books and600settled funding events over178.39seconds. Those are not replaced by synthetic tests. The assistant runtime's prior non-JSON response is unresolved; this batch made no repeat real API request. The proven user-local collector path is used for the new history package.

## Preparation for finding strong candidates

The separate design in `docs/BYBIT_PERPETUAL_REPLAY_013.json` fixes six distinct existing families: SMA200band, regression trend, Keltner breakout, OBV breakout, Aroon trend and CCI reversion. Each selected sizing will be tested on all three assets, with10,000USDT initial equity per independent simulation. They are selected from prior exploratory rankings, so the resulting venue-transfer study cannot be called untouched evidence.

The design specifies chronological training/evaluation, a one-hour signal/fill buffer, delays, baseline/stress fee and slippage assumptions, actual funding events, operating expense, quantity constraints, conservative collateral guards and full reporting of failures. Costs are explicitly new venue assumptions, not reductions to the frozen Coinbase experiments. The cash-flow kernel tests signed funding, realized/unrealized PnL, fee debits, cash conservation and actual peak-to-trough drawdown amounts. It is **not** a liquidation or complete execution simulator.

## Verification

-34new network-free tests: full pagination/audit roundtrip, interruption and resumption, cached-byte/source tampering, missing candles, wrong symbols, invalid OHLC, non-finite values, duplicates, chronology, unclosed candles, negative volume, funding gaps/cadence/anchor failures, incomplete days, unsafe ZIP paths, non-JSON responses, standalone Python without site packages, independent cash/funding/drawdown oracles.
-86total targeted tests, including prior Bybit capture/discovery checks and frozen campaign isolation checks.
-Existing011and012source hashes and both prospective runtime pins remain unchanged; exact receipt is in `research/experiments/013/verification.json`.
-Tests are synthetic software verification, not profitable trading observations. Cumulative actual historical strategy simulations remain6,990from prior overlapping spot studies; this batch adds0newstrategy variants and0realstrategy simulations.

## Use and next action

Extract `Bybit_History_Collector.zip` on the Windows computer used for the successful snapshot capture. Run `START_HISTORY.cmd`, keep the window open, and return the generated `bybit_history_013.zip`, even if it reports an error. The launcher requires the existing Python3installation and no extra packages. It does not run inside the Bybit mobile app. A10–30minute duration is an estimate, not a benchmark.

Audit the returned archive without executing its contents:

```text
python3 -S scripts/audit_bybit_history.py --input PATH_TO_ZIP --sha256 EXTERNAL_ARCHIVE_SHA256 --output NEW_AUDIT_JSON --normalized NEW_DATA_JSON_GZ
```

Normalized replay inputs are emitted only when all three assets have complete history under the fixed schedule. Complete and independently test the causal hourly replay adapter, record an additive engine freeze and pin the real data archive before calculating any strategy outcome. Preserve all six candidates and all failures; existing seven-candidate prospective cohorts remain untouched.

Official references: [trade candles](https://bybit-exchange.github.io/docs/v5/market/kline), [mark candles](https://bybit-exchange.github.io/docs/v5/market/mark-kline), [settled funding](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate), [USDT PnL](https://www.bybit.com/en/help-center/article/Profit-Loss-calculations-USDT-Contract), [funding calculation](https://www.bybit.com/en/help-center/article/Funding-fee-calculation).
