# Unified Bybit collection014

The user requested one comprehensive data collection instead of repeated separate uploads. `START_ALL.cmd` now coordinates the required public research inputs and emits one `BYBIT_SEND_THIS.zip`. This supersedes the separate user-facing snapshot/history collection instructions. It does not change any frozen strategy or paper-trading cohort.

## Requested contents

| Component | Requested coverage |
|---|---|
| Traded-price and mark-price hourly candles, settled funding | Original013window:2021-01-01 through2026-10-15 inclusive |
| Index and premium-index hourly candles | Same historical window |
| Traded-price and mark-price five-minute candles | Last90days of the fixed historical window |
| Open interest | Hourly, last365days of that window; both/single-side source fields preserved |
| Long/short account ratio | Daily from2021; this is a public aggregate, not the user's account |
| Instruments and current risk tiers | Current specifications; risk tiers captured initially and finally, instruments each live round |
| Market observations |865rounds at least5minutes apart, approximately72hours; three symbols; two sequential1000level books, ticker and100recent public trades per symbol/round |
| Closing extension | Hourly traded/mark/funding from013cutoff through the latest fully closedUTCday at finish |
| Provenance and coverage | Exact response bytes, source/receipt times, request metadata, SHA256inventory, state, errors and Greek status |

The planned live sample is5,190books if all rounds validate. Ordinary orderbook snapshots excludeRPIliquidity. The100trade tails are sampled recent trades, not a complete trade tape. Paired-book timing measures observed quote changes and HTTP latency, not actual order-fill latency. No continuous websocket/full-tick historical data is claimed.

The initial plan requires approximately1,017GETrequests when expected history is available, then12,975liveGETrequests and final risk/history extension requests. Pacing is at least0.3seconds between requests and5minutes between round starts. At most30,000total recorded attempts,15MBper response,1.5GBraw evidence and7dayswall time are allowed;3GBfree disk is required at launch. These are software bounds, not measured package size or completion time on the user's network.

## Resumption and failure behavior

Historical successful pages are reused only after exact source/protocol/query/byte validation. Matching013outputs in a bounded set of known sibling folders can be imported without network calls. No arbitrary personal-folder scan occurs. PublicGETnetwork timeouts, connection errors,HTTP429/5xx andAPI10006receive at most3attempts with5/15second waits. An exhausted query cannot start another retry cycle within the same invocation. HTTP401/403,redirect,non-JSON and clock/integrity failures stop collection; there is no alternate-host/proxy fallback.

One optional or core data component failing does not suppress independent asset/component downloads. Gaps are reported and never fabricated. An interrupted live round is retained as partial; a resumed round receives new timestamps and new request identities. No missed live observation is backfilled. A controlled stop/error produces the same one output ZIP. An OS-held process lock prevents concurrent writers and releases on process termination. Windows idle-sleep prevention is temporary and does not alter the user's power plan or bypass lid closure, reboot or manual sleep.

## Verification and limits

110targeted tests passed, including24new unified-collector tests. They cover full synthetic pipeline and ZIP audit, retry bounds, access-block refusal, historical/import cache integrity, interruptions, optional/core failure isolation, history extension, risk pagination, missing auxiliary values, negative premium-index values, source/response/cache-key/summary tampering, unsafe archives and lock cleanup. Standalone commands work withPython-Swithout third-party packages. Existing011/012/013source freezes and both prospective runtime pins were verified unchanged.

The Windows launcher and platform-specific branches were inspected; this Linux runtime did not execute an actual72hourWindowscapture. No real API request or actual historical strategy simulation occurred in this implementation batch. The already validated36book/600fundingevent capture remains actual evidence.

Account-specific fees, real user leverage/margin mode, historical margin/filter versions, complete tick-level execution and future profitability remain unknown. Hypothetical10,000USDT,1xand stated fee scenarios remain assumptions. This packet cannot certify a profitable strategy. The013full replay adapter still needs implementation and an additive engine freeze before any real strategy outcome is computed.

## Offline receipt check

```text
python3 -S scripts/audit_bybit_complete.py --input BYBIT_SEND_THIS.zip --sha256 EXTERNAL_ARCHIVE_SHA256 --output NEW_AUDIT_JSON
```

The audit reads only bounded flat data files, verifies the external archive hash and member inventory, checks the expected source/protocol pins, reconstructs historical coverage and recomputes valid live book diagnostics. It never executes uploaded archive code. Valid hashes and internal consistency are not independent exchange attestations.

Official endpoint references are recorded in `docs/BYBIT_COMPLETE_014.json`. The user-facing instructions are `docs/BYBIT_ALL_DATA_README_EL.txt`.
