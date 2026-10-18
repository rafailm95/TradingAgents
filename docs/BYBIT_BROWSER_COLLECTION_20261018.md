# Easier user-operated historical collection — 2026-10-18

The user asked for an easier alternative to the Windows complete packet. The new self-contained `notebooks/Bybit_History_One_Click.ipynb` runs in a user-controlled Google Colab CPU session. It needs a Google session, no Python installation, no pip packages, no Google Drive permission, and no Bybit login or keys. It embeds the exact delivered026 package plus an independently hashed additive wrapper. The original013/014/026 sources, protocols, freezes and full Windows package remain unchanged.

## Scope and limitations

Run all downloads historical components through the unchanged026 `historical()` function and produces one `BYBIT_SEND_THIS.zip`. BTC/ETH/LTC original013 core and all five BTC/ETH/LTC/SOL/XRP supplements retain their exact rules. Trade/mark/index/premium, actual funding events, 5-minute/1-minute bars, OI, ratio and risk requests remain bounded. Unavailable/prelaunch rows are not filled. The initial closed-UTC-day cutoff remains pinned. There are no strategy calculations or orders.

This optional profile does **not** request the865 live rounds, the72-hour depth sample, final risk refresh or closing extension. Its full-packet status therefore remains `COLLECTED_WITH_GAPS_REVIEW_REQUIRED`, even when historical core is complete. Zero new books is not presented as completed depth coverage. It can unblock frozen013 historical input only if the independent auditor certifies its original core. The additive026-to013 replay adapter still must be pinned before PnL, as already documented. No new user package is required merely for that adapter.

Each button run has a four-hour pre-request budget; normal026 request, compressed storage and seven-day bounds also apply. Same-runtime continuation reuses hash-verified pages and the original cutoff. The wrapper refuses to automatically repeat previous access/integrity stops. Interruptions during collection package partial evidence; an abrupt Colab VM deletion may lose all local files. No Drive mounting, external upload or background execution is introduced. Download the ZIP before leaving the session. The wrapper has no alternate hosts, region selection, proxies, account credentials or paid model/data/service calls.

Colab execution and its actual network access were **not** tested here. The official Colab FAQ says the free runtime can last at most12hours depending on availability/usage and may terminate on inactivity. Therefore it is a convenient history-only option, not a guaranteed72-hour collector or a verified cure for Bybit access restrictions.

## Actual access checks

On2026-10-18 around00:59–01:00UTC (03:59–04:00Cyprus), exactly one fresh runtime public API probe was made to mainnet `/v5/market/instruments-info?category=linear&symbol=BTCUSDT`. It returned HTTP200 HTML `Site Unavailable`,195bytes, not JSON. No retry or second API request followed.

Two independent public download checks were made: the official historical-download page and one archive file explicitly listed in Bybit's public directory, `SOLUSDT2021-07-01.csv.gz`. Both also returned the same195-byte HTML error, not a downloaded market file. All three raw bodies share SHA256`5b131ca14aa96311d3432b0062c7443d3b0e6346ec279bd376a75f0a76bcd5d7`. Request timestamps, raw bytes and hashes are preserved below `research/collection-026/browser-profile/access-check/`. No current quotes or market observations were accepted. Existing36validatedBybitbooks/600fundingevents remain prior actual evidence.

The web research service could read official public archive directory listings for BTCUSDT/SOLUSDT/XRPUSDT, including SOL entries from2021-06-29. A directory listing is not an audited data file or evidence of complete mark/funding coverage. The official download page is an additional manual-download option from the user's browser; it is not certified as a one-file substitute for all026streams. Do not retry failed endpoints automatically or substitute search snippets for data.

## Verification and reproduction

Python3.12.14 isolated research environment:46tests passed (8new browser-profile checks plus38existing026 checks). Tests cover original013 complete/incomplete export, all five synthetic histories, no live endpoints, access-block preservation without cell-rerun retry, request-budget resumption, controlled interruption, profile isolation, and execution of the embedded notebook setup and collector under `python -S`. This is software evidence, not a successful real Colab/Bybit capture.

Initial test result44passed/1failed is preserved. An inherited fake transport returned a `KeyboardInterrupt` object instead of raising it, because its exception branch only checked `Exception`. The test fixture was corrected with an actual interrupting transport; production rules and collectors were unchanged by that correction.

Reproduce:
```
python scripts/build_bybit_history_notebook.py --packet /path/to/Bybit_Complete_Packet_20261018.zip --output notebooks/Bybit_History_One_Click.ipynb
python -m pytest --noconftest -q tests/test_bybit_history_browser.py tests/test_bybit_packet_026.py tests/test_bybit_packet_026_extensions.py
```

The generated notebook verifies original packet SHA256`a741d8c87462efa806d8f8ad778b3cabe35447d535864e99ad6f20fc60685ea5` and wrapper bytes before use. Returned ZIPs use unchanged `scripts/audit_bybit_packet_026.py`, with an independently pinned external archiveSHA; never execute uploaded code. Research counters remain90variants/45families,9894design executions plus7integrity replays=9901known executions. No research family, strategy outcome, prospective cohort or frozen pin changed.

## Primary sources checked2026-10-18

- https://bybit-exchange.github.io/docs/v5/market/recent-trade
- https://www.bybit.com/en/derivative-activity/history-data
- https://public.bybit.com/trading/BTCUSDT/
- https://public.bybit.com/trading/SOLUSDT/
- https://public.bybit.com/trading/XRPUSDT/
- https://research.google.com/colaboratory/faq.html
