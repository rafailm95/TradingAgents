# Reproduce bounded022 without network data requests or orders

Python3.12. Fresh checkout of `codex/research-continuation-20261016`; install only `requirements-research.txt` in an isolated virtual environment. No fullapplication/modelproviders. All dates UTC. The original021failure and BTC/XRP results remain untouched.

Remote pre-outcome checkpoint: `9f2994071c2f7231c063b3d504253e2feda0fd21`.
Exact engine freeze SHA256: `599c6e7da6f68036fcf28d8ff1286d7321d736da23026d75c0794b2ee283d100`.

The complete normalized SOL input is source-controlled as base64 of deterministic gzip JSON. Decode without changing bytes:

```python
from pathlib import Path
import base64,hashlib,shutil
out=Path('../futures-022-data/SOLUSDT')
out.mkdir(parents=True,exist_ok=False)
raw=base64.b64decode(Path('research/experiments/022/SOLUSDT-normalized.json.gz.b64').read_bytes())
assert hashlib.sha256(raw).hexdigest()=='caf418c4b634991cbbdf64c1fc1ffba3e6bf15b87f049742816ca290d86287da'
(out/'normalized.json.gz').write_bytes(raw)
shutil.copyfile('research/experiments/022/SOLUSDT-manifest.json',out/'manifest.json')
```

For independent raw provenance audit, restore `Futures_021_Inputs_Part1.zip` from the persisted input receipt (`research/experiments/022/input-receipt.json`), verify external SHA256 `5b83978eb5b4afc30d8a686c9a794c9681eb4230908f87f363ed0229bbc60da4`, extract preserving paths and run to a NEW directory:

```bash
python scripts/audit_sol_funding_022.py --raw-root ../restored/futures-021-data/SOLUSDT --manifest-sha256 90d11e87d2ffbaf2ffd280351e27d0e8a2347c3a8e238e0640a59b9df8587b81 --output ../audit-022
```

This verifies144monthly+10daily official archives, all published checksum bytes, CRC, exact candle overlap and the full4458event schedule. No aggregation, interpolation or fresh download. The normalized artifact must match the pinned hash. The old021strict8h auditor intentionally still rejects this SOL source.

Synthetic preflight command and observed157pass output are in `research/experiments/022/preflight.json`. These are software tests, not historical strategy search. Reproducible stages use new output directories, preserve every failure, and refuse source/input/selection hash mismatches:

```bash
python scripts/run_sol_funding_022.py --data-root ../futures-022-data --freeze-sha256 599c6e7da6f68036fcf28d8ff1286d7321d736da23026d75c0794b2ee283d100 --stage train1 --output ../futures-022-train1
```

The initial run's train1 SHA256 is `975d80d1ddbca1bdee4f651695c04ad8ae759a3308d3b429d7fb9ef2a0929dbf`; remote checkpoint `00e6d6503fdf6dff66dddcbe00ad7bda14e94937`. Pin and publish selection before proceeding; never adjust rules after seeing it.

```bash
python scripts/run_sol_funding_022.py --data-root ../futures-022-data --freeze-sha256 599c6e7da6f68036fcf28d8ff1286d7321d736da23026d75c0794b2ee283d100 --stage train2 --output ../futures-022-train2 --train1 ../futures-022-train1 --selection1-sha256 975d80d1ddbca1bdee4f651695c04ad8ae759a3308d3b429d7fb9ef2a0929dbf
```

Record train2 hash and publish its selection before evaluation. The exact final evaluation command and commit chain are retained in `research/experiments/022/publication.json` and the original stage intent files. Evaluation requires both original selection directories and their external SHA256. Replays are not new independent evidence and are not authorized solely to improve a result.

Reports are produced by `scripts/package_sol_funding_022.py`, which verifies all125stored outputs against their SHA256 and independent wealth-audit records without executing strategies. `metrics-all18.csv` and `walk-forward-all3.csv` explicitly label reused021BTC/XRP rows. The joint18diagnostic reuses hash-pinned021daily curves; it does not rerun those strategies. Sources, data, tests and all604prior trackedfiles except mutable registry are pinned by the freeze.

Full outputs use the inherited deterministic base64+gzip container; decode only through `read_result` in `scripts/run_nr7_futures_020.py` to validate both container and payload hashes. Full curves, fills, funding, wealth-events, selections and run intents are stored in the independent ZIP parts listed in `artifact_receipts.json`. Extract allparts into one workspace, preserve original names. No credentials or paid services are needed.

After packaging, run `python scripts/report_cross_asset_022.py --workspace ..` once to add the descriptive all-six cross-asset sign check. It reads the already verified complete summary and performs no strategy replay or parameter selection.

Train2 pin: `3afb1c1642e91ecacc3b8671384e227cd6568e3f9856678b572e506762d746cd`, committed at `04c4d6f7fa7a3e480d9e0335faf95d56e3b70558` before evaluation.
