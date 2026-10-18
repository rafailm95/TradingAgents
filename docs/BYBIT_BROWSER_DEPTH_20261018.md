# Depth now, then history — additive browser profile2026-10-18

User authorization: “Since you need depth recording, why not do it now?” Extend the easier browser collection to take live public depth immediately, without changing the frozen013/014/026contracts or the previous delivered history-only notebook. This is collection infrastructure, not a strategy batch.

## Exact bounded behavior

`notebooks/Bybit_Depth_and_History_One_Click.ipynb` embeds the exact original026package and the separately hashed `scripts/collect_bybit_depth_browser.py`. Run all in a user-controlled ColabCPU session. No dependency installation, GPU, Bybit keys/login, GoogleDrive permission, paidservice, trade or privateAPI is used.

The first requests are live instrument/ticker/book measurements. Default25rounds have at least300seconds between starts, approximately2hours start-to-start. Each round uses unchanged026 `live_asset` for BTCUSDT,ETHUSDT,LTCUSDT,SOLUSDT,XRPUSDT: currentinstrument,ticker,two1000-levelbook requests separated at least2seconds,and100recentpublictrades. Up to250validbook responses are possible, but actual distinct timestamps, acceptedbooks, gaps and validity determine reported coverage. RPIorders excluded by the source endpoint are not invented. These are sampled snapshots/trade tails, not continuous level2, fulltrades or actualfills.

After this first depth sample, unchanged026historical collection runs/reuses verifiedpages. One `BYBIT_SEND_THIS.zip` contains the availabledepth and history. No closingextension or finalriskrefresh is claimed. Original026livegoal remains865rounds/~72hours in its unchangedplan. A25roundbrowsercapture is therefore PARTIAL against the fullgoal. A long gap cannot be labeled continuously observed hours. The fullWindows026packet remains the route for requesting the original multidaygoal.

The browser wrapper admits at most25newrounds, pins the initialcount/target, and refuses silenttargetexpansion. Each run has a21600second pre-request budget; original40000requests/350MBcompressed evidence/480MBZIP/sevendays bounds remain. Cachedhistory reads are not newnetworkrequests. Packaging/auditingtime is additional; no guarantee of successful capture within a cloudruntime lifetime.

Every completedround writes a fresh atomicZIP checkpoint. Stop once catches KeyboardInterrupt, retains rawresponses, closes any pendinground with explicit INTERRUPTED assets, and packages evidence. Resume uses a new roundID after an interruptedround; it never fills the old round with newquotes. Previousaccess/integritystops forbid automatic cell-rerun networkretry. HTTP403/HTML stops without alternatehost, proxy or regionchange. AbruptColabVM deletion can still lose files not downloaded. The wrapper does not defeat idlelimits or cloudsessionpolicy.

## Preserve an existing historical download

If the previousnotebook is running, let it finish and download its ZIP. In the newnotebook, select the optional `IMPORT_EXISTING_ZIP` checkbox before Runall and choose that existingresult. Otherwise leave it unchecked. Notebooks are not assumed to share a runtime.

`import_packet` independently hashes and invokes the unchanged026offlineauditor before extracting only its bounded, flat, allowlisted data. It never executes uploadedcode and refuses a nonemptydestination. Originalrawresponses/requestrecords, pinnedhistorycutoff andsourceidentity remain unchanged. The importedarchiveSHA, previousprofile/status/summary are retained in state. Sameprofile continuation preserves its depthtarget. If a previousresult contains an accessblock, import does not clear the block or trigger a retry. A resulting packet must again be independentlyaudited before researchuse.

ReturnedZIPs use unchanged`scripts/audit_bybit_packet_026.py`. Original013completecore remains mandatory for the original6variantreplay. The alreadydocumented additive026inputbridge must still be frozen before realPnL. Depth collection does not authorize changing those variants, costs or papercohorts.

## Verification and actual work

Python3.12.14 isolatedresearch environment:57tests passed,11newdepth-profilecases plus46existingbrowser/026cases. No testfailed in this iteration: preliminary55passed; twoadditional checks verifytargettampering and standalone notebook setup underPython-S. Synthetic cases verifydepthbeforehistory,20booksfrom2shortfixture rounds, originalfullgoal remainsPARTIAL, cell-rerun cache reuse, accessblockone-requeststop, pairinterruption/no backfill, observedgapretention, waitbudgetcheckpoint/resume, pre-next-roundZIP, auditedprevioushistoryimport/no redownload, wronghash/nonemptydestinationrefusal, andsourceprofileisolation.

No actualBybitrequests, realColabexecution, newmarketobservations or strategysimulations occurred in this iteration. The earlier2026-10-18runtimeAPI/archivechecks returnedHTMLSiteUnavailable; thosefailurebytes remain in browser-profile/access-check. ActualColab→Bybitaccess is still unverified. Existing36Bybitbooks/600fundingevents remain actualprior evidence. Researchcounts remain90variants/45families,9894designexecutions+7integrityreplays=9901knownexecutions. All previoussource/freezes and prospectivepins are verified unchanged, except additive mutable registrymetadata.

Reproduce:
```
python scripts/build_bybit_depth_notebook.py --output notebooks/Bybit_Depth_and_History_One_Click.ipynb
python -m pytest --noconftest -q tests/test_bybit_depth_browser.py tests/test_bybit_history_browser.py tests/test_bybit_packet_026.py tests/test_bybit_packet_026_extensions.py
```

Primary references checked2026-10-18:
- https://bybit-exchange.github.io/docs/v5/market/orderbook
- https://research.google.com/colaboratory/faq.html

The officialColabFAQ permits at most12hours per free session depending on availability/usage and describes idletermination; this is not a reliable72hourhost. No runtimekeepalive bypass is introduced. Collecting a shorter truthful sample now is useful without presenting it as completehistorical/futureliquidity or proof of profitability.
