# Bybit013replay engine: frozen before real historical PnL

This additive implementation completes the hourly adapter for the existing013design. It does not change the six daily signal definitions, the original013collection/design freeze, the shipped014collector, or either Coinbase prospective cohort. No real Bybit historical strategy calculation has run in this implementation stage. Tests use synthetic prices/funding; they are software evidence, not profitable trading evidence.

## Execution and accounting

- Each asset/candidate/scenario starts flat with10000USDT. Independent results must never be summed as one10000USDT portfolio.
- Signals use exactly24complete UTC traded-price candles per day. The frozen original signal functions are reused. Closed dayD is first eligible at01:00UTC onD+1+lag, with lag0,1,2days. The volatility sizing input is delayed with the signal; missing sizing volatility rejects entry. Fixed50sizing does not need that feature.
- One long position or flat. No pyramiding or shorting. Entry notional at most50%of current cash equity; no subsequent weight rebalance. Quantity is floored to current qtyStep, prices rounded adversely to current tickSize. Entries outside current min/max quantity/notional constraints are rejected and retained, never resized or split.
- Time exits count elapsed UTC days from actual entry. Exit decisions take precedence; a time exit cannot immediately reenter in the same hour.
- Funding uses the position held before the event, its actual quantity, settled rate and that hour's mark open. Positive funding is paid by a long, negative funding received. Every event, including flat events, is recorded once. Nominal mark valuation and adverse5bpsvaluation are separate runs.
- Full hourly trade and mark grids and the original eight-hour funding grid plus pre-start anchor are mandatory. A changed/missing funding cadence stops the batch for review. Bybit can change funding frequency; the assumed grid is a validation constraint, not an assertion that every contract always funds every eight hours.
- Cash accounting uses Decimal precision128. Operating expense120USDT/365.25days accrues by completed hour; cumulative expense is rounded to18decimal places and the difference is charged. Idle cash has zero operating expense. Fees and funding use unrounded finite decimal inputs.
- Each hourly opening mark is sampled before funding, after funding and after a01:00decision, as applicable; hourly closing marks are sampled after operating expense and terminal close. Estimated exit taker fees are reserved on open-position equity. Sampled maximum drawdown therefore includes these chronological endpoint/event samples. The USDT drawdown is the actual peak-minus-trough at the maximum percentage drawdown, with maximum cash drawdown also reported separately.
- Intrahour low-equity excursion is compared with the preceding sampled peak after charging that hour's expense. High/low ordering is unknown; those extrema are never inserted as a fictitious chronological price path. Both extremes are checked against the fully cash-backed guard, including the exit-fee reserve. A failure stops with MARGIN_MODEL_UNSUPPORTED, preserves open exposure and partial accounting, and receives no successful full-window score. This is not an exchange liquidation model.
- The scheduled terminal close uses the final fully closed traded candle's close, adverse slippage and fees. Its synthetic timestamp is the final millisecond of that candle. Funding at the exclusive next-day boundary belongs to neither the old position after close nor an inherited position in the next independent window. This endpoint convention is disclosed; hourly data cannot establish an exact executable final tick.
- A second oracle uses mark-to-mark wealth changes, position changes and independent fee/funding/expense reconstruction. It verifies every event, the sampled equity curve, drawdowns, final wealth and completed-trade reconciliation.

## Bounded research matrix

Original windows remain:2021warmup,2022–2023training,2024-01-01through2026-10-15evaluation. The extra prices collected after that cutoff are not included automatically.

| Stage | Scope | Runs |
|---|---|---:|
| Training |6candidates ×3assets ×2costs; lag0, nominal funding |36|
| Evaluation |6candidates ×3assets ×2costs ×3lags ×2funding valuations |216|
| Evaluation benchmarks |3assets ×(cash +50%hold under2costs ×2valuations) |15|
| Total |Independent scenario executions, not independent hypotheses |267|

Training selection is written to a SHA256-pinned selection.json before evaluation can run. Both training costs must have positive net PnL, sampled drawdown at most35%, at least10nonterminal exits, and no margin/accounting failure. Rank by stress annualized net return divided by max(stress drawdown,1%); tie by candidate ID. If none qualify, select cash. Time exits count as nonterminal strategy exits; scheduled research terminal closes do not.

Every candidate receives all12evaluation scenarios, regardless of training selection. The historical gate requires positive net PnL, drawdown at most35%, at least20nonterminal exits and complete/audited accounting in every scenario. Failed cases and entry rejections remain in the output.35%is a research screen, not user risk consent. A separate descriptive opportunity table compares worst-scenario returns, USDT amounts and failure reasons, retaining strong-but-incomplete ideas without changing training selections. A historical pass is exploratory; families were selected using already-seen, correlated Coinbase history.

## Input and reproducibility

scripts/run_bybit_replay_013.py accepts the one BYBIT_SEND_THIS.zip and its externally computed SHA256. It first runs the unchanged014auditor, then assembles and revalidates the original013core offline. Optional live/supplement gaps remain in the receipt but do not discard a complete historical core. The original013ZIP is also supported. Archive code is never executed. The entire frozen core interval must be present; no interpolation or silent shorter test window.

The runner verifies the externally supplied engine-freeze hash, every frozen source/contract hash and pinned Python major/minor and package versions. Outputs must use new directories. Failures preserve partial evidence and a stopped.json; rerunning cannot overwrite it. Training selection and all its result-file hashes are revalidated before evaluation. Current filters, fee assumptions, fixed slippage, hourly mark valuation and account margin limitations remain disclosed proxies.

Commands (replace placeholders after auditing the returned packet):

```bash
python scripts/run_bybit_replay_013.py --input BYBIT_SEND_THIS.zip --sha256 INPUT_SHA256 --engine-freeze-sha256 ENGINE_FREEZE_SHA256 --stage train --output NEW_TRAIN_DIRECTORY
python scripts/run_bybit_replay_013.py --input BYBIT_SEND_THIS.zip --sha256 INPUT_SHA256 --engine-freeze-sha256 ENGINE_FREEZE_SHA256 --stage evaluate --training-directory NEW_TRAIN_DIRECTORY --selection-sha256 SELECTION_SHA256 --output NEW_EVAL_DIRECTORY
```

No new user collection step is required. The already-issued START_ALL.cmd and BYBIT_SEND_THIS.zip remain the handoff. No credentials, real orders, paid services or new forward cohort are involved.

Official references checked2026-10-16:

- https://www.bybit.com/en/help-center/article/Funding-fee-calculation
- https://www.bybit.com/en/help-center/article/Profit-Loss-calculations-USDT-Contract
- https://bybit-exchange.github.io/docs/v5/market/mark-kline

Verification results and exact source/runtime pins are stored in research/experiments/013/engine-verification-v1.json and engine-freeze-v1.json.
