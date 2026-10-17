# Reproduce bounded futures batch021

Only the research branch `codex/research-continuation-20261016` is writable. Never modify main, upstream, frozen013/014, or either prospective cohort.

The public native Binance histories cover 2022-01-01 00:00 UTC through 2026-01-01 exclusive. No current quote, private account, order, paid provider or new download is required. Restore the exact input archive listed in `research/experiments/021/input-artifact-receipts.json` and verify its external SHA256 before extraction. Preserve all raw responses, checksums and the SOL funding-cadence rejection. Do not overwrite or redownload frozen inputs.

Input checkpoint published before strategy outcomes: `9f2da0d6202445af0ab4de7eaa306f466be39766`.

- Final engine/input freeze SHA256: `84a327534067a10aca16eb0cb8e162914b84ce78d2a149098595600484ad5f34`.
- BTC normalized SHA256: `7c9124b3259aa45445a1dd4e924a8749fad4b21a60965c03e0094ecc2c0d7b50`.
- XRP normalized SHA256: `367f1d7bef2bafd09da18e8514c4a3b5b7319085f8aa2cb7c33c3f58b0b6e7d6`.
- Main train-only selection SHA256: `6eaac57ec7928c13a933d65717c8bae88be4e12029289c7fb44f5a6bbad8f3ba`, published `80bfd7f2d851739f621f24ba273ff150e2f978f1`.
- Expanding selection SHA256: `0cc99b09bf05aa5174d29ddbbe0f6ded63335e36ca1f07a62104c3979feb1ae0`, published `9c9ebbcafaae821ed1fe26acb21681d6fb5829cf` before evaluation.

Use Python3.12 in an isolated environment; install only `requirements-research.txt`. No full application or model provider imports are needed. Versions are checked by the frozen runner. From a fresh research checkout, with restored `futures-021-data` as a sibling directory, use new output directories:

```bash
python3.12 -m venv ../reproduce021-venv
../reproduce021-venv/bin/python -m pip install -r requirements-research.txt
../reproduce021-venv/bin/python scripts/run_futures_assets_021.py --data-root ../futures-021-data --freeze-sha256 84a327534067a10aca16eb0cb8e162914b84ce78d2a149098595600484ad5f34 --stage train1 --output ../reproduced021-train1
```

Verify the newly produced `selection.json` SHA against the published main-selection pin before the next stage. Never choose a different candidate from an evaluation result.

```bash
../reproduce021-venv/bin/python scripts/run_futures_assets_021.py --data-root ../futures-021-data --freeze-sha256 84a327534067a10aca16eb0cb8e162914b84ce78d2a149098595600484ad5f34 --stage train2 --output ../reproduced021-train2 --train1 ../reproduced021-train1 --selection1-sha256 6eaac57ec7928c13a933d65717c8bae88be4e12029289c7fb44f5a6bbad8f3ba
../reproduce021-venv/bin/python scripts/run_futures_assets_021.py --data-root ../futures-021-data --freeze-sha256 84a327534067a10aca16eb0cb8e162914b84ce78d2a149098595600484ad5f34 --stage evaluate --output ../reproduced021-evaluation --train1 ../reproduced021-train1 --selection1-sha256 6eaac57ec7928c13a933d65717c8bae88be4e12029289c7fb44f5a6bbad8f3ba --train2 ../reproduced021-train2 --selection2-sha256 0cc99b09bf05aa5174d29ddbbe0f6ded63335e36ca1f07a62104c3979feb1ae0
```

Preserve any unexpected failure and its partial files. Do not silently rerun, replace accepted results or lower gates. Reproduction runs are integrity replays, never new variants or independent evidence. Full results use fsynced base64/gzip envelopes and separate decoded/container SHA256 values; each is independently checked by the wealth-accounting oracle.

The six original017 variants are tested in both BTC and XRP:24 train1,24 train2,144 fixed evaluation,48 walk-forward annual folds and10 benchmarks, maximum250 design executions. SOL has complete audited trade/mark candles but is excluded before any strategy PnL because the original contract requires8-hour funding. All4,458 captured SOL events remain intact, including2h/4h events. A separately preregistered causal funding-schedule extension is needed; no eight-hour resampling or invented rates is permitted.

Data/audit commands, if independently needed, read existing inputs only:

```bash
../reproduce021-venv/bin/python scripts/summarize_futures_inputs_021.py --data-root ../futures-021-data --output ../reproduced021-coverage.json
../reproduce021-venv/bin/python scripts/audit_sol_candles_021.py --data-root ../futures-021-data --output ../reproduced021-sol-candles.json
```

Do not regenerate the already published freeze. The collection, source and final engine/input freezes are additive immutable records. The input archive contains all432 monthly and26 daily archives with published checksums; the report and result artifacts are separately linked by the final artifact receipt.
