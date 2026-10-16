# Prospective virtual portfolio ledger — experiment 005

This adds independent virtual books to the frozen two-candidate journal. It
does not change either candidate, the historical backtests, the signal journal,
or the application's account-context module. There are no real orders, account
credentials, paid model calls, or background scheduler.

The accounting and quote protocol was committed before implementation and
before any prospective observation or P&L existed:
`docs/PAPER_PORTFOLIO_PROTOCOL.json`, SHA-256
`776cb747320743eb20ef42e5900861388c5fe5d04d7ffc16e12ec7adba8b4cbc`.
The protocol, source journal and current ledger build are checked during replay.
Windows CRLF is normalized to LF for source/protocol identity only.

## Books and costs

Each row has an independent hypothetical $10,000 starting balance. These are
comparisons, not allocations of a shared real portfolio. Both cost scenarios
use the same quote and signals; the expensive scenario is not selected after
seeing its performance.

| Book | Entry/exit | Operating cost sensitivity |
|---|---|---|
| `breakout20__vol15_cap50` | Frozen training-selected rule on reused history | $120/year |
| `sma200_band__vol15_cap50` | Frozen post-hoc exploratory rule | $120/year |
| `buy_hold_50` | Buy once with 50% of starting cash; retain position | $0/year |
| `cash` | Stay in USD cash, zero modeled interest | $0/year |

| Scenario | Fee per side | Slippage per side |
|---|---:|---:|
| `base` | 60 bps | 10 bps |
| `stress` | 120 bps | 25 bps |

Fees and expenses are research assumptions, not a verified account fee tier.
Results are before taxes. Benchmark expenses deliberately differ: passive
comparators do not receive the modeled candidate operating expense.

For an entry, the frozen candidate's allocation fraction applies to available
cash while flat. The budget includes the buy fee:

```text
budget = cash * entry_fraction
buy_price = ask * (1 + slippage)
quantity = budget / (buy_price * (1 + fee))
cash -= budget
cost_basis = budget
```

Positions do not rebalance. The entry fraction is capped at 50%; market moves
can subsequently take position weight above 50%. A 15% volatility sizing input
is not a guarantee about realized volatility. When holding and the frozen exit
condition becomes true:

```text
sell_price = bid * (1 - slippage)
net_proceeds = quantity * sell_price * (1 - fee)
realized_pnl += net_proceeds - cost_basis
cash += net_proceeds
quantity = cost_basis = 0
```

One book can make at most one hypothetical fill per recorded signal day. No
shorting, borrowing, pyramiding or same-event exit/re-entry is modeled.

## Honest execution timing

The runner first records/verifies the signal, then makes one bounded GET to
the public Coinbase Exchange BTC-USD ticker. The official
[ticker reference](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker)
describes a last-trade and best-bid/ask snapshot. The response's `time` is the
last-trade time; it is **not** an independently timestamped bid/ask update.
Local request and receipt timestamps, endpoint and exact response body are
retained in the ledger event.

The protocol requires:

- Request start at or after actual signal observation; receipt after request
  start and before the event's recording timestamp.
- Request duration at most 15 seconds; HTTP timeout 10 seconds; response body
  at most 65,536 bytes; no automatic retry.
- Last-trade time at or after signal observation, not in the future relative
  to receipt, and at most 15 seconds old at receipt.
- Event recorded within 30 seconds of receipt, on the same UTC date as receipt.
  The signal candle must still be yesterday UTC at append time.
- Positive finite prices, bid no higher than ask, timezone-aware timestamps,
  strict JSON without duplicate keys or non-finite constants.

Receipt time is the hypothetical execution and valuation time. There is no
retroactive next-open fill. This is a quote-based simulation, not a broker
execution confirmation or a guarantee that the displayed price had enough
liquidity. Local response files and clocks have no external authentication.

A quote failure leaves the valid signal intact. A manual retry on that same
UTC day can use a newly fetched quote. Once that signal becomes stale, the
ledger refuses to invent an old execution. Preserve state for inspection;
there is no automatic reset, repair, overwrite or migration.

## Valuation and reporting

Each event retains cash, BTC quantity, cost basis, cumulative paid fees,
realized P&L, estimated unrealized liquidation P&L and hypothetical fill count.
It reports midpoint equity and estimated net liquidation equity separately.

```text
midpoint_equity = cash + quantity * midpoint
liquidation_equity = cash + quantity * bid * (1 - slippage) * (1 - fee)
opex = annual_opex * elapsed_seconds_since_first_receipt / 31_557_600
net_liquidation_equity = liquidation_equity - opex
net_pnl = net_liquidation_equity - 10_000
```

Estimated selling costs are included in open-position valuation but are not
counted as paid fees before a sell. Operating expense is an external sensitivity,
not a cash withdrawal or a financing assumption. It accrues across calendar
gaps. The initial $10,000 is included in the running equity peak, so immediate
entry costs appear as drawdown. Drawdown is sampled only at recorded valuations;
it does not measure missed-day or intraday lows. No stale valuation is presented
as current: every result carries its last valuation timestamp.

## Sequence and persistence

The source journal and ledger must have separate, non-nested directories.
Under cooperative locks, the ledger replays all source observations and all
existing accounting events before appending. Every recorded observation must
be consumed in order. Multiple unconsumed observations, or a stale unconsumed
observation, block the runner before downloading more data. Start this ledger
with the first actual observation; do not attach it retrospectively to a long
signal-only history.

The signal journal can have missing calendar days. Existing positions persist
across such gaps, and the next event explicitly records the number of missing
days; no intervening signals, fills or valuations are invented. A late first
observation starts its books at its actual quote receipt time.

Each event binds the source observation hash, protocol, observer/ledger builds,
quote evidence, previous event and recomputed book balances. Exclusive file
creation, fsync and read-back replay precede success. Re-running an already
consumed observation makes no new trade and does not overwrite its quote.
Malformed data, changed rules, unexpected files, incomplete writes, source
conflicts and leftover locks fail closed. CLI errors report persistence as
`UNVERIFIED` when it cannot safely be asserted that nothing was written.

Local hashes and replay detect inconsistencies, not a privileged coordinated
rewrite. Complete trailing-event removal is not externally detectable without
an independent anchor. Keep this limitation separate from numerical correctness.

## Run on demand

Use the isolated environment described in `docs/TWO_CANDIDATE_JOURNAL.md`.
The combined command replaces the signal-only invocation for this campaign:

```powershell
.\.venv-research\Scripts\python.exe scripts\observe_paper_portfolios.py --state-dir ..\two-candidate-observations
```

This verifies prior state, downloads the 200 completed candles when needed,
records the signal, fetches a fresh ticker, and appends the virtual accounts.
It exits when finished. It does not run continuously or schedule future work.

Read and replay existing state without downloading:

```powershell
.\.venv-research\Scripts\python.exe scripts\observe_paper_portfolios.py --state-dir ..\two-candidate-observations --verify-only
```

There is no production clock override or arbitrary historical fill-date option.

## Validation and real readiness — 2026-10-16

168 targeted tests passed (56 new ledger/runner cases plus 112 prior tests).
They cover independent fee/budget/exit arithmetic, cash and buy/hold benchmarks,
held position continuity, realized versus liquidation P&L, operating expense,
drawdown, quote timing and size limits, malformed data, duplicate preservation,
calendar gaps, forbidden backfill, corrupted/rehashed records, modified source
signals, partial writes, locks, Windows source line endings, single-request
HTTP behavior, download/quote failures, manual retry, and CLI failure reporting.

```bash
python -m pytest --noconftest tests/test_paper_portfolio.py tests/test_observe_paper_portfolios_runner.py tests/test_candidate_journal.py tests/test_observe_candidates_runner.py tests/test_signal_journal.py tests/test_strategy_lab.py tests/test_strategy_backtest.py tests/test_entry_allocation.py -q
```

These are focused isolated tests, not full application CI or a Windows-host
execution claim. Future fixtures, market quotes and clocks in those tests are
synthetic. The public HTTP adapter was tested with mocked responses, not an
actual prospective market execution. Existing provider-dependent conftest is
excluded. No frozen source journal or strategy code was modified.

The actual-clock combined runner returned `WAITING_FOR_NEW_CANDLES` on
2026-10-16; verification returned `NOT_STARTED`, zero observations/events and
`books=null`. No state directory, download, quote, real order or virtual fill
was created. There is no prospective P&L yet. The first eligible candle is
2026-10-17; earliest observation is 2026-10-18 00:00 UTC / 03:00 Cyprus.

The protocol and implementation are local commits. No remote branch was
published as part of this slice.

```text
RESOLVED=PROSPECTIVE_VIRTUAL_LEDGER_AND_COMBINED_ON_DEMAND_RUNNER
OPEN=ACTUAL_FORWARD_OBSERVATIONS_AND_PNL_EVIDENCE
IMPLEMENTATION_READY=YES
MATERIAL_BLOCKER=FIRST_ELIGIBLE_CANDLE_NOT_YET_COMPLETED
NEXT_IMPLEMENTATION_SLICE=FIRST_FORWARD_RUN_AND_COST_AWARE_PERFORMANCE_REVIEW
DONE_CONDITION=VERIFIED_FORWARD_EVENTS_WITH_TRACEABLE_QUOTES_AND_REPLAYABLE_BALANCES
EXECUTION_ENVIRONMENT=ISOLATED_RESEARCH_WORKSPACE
REQUIRED_MODE=DEFAULT
```
