# Reproduce023 without network or strategy PnL

Python3.12 and an isolated environment using requirements-research.txt. Do not install the full application or load providers. Resolve the current authorized research branch and verify collection-freeze.json and adapter-freeze.json plus every source/preservation hash before importing research code.

Collection checkpoint771004075dbc50c9d631f91c08d076942e907dad preceded all new data. Collection freeze SHA2561e0c382e9f9c665790c8e5ca4d25c82cfb159b015d65e45878fe286db79c7270. The initial attempt is closed with data blocked; do not automatically rerun the collector or repeat failed requests.

The source-controlled research/experiments/023/data/partial-public-archives.zip.b64 contains every accepted raw archive, checksum, receipt, original collection intent, failed response and stopped state. Decode base64, check the archive SHA256 against data/manifest.json, check ZIP CRC and each member SHA256 before extracting to a new folder. The archive is incomplete and is never replay eligible.

Offline commands (substitute only filesystem locations):

```bash
python -m pytest --noconftest -q tests/test_binance_archive.py tests/test_futures_assets_021.py tests/test_futures_extension_023.py
python -m pytest --noconftest -q tests/test_futures_calendar_023.py
python scripts/audit_partial_futures_023.py --input /path/to/restored-023 --output /path/to/new-partial-audit.json
```

Expected original evidence:50collection tests plus23adapter tests,35new total;179synthetic matrix executions excluded from research counts. Offline data audit:66checksummed archives, each asset5832trade hours/5064mark hours/636funding rows, missing2026-06-29mark plus uncollected later months. Original failed Augustmark requests returned tunnel403; no retries, daily repairs or changed date window.

The optional scripts/package_futures_calendar_023.py is the initial publication packager. It expects the initial collection directory and original test log in its workspace argument. Do not rerun it against accepted registry state to imply new work; exact original output is preserved.

tradingagents/futures_calendar_023.py joins consecutive2022–2025 and2026 data only after external normalized/manifest SHA checks and full trade/mark/funding grid validation. BTC/XRP use unchanged021 parsing, SOL uses unchanged022 piecewise historical funding parsing. New2026 remains strict8h. The additive runner reuses the validated019Decimal ledger.

There is intentionally NO research/experiments/023/engine-freeze.json with real inputs: no asset is eligible. Therefore scripts/run_futures_calendar_023.py cannot run its historical stages. Future completion requires full genuine inputs, an additive input/source/test freeze published before training, then publication of the exact training selection SHA before evaluation. Do not point the runner at adapter-freeze.json or infer permission to bypass missing coverage.

Frozen design:6existing variants,3assets max; train2023–2025, evaluate2026Jan–Sep;12train+72evaluation+5benchmarks perasset, plus one managedcash path only if selected. Selected candidate scenario is reused as2026fold without another strategy execution; reset2026capital is never compounded onto olderWFA. Original maximum270 executions, zero executed here.

Prior2022–2025 normalized inputs remain immutable: BTC7c9124b3259aa45445a1dd4e924a8749fad4b21a60965c03e0094ecc2c0d7b50; XRP367f1d7bef2bafd09da18e8514c4a3b5b7319085f8aa2cb7c33c3f58b0b6e7d6; SOLcaf418c4b634991cbbdf64c1fc1ffba3e6bf15b87f049742816ca290d86287da. BTC/XRP restored from original021 evidence Part1 externalSHA5b83978eb5b4afc30d8a686c9a794c9681eb4230908f87f363ed0229bbc60da4; SOL restored from source-controlled022normalizedbase64. No old outcome rerun and no old data redownload.

Bybit013/014 and both prospective cohort runtime pins remain unchanged. Prior evidence table is explicitly reused021/022, not new023 performance. All amounts refer to virtual USDT accounts, not USD spot or actual funds.
