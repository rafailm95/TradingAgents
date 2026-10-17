# Reproduce024: exactly20newvariants, never optimize until green

User2026-10-17 explicitly requested10–30strategies. One preregistered batch contains10distinct signal families ×2unchanged sizings=20variants, applied independently toBTCUSDT,SOLUSDT,XRPUSDT. Olderonefamily/max6variant cap is superseded for this request only. Publicdata/virtualaccounting limits and alloriginalfreezes remain unchanged.

Remote preregistration: ce5344ba556ffd3312faa68f68aadcf6f40dbda0.
Freeze research/experiments/024/freeze.json externalSHA256 ff166e2a69fdb339319ed9a6ee7f09d0e1f977c48a7527e50216e45552dae812.
Training1selection externalSHA256354db42cacfa74c2a9d349b4f7717265e5565703ea05d0735b75ee92b377834b published115ef568b725e72590a19df558602a570c0704a6 before nextstage.
Training2selection externalSHA2567cec2b484e2e6a8e004f90e8c04ffd089cea413a5417355e79085a5ef31ca451 published6ccbcdfc11d81618c76480dca307871e8aec9b1d beforeevaluation. Later result checkpoint hashes are recorded in publication-checkpoints.json and registry. Never rerun the completed batch merely to obtain profit.

Python3.12 with requirements-research.txt in an isolated environment. Original invocation used a research-onlyPython3.12.14 environment created in the previous freshcheckout, with allfour exact package versions verified; no application/provider packages, secrets or model calls.

Before imports verify every freeze source/preservation hash. Restore exact old2022–2025 normalizedinputs and manifests into DATA/{BTCUSDT,SOLUSDT,XRPUSDT}/. Input SHA values are in024freeze. BTC/XRP originate021, SOL022. Alloriginalrawarchive/normalizeddata Libraryreceipts remain in021/022artifact_receipts.json. No dataredownload or replacement for nicerresults.

Restore oldWFA envelopes under REFERENCES/futures-021-evaluation/ and REFERENCES/futures-022-evaluation/ as needed, using original021/022 persisted ZIPparts. The024freeze pins every72possible oldfold envelope and originaldecodedhash. Existinglocalcopies may be used only after thosehashchecks; they are caches ofalreadydurableevidence, not theauthoritative scratchsource. Oldtraining/evaluation compactoutputs are source-controlled and included inpreservationhashes.

Preflight commands actually executed:

```bash
python -m pytest --noconftest -q tests/test_multifamily_futures_024.py
python -m pytest --noconftest -q tests/test_multifamily_runner_024.py
```

88passed, zeroinitialtestfailures. Allfixturesare synthetic and excluded fromresearchcounts. Full20variant matrix, oldreference/WFAreuse, changedchoicecapitalcarry, closedbar/prefixcausality, independentindicatororacles,20sizings×3lagsandindependentcashflow checks.

Research stages, new nonexisting outputdirectory each time:

```bash
python scripts/run_multifamily_futures_024.py --data-root DATA --freeze-sha256 ff166e2a69fdb339319ed9a6ee7f09d0e1f977c48a7527e50216e45552dae812 --stage train1 --output TRAIN1
# Verify/persist/publish exactselection1hash before proceeding.
python scripts/run_multifamily_futures_024.py --data-root DATA --freeze-sha256 ff166e2a69fdb339319ed9a6ee7f09d0e1f977c48a7527e50216e45552dae812 --stage train2 --output TRAIN2 --train1 TRAIN1 --selection1-sha256 SELECTION1_SHA
# Verify/persist/publish exactselection2hash before anyevaluation.
python scripts/run_multifamily_futures_024.py --data-root DATA --reference-root REFERENCES --freeze-sha256 ff166e2a69fdb339319ed9a6ee7f09d0e1f977c48a7527e50216e45552dae812 --stage evaluate --output EVALUATION --train1 TRAIN1 --selection1-sha256 SELECTION1_SHA --train2 TRAIN2 --selection2-sha256 SELECTION2_SHA
```

The reporting/archiving helpers use WORKSPACE/{futures-024-train1,futures-024-train2,futures-024-evaluation} and originalstdoutlogs. They never replaystrategies. Everyacceptedfullresult is anfsyncedbase64+gzipenvelope withcontaineranddecodedhashes plusindependentwealthaudit. Allresultsarepersisted inFutures_024_Results_PartN.zip; exactIDs/SHA/bytes are inartifact_receipts.json.

A progresslog anomaly was observed intrain1:38lines instead of60, despite120completeenvelopes individuallyread/hashchecked/audited. Originalpartiallog and observation are preserved; noresultreconstruction orstrategyreplay. Thecause isunknown; financialevidence remains complete. Laterstage logs are retained asobserved, not regenerated.

Read-only final verification/reporting and registry completion (only after every research stage finishes):

```bash
python scripts/package_multifamily_futures_024.py --workspace WORKSPACE --freeze-sha256 ff166e2a69fdb339319ed9a6ee7f09d0e1f977c48a7527e50216e45552dae812
python scripts/complete_multifamily_futures_024.py --workspace WORKSPACE
python scripts/archive_multifamily_futures_024.py --workspace WORKSPACE
```

The completion helper refuses to overwrite a completed024 entry. Archive helpers use exclusive creation and verify every ZIP member byte for byte. Library receipt metadata is generated after successful saving and published with final results; it is not an input to any strategy calculation. Reporting helpers were added after the financial implementation freeze and cannot change frozen results.

Frozen financialcontract: independent10000USDT,50%entrycap,longflat,cash-backedguard;5.5+2bps/sidebase,10+10stress,120USDT/365.25days;actualheldfunding withmarkproxy/adverse5bps,lag0/1/2. Noactualpersonal/historicalfees, historicaldepth/fills, historicalorderfilterverification orleveragedliquidation model. HeikinAshi onlyfeatures, fillsrealprices. All20newvariants/all3assets/all12cases retained. Include all26compatible candidates inselection/diagnostics; preserveETH10 andspot40references separately.

Expected core newcount120train1+120train2+720fixed=960. Up to72changedWFAfolds and0..3mainselectedmanagedcashpaths; max1035. Reuseidenticaloldfolds whenchoiceandexactcapitalmatch. Fullsource/data/testfreeze before firstoutcome, eachselectionpublishedbeforeevaluation. Failuregatesneverlowered; allhistories exploratory, notnewprospectiveevidence.

## Exact archive restoration after transfer recovery

The initial report and original Part21 saved successfully. Twenty larger ZIP files returned explicit `transfer_failed` results. The service did not provide a more specific cause. Each failed original was preserved unchanged and split into two chunks of at most48,000,000bytes, each inside a smaller ZIP. All40 segment ZIPs, their original offsets, chunk hashes, wrapper hashes and exact reconstructed original SHA256 values are recorded in `research/experiments/024/artifact-transfer-recovery.json`. The initial failed results remain in that file. This is artifact-transfer recovery, with zero financial replays or result changes.

Use final `artifact_receipts.json` to obtain the saved40 segment ZIPs and original Part21. Do not retry or reconstruct financial simulations. Restore the original archives into a new directory:

```bash
python scripts/restore_multifamily_archive_024.py --segments DOWNLOADED_SEGMENTS --output RESTORED_ORIGINAL_ZIPS
```

The helper verifies every wrapper and chunk and requires the complete original ZIP SHA256 to match. Copy the independently saved Part21 alongside restored Parts1–20, then extract all21 original archives into one directory. Full-result files are independently pinned by `full_result_hashes.json`; each original archive includes its complete member inventory. Reporting-stage sources and later persistence receipts in the final Git commit are authoritative; original archived snapshots intentionally remain unchanged.
