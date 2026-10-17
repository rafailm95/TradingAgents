# Reproduce020 without changing any historical result

Use Python3.12 and `requirements-research.txt` in a fresh isolated environment. No application startup, model provider, key, network request or order is used by the replay. Work on the authorized research branch, using the committed sources and exact externally pinned inputs.

Obtain the saved017 evidence ZIP and allthree019 evidence parts identified by `docs/NR7_FUTURES_020.json` and `research/experiments/019/artifact_receipts.json`. Their exact hashes are enforced by the runner. Extract the normalized input from017, or use the identical copy in020 evidence; SHA256 `cccf3ff868465439ede973dd505c95d906c9e6eb9a9c31263c040fd053ccd00e`. Never redownload/replace frozen input to improve an outcome.

From the repository root, with input/reference files in the parent directory:

```bash
python3.12 -m venv ../research020-venv
../research020-venv/bin/pip install -r requirements-research.txt
../research020-venv/bin/python -m pytest --noconftest -q tests/test_bybit_replay.py tests/test_bybit_cashflow.py tests/test_binance_archive.py tests/test_funding_futures_019.py tests/test_nr7_futures_020.py

../research020-venv/bin/python scripts/run_nr7_futures_020.py --input ../binance-017-normalized.json.gz --reference-archive ../restored017/Futures_Binance_017_Evidence.zip --reference-parts ../Futures_019_Evidence_Part1.zip ../Futures_019_Evidence_Part2.zip ../Futures_019_Evidence_Part3.zip --freeze-sha256 81bc0277b2adb9141b4a3a6aad92a72253949848a1d0926089aeaa70f8a6c74d --stage train1 --output ../nr7-020-train1

../research020-venv/bin/python scripts/run_nr7_futures_020.py --input ../binance-017-normalized.json.gz --reference-archive ../restored017/Futures_Binance_017_Evidence.zip --reference-parts ../Futures_019_Evidence_Part1.zip ../Futures_019_Evidence_Part2.zip ../Futures_019_Evidence_Part3.zip --freeze-sha256 81bc0277b2adb9141b4a3a6aad92a72253949848a1d0926089aeaa70f8a6c74d --stage train2 --output ../nr7-020-train2 --train1 ../nr7-020-train1 --selection1-sha256 316418d95c59982fb936005ee47b5707581f1d4dbbc5d8fb58156c175a8b5220

../research020-venv/bin/python scripts/run_nr7_futures_020.py --input ../binance-017-normalized.json.gz --reference-archive ../restored017/Futures_Binance_017_Evidence.zip --reference-parts ../Futures_019_Evidence_Part1.zip ../Futures_019_Evidence_Part2.zip ../Futures_019_Evidence_Part3.zip --freeze-sha256 81bc0277b2adb9141b4a3a6aad92a72253949848a1d0926089aeaa70f8a6c74d --stage evaluate --output ../nr7-020-evaluation --train1 ../nr7-020-train1 --selection1-sha256 316418d95c59982fb936005ee47b5707581f1d4dbbc5d8fb58156c175a8b5220 --train2 ../nr7-020-train2 --selection2-sha256 fdf33d8b03bf96ba2e64fca5dfaa325a8dd4c881568bce12a4043263f7718034
```

Output directories must not exist. These commands document reproduction; do not automatically rerun unchanged historical simulations merely to accumulate favorable results. The original run published preregistration at `2ab77e2141b849faa9f3bc676e509f38a5969fc5`, train1 at `8a2f24bde58d017444cd93a0d660be36f450bb69`, and train2 at `fdcf0a759801e49ed8bd121b8c1faf9f4e392b01`, each before its dependent outcome stage.

New full results use JSON envelopes containing deterministic gzip in base64. Verify the container hash, decode `payload_base64`, verify `decoded_sha256`, decompress, then independently audit wealth. See `full_result_hashes.json`. The frozen019 reference reader preserves and resolves previously documented zero-byte failures without counting reference reads as simulations.

The report/archive scripts only summarize, hash and package existing results; they never call a strategy replay. All old-source hashes and prospective pins remain unchanged.
