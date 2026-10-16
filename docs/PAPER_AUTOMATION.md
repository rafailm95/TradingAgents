# Scheduled paper campaign — experiment 006

## Deployment scope

The user authorized scheduled execution and more tests on 2026-10-16. The
deployment uses the isolated branch `codex/paper-campaign-20261016` in
`rafailm95/TradingAgents`. This public research branch contains public BTC data
and independent hypothetical books. It contains no real account balance,
credentials, order interface or paid-model integration. `main`, the upstream
repository and PHOENIX-JARVIS are outside this deployment.

The scheduled task is a web ChatGPT Work task returning to this conversation.
Its intended cadence is daily around 08:00 Asia/Nicosia, beginning 2026-10-18.
The actual automation tool confirmation, not this document, establishes whether
the schedule was activated. A scheduled time is not a guaranteed market fill.

Official [scheduled-task documentation](https://learn.chatgpt.com/docs/automations)
states that web tasks do not retain a local folder between runs. Therefore a
fresh checkout restores accepted state from the dedicated branch; it never
depends on a scratch path from this conversation or access to the user's PC.

## Frozen runtime and state

Runtime manifest: `docs/PAPER_AUTOMATION_RUNTIME.json`.
LF-normalized SHA-256:
`22c65210592af6a789cdc21014b045a515fe591d9f85f59a6213df8478b533c7`.

The manifest identifies 14 runtime source/protocol/dependency files. The
scheduled task carries that manifest hash outside the repository and verifies
all source hashes before execution. Python 3.12 and the four exact direct
dependency versions in `requirements-research.txt` are required. The scheduled
entry point disables dotenv discovery before package import. No clock override
or automatic historical backfill exists.

Campaign directory: `campaigns/btc-paper-005`.
Generation-zero checkpoint SHA-256:
`09b788c6bd96618736f740ca452b01723a7e70aa3fe0ddc492ec3d228da25ec3`.

The checkpoint records generation, predecessor checkpoint hash, exact state
file hashes, journal/ledger counts, latest day, valuation time and ledger tip.
The numerical journal and ledger are fully replayed before an attempt. Missing,
modified, unlisted or truncated accepted files block execution. There is no
automatic bootstrap when the checkpoint is absent. Runtime changes require an
explicit new pin and migration decision.

The source journal and paper rules from experiments 004/005 are unchanged.
Missing calendar days stay missing. Two strategy books and cash/buy-and-hold
benchmarks continue with the same fee/expense assumptions and provenance.

## One complete iteration

1. Make a fresh checkout of the dedicated remote branch. Retain its exact
   starting commit and tree. Do not assume a previous local directory exists.
2. Verify the external runtime hash and all listed source hashes. Use a fresh
   Python 3.12 environment with the pinned direct dependencies; no provider or
   account configuration is required.
3. Run the checkpointed command exactly once:

```bash
python scripts/run_paper_campaign.py \
  --campaign-dir campaigns/btc-paper-005 \
  --runtime-sha 22c65210592af6a789cdc21014b045a515fe591d9f85f59a6213df8478b533c7
```

For a read-only replay, add `--verify-only`.

4. Inspect the structured output even when the process exits nonzero. When
   `publish_files` is empty, do not create a remote commit. Otherwise prepare a
   commit containing exactly those files, prefixed by the campaign directory.
   All accepted old state files must remain byte-identical.
5. Publish atomically using the original remote commit as the parent and an
   expected-head, non-forced branch update. Use the GitHub connector's
   `create_tree` with the original base tree and exact UTF-8 file contents,
   `create_commit` with the original parent, then `update_ref` with
   `expected_sha` equal to that parent and `force=false`.
6. Verify the resulting remote branch and checkpoint bytes. Only then describe
   the new observation/P&L as durably accepted. Report virtual net P&L, fees,
   sampled drawdown, actual valuation time, gaps and benchmark comparison in
   Greek, preserving both candidates' selection provenance.

The tools and ordinary public read-only Git access were checked during setup.
The remote write path must still be available at each future run. Connection or
permission failures are blockers, not permission to invent or silently reset
state. No emails, comments, PRs, merges, changes to other branches or remote
force pushes are part of the scheduled task.

## Failures, races and restart

`LOCAL_PROPOSAL_READY` is a local proposal, not proof of a remote commit. If
two independent runs restore the same head, their competing children cannot
both fast-forward the branch. On an expected-head conflict, read the new head;
do not rebase/merge proposals, force a push or rerun fills automatically. The
accepted remote state is authoritative.

A quote timeout after a valid signal produces a checkpoint containing that
pending signal, which must be published despite the nonzero attempt status.
A same-UTC-day supervised retry can fetch a new quote. A stale pending signal
blocks later trading simulation; a daily task cannot backfill its old fill.
There is one attempt per scheduled run, with no automatic HTTP retry.

A partial new journal/ledger write that can be safely inventoried is published
as `LOCAL_QUARANTINE_READY`, with `INSPECTION_REQUIRED`. The next run refuses
to proceed. Old accepted files are never changed to make replay pass. Failure
to prepare or publish a checkpoint remains uncommitted/ambiguous and must be
reported. Preserve local evidence when possible; do not claim a virtual fill
was accepted merely because it was computed before an interruption.

Core state is bounded at 10,000 files and 100 MB; individual inputs also retain
their existing limits. Exact evidence bytes are preserved across Windows/Linux
checkouts with campaign-local `.gitattributes`. Candle download scratch is not
part of the remote checkpoint; replay retains the exact 200-row input snapshot,
source digest and quote response in the accepted journal/ledger. This does not
independently authenticate exchange origin or bid/ask depth.

A Git checkpoint provides a remote consistency anchor against accidental local
trailing-record deletion. It does not make the history tamper-proof against a
privileged actor rewriting both the branch and the task's trusted references.

## Additional validation

The targeted suite now includes campaign restore, checkpoint loss/changes,
unlisted trailing events, stale proposals, locks, runtime/dependency mismatch,
partial-write quarantine, rename failure, no automatic reset, pending-signal
recovery, duplicate-run preservation and disabled dotenv discovery.

Eight simultaneous local append attempts must yield exactly one event. Eight
seeded paths across two cost scenarios and 120 observations each exercise
1,920 synthetic valuations, repeatedly checking independent cash-flow,
quantity, fee, realized/unrealized P&L and sampled-drawdown identities. These
synthetic results are software checks, not profitable strategy evidence.

The setup test suite has 212 cases: 168 previous cases plus 44 new cases. It
uses `--noconftest` because unrelated provider-dependent fixtures are outside
this isolated deterministic research environment. It is not full-repository
CI or a Windows-host execution claim.

```bash
python -m pytest --noconftest tests/test_paper_campaign.py tests/test_paper_portfolio_adversarial.py tests/test_paper_portfolio.py tests/test_observe_paper_portfolios_runner.py tests/test_candidate_journal.py tests/test_observe_candidates_runner.py tests/test_signal_journal.py tests/test_strategy_lab.py tests/test_strategy_backtest.py tests/test_entry_allocation.py -q
```

Public ticker connectivity was checked once on 2026-10-16. The diagnostic
response was not inserted into the ledger and creates no prospective result.
The first prospective date remains 2026-10-17, available after 2026-10-18 00:00
UTC. Before that boundary, the combined command returns waiting without a
market download, quote, ledger event or checkpoint increment.

```text
RESOLVED=DURABLE_SCHEDULED_RUNNER_AND_EXPANDED_TESTS
OPEN=FIRST_SCHEDULED_FORWARD_OBSERVATION_AND_PERFORMANCE_EVIDENCE
IMPLEMENTATION_READY=YES
MATERIAL_BLOCKER=NONE_FOR_SCHEDULING_AFTER_REMOTE_AND_TOOL_CONFIRMATION
NEXT_IMPLEMENTATION_SLICE=FIRST_SCHEDULED_RUN_REVIEW
DONE_CONDITION=REMOTE_CHECKPOINT_CONFIRMED_AND_GREEK_RESULT_DELIVERED
EXECUTION_ENVIRONMENT=WEB_SCHEDULED_TASK_WITH_FRESH_RESEARCH_CHECKOUT
REQUIRED_MODE=DEFAULT
```
