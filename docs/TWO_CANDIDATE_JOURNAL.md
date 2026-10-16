# Two-candidate prospective signal journal — experiment 004

## Implemented scope

`tradingagents.candidate_journal` records two frozen BTC-USD condition sets
together in one daily observation. It preserves their distinct provenance:

| Candidate | Selection provenance |
|---|---|
| `breakout20__vol15_cap50` | Training-period winner, cutoff 2023-12-31; broader history had already been reused in earlier studies. |
| `sma200_band__vol15_cap50` | Post-hoc exploratory candidate identified after comparing known history through 2026-10-15. |

The watchlist, parent research protocol, signal implementation and CSV
validator are hash-bound after normalizing Windows CRLF line endings to LF.
No other source changes are normalized. This is normalized-source identity,
not a claim that a CRLF checkout has identical raw bytes to an LF checkout.
Every record also identifies the observer's normalized source
build. A changed rule/build requires explicit versioning and a separate
migration decision; it cannot silently continue the old journal.

The original `signal_journal` and all historical simulation rules are unchanged.
This new journal has a separate directory and refuses to adopt a legacy or
unknown nonempty directory.

## Daily boundary and timestamps

- First eligible candle: **2026-10-17 UTC**.
- Earliest observation: **2026-10-18 00:00 UTC**, 03:00 Cyprus on that date.
- Only yesterday's completed UTC candle can be recorded. No `--as-of`, simulated
  clock, or historical backfill option exists in the production CLI.
- Missing days stay missing; a later observation records the number of omitted
  days. It does not invent observations for them.
- Actual observation time and seconds since candle completion are retained.
  They do not imply an executable fill at the already elapsed next-day open.
- A UTC date rollover while processing input refuses the attempt.

## Persistence and consistency checks

One journal directory contains the LF-normalized `watchlist.json` and one directory per
observed day. Each day contains `candles.csv` (the exact 200-row replay snapshot)
and `observation.json` (signals, sizing, provenance, source metadata and chain).

The full caller input is structurally validated, read once and hashed. Exactly
the last 200 completed rows are retained; those are sufficient for these two
finite-lookback rules. The calculation uses the same stored CSV representation
that later replay reads. Actual exchange origin is not authenticated by this
journal. The optional downloader retains public-response provenance separately.

Before appending, every previous observation is replayed. Byte hashes, rule
identity, source shape, timestamps, sequence and calculated values are checked.
A cooperative exclusive lock prevents simultaneous journal writes. Files are
created exclusively, flushed and read back before `RECORDED` is returned.

An identical used snapshot returns `ALREADY_RECORDED` without replacing the
original observation time or provenance. Changes outside the used 200-row
window do not rewrite the original source hash. A revised used window conflicts.

Partial writes, inconsistent snapshots, changed stored signals, unknown files,
changed rules and leftover locks fail closed. No automatic overwrite, repair,
lock removal or retry occurs. Preserve the directory and inspect it if an
error occurs. The CLI uses `ERROR_REQUIRES_INSPECTION` and
`record_created=UNVERIFIED` when an error could have occurred during persistence.

These are local consistency checks, **not** an authenticated, tamper-proof or
externally timestamped ledger. A privileged actor can coherently rewrite a
journal or remove a complete trailing record without an external checkpoint.
There are no broker credentials, LLM calls, orders, positions, fills or P&L.

## One-command public-data observation

`scripts/observe_candidates.py` is an on-demand wrapper around the existing
Coinbase public-candle downloader. Before eligibility it does no download and
creates no state directory. It also skips a download if today's required
observation is already present and verifies successfully.

Otherwise it requests exactly the 200 required completed days in one bounded
downloader invocation, retains the raw response/provenance, and invokes the
journal. A failed or timed-out download is not retried and does not create a
new observation. Parallel wrapper invocations may both download public data;
the journal lock still prevents concurrent writes.

The script is **not a scheduler** and does not remain running after it exits.

From this code's repository directory on Windows, with an isolated research
environment, setup is:

```powershell
py -3.12 -m venv .venv-research
.\.venv-research\Scripts\python.exe -m pip install -r requirements-research.txt
```

The setup installs the listed open-source packages; it makes no paid model call.
The user-facing invocation is then:

```powershell
.\.venv-research\Scripts\python.exe scripts\observe_candidates.py --state-dir ..\two-candidate-observations
```

The command can be run now as a readiness check. Until the boundary above it
returns `WAITING_FOR_NEW_CANDLES`. After that boundary it makes public network
requests. Do not place real-account credentials in this research environment.

Verify existing observations without downloading data:

```powershell
.\.venv-research\Scripts\python.exe -m tradingagents.candidate_journal --journal ..\two-candidate-observations\journal --verify-only
```

To use an independently prepared CSV instead of downloading:

```powershell
.\.venv-research\Scripts\python.exe -m tradingagents.candidate_journal --csv C:\path\btc_coinbase_daily.csv --journal ..\two-candidate-observations\journal
```

Source CSV columns are `Date,Open,High,Low,Close,Volume`. Require 200–4000
consecutive, sorted, unique UTC daily candles, valid OHLC, non-negative volume,
no non-finite values and at most 5 MB. The last row must be yesterday UTC.

## Validation completed 2026-10-16

**112 targeted tests passed** in the isolated numerical suite. The set includes
the old journal and strategy/backtest regressions. New tests cover provenance,
UTC boundaries/timezones, direct indicator/sizing arithmetic, duplicate
preservation, stale/future/gapped/malformed inputs, late starts, missed days,
replay and hash conflicts, modified rules, partial writes, lock refusal,
timezone-naive clocks, midnight rollover, Windows CRLF source identity and
downloader failure/no retry.

Every future-dated fixture is synthetic and uses a mocked function clock. It
is not real market evidence. The actual-clock wrapper on 2026-10-16 returned
`WAITING_FOR_NEW_CANDLES`; verification returned `NOT_INITIALIZED`. There are
zero actual prospective records and no actual download in that readiness run.

Runtime tested: Python 3.12.14, numpy 2.3.5, pandas 2.2.3,
python-dotenv 1.2.4, pytest 9.1.1. The focused test command intentionally excludes
the full application's provider-dependent conftest; this is not a full-repo CI
or Windows-host execution claim.

```bash
python -m pytest --noconftest tests/test_candidate_journal.py tests/test_observe_candidates_runner.py tests/test_signal_journal.py tests/test_strategy_lab.py tests/test_strategy_backtest.py tests/test_entry_allocation.py -q
```

## Next implementation slice

Add a separate virtual portfolio ledger using only observations that were
actually collected. Define fills at or after the recorded knowledge time,
cash/position accounting, fees, stale-data refusal and both benchmarks before
reporting prospective P&L. A delayed observation must never get a retroactive
fill at the historical next-day opening price. Live order placement and
permanent scheduled execution remain outside this implementation.

```text
RESOLVED=TWO_CANDIDATE_JOURNAL_AND_ON_DEMAND_RUNNER
OPEN=FIRST_NEW_OBSERVATIONS_AND_PROSPECTIVE_PNL
IMPLEMENTATION_READY=YES
MATERIAL_BLOCKER=NONE_FOR_VIRTUAL_LEDGER_IMPLEMENTATION
NEXT_IMPLEMENTATION_SLICE=TIMESTAMP_AWARE_VIRTUAL_PORTFOLIO_LEDGER
DONE_CONDITION=REPLAYABLE_FILLS_NEVER_PRECEDING_OBSERVATION_TIME
EXECUTION_ENVIRONMENT=ISOLATED_RESEARCH_WORKSPACE
REQUIRED_MODE=DEFAULT
```
