# Reproducing025 for a specified audit

Do not repeat unchanged experiments merely to search for profit. No model providers, private keys or exchange orders. Only the research branch is writable. Preserve prior outputs and failures. The initial runtime interruption has no acknowledged financial process/output; the recovered run is the first verified025 history. This uncertainty is retained in runtime-interruption.json and runtime-recovery-success.json.

Use a fresh checkout of the verified research branch and Python3.12 with requirements-research.txt in an isolated virtual environment. The engine freeze SHA256 is `d1004b32dce61b57dce36eae32901e843146e632813bd90db4ff7b199173eae9`; source hashes, all692 protected prior files and input hashes must match before importing/running research. Do not regenerate the freeze.

Obtain the exact saved files using research/experiments/021,022,024 artifact receipts. Required input archive: Futures_021_Inputs_Part1.zip. SOL normalized bytes and manifest are source-controlled under022. Required old WFA reference archives:024Parts10,16,21;10and16 are reconstructed from their two saved segment ZIPs. No raw-market redownload or old financial replay is needed. The restoration utility refuses changed existing files and verifies all hashes:

```bash
python scripts/restore_futures_references_025.py --archives /ABS/archives --workspace /ABS/reference-workspace
```

For already authorized reproduction/audit only, create new output directories and use the commands below. Fill selection SHA arguments from the SHA256 of the newly written selection.json, and compare with the published pins in research/experiments/025/publication.json. A mismatch is an integrity finding; preserve it instead of changing parameters. Do not proceed to evaluation until both selection checkpoints are confirmed on the research branch with expectedHEAD and force=false.

```bash
python scripts/run_multifamily_futures_025.py --data-root /ABS/reference-workspace/futures-023-base --freeze-sha256 d1004b32dce61b57dce36eae32901e843146e632813bd90db4ff7b199173eae9 --stage train1 --output /ABS/new-run/futures-025-train1
python scripts/run_multifamily_futures_025.py --data-root /ABS/reference-workspace/futures-023-base --freeze-sha256 d1004b32dce61b57dce36eae32901e843146e632813bd90db4ff7b199173eae9 --stage train2 --train1 /ABS/new-run/futures-025-train1 --selection1-sha256 SELECTION1_SHA --output /ABS/new-run/futures-025-train2
python scripts/run_multifamily_futures_025.py --data-root /ABS/reference-workspace/futures-023-base --freeze-sha256 d1004b32dce61b57dce36eae32901e843146e632813bd90db4ff7b199173eae9 --stage evaluate --reference-root /ABS/reference-workspace --train1 /ABS/new-run/futures-025-train1 --selection1-sha256 SELECTION1_SHA --train2 /ABS/new-run/futures-025-train2 --selection2-sha256 SELECTION2_SHA --output /ABS/new-run/futures-025-evaluation
```

The fixed evaluation includes all20newvariants*3assets*2costs*3signalfeedlags*2funding valuations=720scenarios, plus240newtraining scenarios. Up to72annual WFAfolds and3managedcash cases are conditional; an old WFAfold is reused only with identical candidate, dates, cost, lag, funding valuation and exact openingcash, after hash/wealth verification. Old26compatible fixed candidates, their312training outcomes,936evaluation outcomes and15benchmarks are reused from immutable024summaries. Total full comparison:46candidates perasset,138asset-candidate pairs.

All positions long/flat, independent10000USDT initial accounts,50%entrycap, no historicalbook/fill or leveraged liquidation claim. Maintrain2023; expandingtrain2023–2024 applies only to2025. Evaluation2024–2025 is reused, correlated history; never relabel as newforward evidence or Bybit performance. Preserve all120training files perstage, all720newfixed cases, every computedWFAfold, failures, intents and logs. Full results are base64+gzip envelopes with both container and decoded hashes. Copying saved evidence and checking its hashes is not a strategy replay.

Read-only verification/reporting (writes derived report files, never runs a strategy):

```bash
python scripts/package_multifamily_futures_025.py --workspace /ABS/new-run --freeze-sha256 d1004b32dce61b57dce36eae32901e843146e632813bd90db4ff7b199173eae9
```

Archive receipts are authoritative durable pointers. The full immutable source/rule/test freeze, original failed synthetic preflight, runtime interruption and exact recovery records remain in the repository. Both prospective paper cohorts and013/014/023 are untouched. No automatic promotion or retuning.
