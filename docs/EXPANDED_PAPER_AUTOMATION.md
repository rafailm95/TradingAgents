# Expanded exploratory forward cohort008

On2026-10-16 the user authorized adding the five experiment007 historical-screen
passes and continuing tests without repeated prompts. These five remain
`POST_HOC_EXPLORATORY_DELAY_FAILED`: ADX fixed50, Aroon fixed50, Aroon vol15,
CMO vol15 and squeeze breakout vol15. Their past delay-test failures are retained.

The original two-candidate campaign remains on its original branch and source
pins. This additional campaign uses `codex/expanded-paper-20261016` and
`campaigns/btc-expanded-008/`, with fourteen independent10000USD books: five
candidates plus cash and buy_hold_50, each under base and stress costs.
No portfolio pools the seven candidates or represents a real account.

## Frozen execution

Runtime manifest `docs/EXPANDED_AUTOMATION_RUNTIME.json`:
`7e8d7cbe7758c2fd3fd4313b102d4f9729627e32bc0fe757e048dd55e973b2b8`.

Generation-zero checkpoint:
`56f2ba90a7aa606afc40d6cdd57791d6874c339156d6bf54b029a75bb1e56667`.

The manifest binds19 source/configuration/input files. Verify its external
SHA256 and every listed source before importing code, normalizing CRLF to LF.
Use Python3.12 and `requirements-research.txt` in an isolated environment.
The entry point disables dotenv discovery. No broker keys, paid models or orders.

```bash
python scripts/run_expanded_campaign.py --campaign-dir campaigns/btc-expanded-008 --runtime-sha 7e8d7cbe7758c2fd3fd4313b102d4f9729627e32bc0fe757e048dd55e973b2b8
python scripts/expanded_forward_status.py --campaign-dir campaigns/btc-expanded-008
```

Use the actual clock. First eligible candle2026-10-17; earliest observation
2026-10-18T00:00Z. A run earlier than that must wait without reading prices or
recording positions. Setup readiness correctly returned WAITING with0quotes,
0observations,0events and no state mutation.

ADX is recursive. A moving200-candle seed would silently change its rules.
Instead all snapshots retain the exact original2019-01-01..2026-10-15 CSV prefix,
then append actual daily prices. Download only the missing price interval.
Historical gaps may supply indicators; no observations, fills or PnL are invented
for missed days. Previously accepted price bytes never change. One causal
indicator calculation per journal replay supplies all prefix-equivalent records.
The original research modules and all14 original campaign source files are unchanged.

The new ledger/checkpoint modules intentionally isolate copies of the frozen
accounting/verification code; only cohort bindings, full-history observation and
storage limit differ. This avoids changing the existing running contract.
Future bug repairs need a versioned contract and explicit state migration;
standing research authorization does not allow silently rewriting accepted events.

## Persistence and failures

Fresh clone the dedicated expanded branch each run; record its starting head
and tree. Never bootstrap/reset a missing checkpoint. Verify complete state and
replay before one execution attempt. Fetch a fresh public ticker only after
the signal; buy ask plus slippage, sell bid minus slippage, fees both sides.
Retain actual receipt time. Never substitute a next-open historical execution.

If `publish_files` is nonempty, publish exactly those files under the campaign
directory using original tree, original commit parent, `expected_sha` and
`force=false`. Never force, merge a competing proposal, rerun a virtual fill,
or rewrite previous accepted state. Preserve a pending signal/quarantine even
when the run exits nonzero. Verify the remote head and checkpoint afterward.
No successful publication means no claim of an accepted forward event.

Stale pending observations, locks, missing or changed files, source mismatches,
quote failures and access failures are explicit blockers, not profit signals.
One request per required candle page and one quote attempt; no automatic retry.
Core storage is bounded at10000files/500MB; snapshots at5MB/10000rows. Bounds
eventually require a planned archival migration; never delete history to proceed.

## Forward milestone

Read-only `expanded_forward_status.py` requires at least180elapsed days and
20closed exit trades per cost book, positive net liquidation PnL after modeled
operating expense under bothcosts, sampledDD<=35%, coverage>=95% of eligible
calendar days and no pending observations. The campaign verifier must first
pass. This is a monitoring milestone, not statistical proof or real-order authority.

Daily timing is established by the automation tool, not this document. The
same daily task runs the original two and the separate five independently.
Weekly research has another task and another branch, avoiding write races.

RESOLVED: Five exploratory candidates added with causal full-history replay.
OPEN: Prospective evidence; no forward events existed at setup.
IMPLEMENTATION_READY: Public-data paper observation and research only.
MATERIAL_BLOCKER: Past delay robustness failed; future profitability unknown.
NEXT_IMPLEMENTATION_SLICE: First eligible observation and queued weekly batch011.
DONE_CONDITION: Both schedules enabled and source/checkpoint deployment verified.
EXECUTION_ENVIRONMENT: Python3.12, pinned research dependencies, fresh remote checkout.
REQUIRED_MODE: Research/virtual accounting; no real orders.
