# Reproduce019 without changing accepted evidence

Use Python3.12 and a fresh virtualenv with requirements-research.txt. The repository is rafailm95/TradingAgents; authorized writes only codex/research-continuation-20261016. No providers, credentials or network calls are used by the replay.

Restore Futures_Binance_017_Evidence.zip (Library libfile_4a34e6a7d2dc8191bca89e277b1fbd97), verify external SHA256 676079438cd5b4b1d3bb768368bf9ba02518687461fa98f2c85f4bb671f53236 before reading. Extract only binance-017-normalized.json.gz, SHA256 cccf3ff868465439ede973dd505c95d906c9e6eb9a9c31263c040fd053ccd00e. The new019 evidence also includes this exact normalized file; raw provenance remains in the separately persisted017 archive.

From the repository root, with the restored files in its parent:

```bash
python -m pytest --noconftest -q tests/test_bybit_replay.py tests/test_bybit_cashflow.py tests/test_binance_archive.py tests/test_funding_futures_019.py
python scripts/run_funding_futures_019.py --input ../binance-017-normalized.json.gz --reference-archive ../restored017/Futures_Binance_017_Evidence.zip --freeze-sha256 04c9fb5a8ea26ee1ed3640ec75f2ef524dd50ffce1f9603bbb261ce941ad541d --stage train1 --output ../funding019-train1
python scripts/run_funding_futures_019.py --input ../binance-017-normalized.json.gz --reference-archive ../restored017/Futures_Binance_017_Evidence.zip --freeze-sha256 04c9fb5a8ea26ee1ed3640ec75f2ef524dd50ffce1f9603bbb261ce941ad541d --stage train2 --output ../funding019-train2 --train1 ../funding019-train1 --selection1-sha256 569510dbbe40d2a121d55cfe5ba2fd553719a31e2c80cb8e1bbcd04e3cd975bc
python scripts/run_funding_futures_019.py --input ../binance-017-normalized.json.gz --reference-archive ../restored017/Futures_Binance_017_Evidence.zip --freeze-sha256 04c9fb5a8ea26ee1ed3640ec75f2ef524dd50ffce1f9603bbb261ce941ad541d --stage evaluate --output ../funding019-evaluation --train1 ../funding019-train1 --selection1-sha256 569510dbbe40d2a121d55cfe5ba2fd553719a31e2c80cb8e1bbcd04e3cd975bc --train2 ../funding019-train2 --selection2-sha256 841a467ecff8f93cfe276b366ba6a01eb8d37abdf4f928d722230179353b8f9f
```

Do not execute into an existing output directory. Published pre-outcome source checkpoint4119be9; train1choice checkpointba36d9c; expandingtrain2choice checkpoint83a0b9f. The ledger derivative differs only in candidate registration, opening cash, managed-cash expense and corresponding independent audit; inspect engine-diff.patch. Prior013/017code remains untouched.

## Preserved integrity failure and exact reconstruction

All68planned scenario outputs initially had SHA256 receipts. Final verification found exactly four zero-byte files. The original evaluation manifest was committed unchanged as evaluation-pre-recovery.json, SHA2569b71fc05e3ab4f12b7036bba7e802e696e6b2e8057f7ed3d5a816a9c08df865c. The four original empty files remain in the evidence. Recovery intent and executable were published at97d380dc6c92eedd408cbc3af26e613877ac625d before reconstruction.

```bash
python scripts/recover_funding_results_019.py --input ../binance-017-normalized.json.gz --evaluation ../funding019-evaluation --output ../funding019-result-recovery
python scripts/package_funding_futures_019.py
```

The recovery script is for the preserved failure, not a step to run when a clean reproduction has no missing files. It refuses nonempty originals, writes only a new recovery directory, and requires exact original SHA256 and metrics. No original output or rule is overwritten. For restored evidence, consult full_result_hashes.json: four resolved paths point into funding019-result-recovery; original_path points at the retained zero-byte file. The package verifier checks all68resolved files and independently re-audits their cashflows. Four recovery executions are separately counted; they add no hypothesis or independent market evidence.

## Accounting and comparisons

The12WFApaths each have2024and2025folds. Each fold flattens at its last closed hour and passes the exact final cash into the next; no cash reset or return multiplication is used. Fees/funding/expense and actual sampled drawdown are recomputed. Scheduled terminal closes do not satisfy the20signal-exit gate. Managedcash incurs120USDT/year; idlecash benchmark incurs zero. All8compatible candidates and96fixed-evaluation scenarios are retained;72old017paths and fivebenchmarks are hash-verified reuse, not new replays. Forty other variants have incompatible spot-only histories and are excluded from native-futures multiplicity diagnostics with this limitation disclosed.

New family outcomes use previously inspected2022–2025historical dates, not prospective data. A historical winner, delayed scenario, diagnostic p-value or WFA result does not establish future profitability. Preserve all failures; no parameter tuning after results.


The first recovered file became zero-byte again on subsequent verification. packaging-second-failure.txt and recovery-v2-intent.json preserve that second failure. One additional preregistered reconstruction at154d2d9f3a710b318ca83351cac8ff3f68b512d6 serializes deterministic gzip in memory into a fsynced base64 JSON envelope. scripts/recover_funding_result_019_v2.py accepts only the original decoded resultSHA; original/first-recovery zero files remain. full_result_hashes.json distinguishes decodedsha256 from container_sha256 and encoding. There are five019integrity replays, no newhypotheses. Reproduction of the preserved failure requires thev2script before thepackageverifier.
