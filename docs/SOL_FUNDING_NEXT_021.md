# Next bounded gap: genuine SOL funding changes

This is a plan, not an active replay freeze and not a new strategy result. Keep the021 strict8h rejection and every frozen013/014/017/019/020/021 source unchanged.

The already persisted official2022–2025 SOL inputs contain35,064 validated trade candles,35,064 mark candles and4,458 actual funding rows. The raw funding interval column contains4,357 rows marked8h, two4h and99two-hour rows. All432monthly and26daily archives across the three requested assets have public checksum evidence. No new collector package or user upload is necessary for this specific gap.

Observed source transitions (all UTC) are:

|Actual timestamp|Interval column|Gap from preceding event|
|---|---:|---:|
|2022-11-09 20:00:00.018|4h|4h|
|2022-11-10 04:00:00.011|2h|4h|
|2022-11-18 16:00:00.000|8h|8h|

The interval column cannot simply be interpreted as the elapsed interval ending at every row: the first2h-labeled row follows a4h gap. Binance's2022-11-09 announcement confirms the initial4h change and explicitly says further changes may occur without another announcement. Source: https://www.binance.com/en/support/announcement/detail/e8be17e1e544418490e86723d84759f0 . These observed transitions do not justify inventing missing settlement rates.

Before any SOL PnL, a separate additive contract must define and pin the exact genuine event schedule, transition interpretation, timestamp jitter and hour-open mark proxy. Audit that schedule against the preserved raw row timestamps and interval column, rejecting duplicates, impossible gaps, missing scheduled rows and any unexplained transition. Disclose the limits of archive-only schedule confirmation; do not claim independent current API confirmation. Retain raw timestamps/rates without eight-hour aggregation or interpolation.

Use synthetic fixtures to check each transition, deletion of one event, duplicates, before/after-position timing and the independent funding cash-flow oracle. Reuse validated Decimal execution/accounting. Keep the original six signals, costs, delays, funding sensitivities, windows and acceptance thresholds; never change rules because a new asset's performance is weak. Publish new source/tests/input hashes and an active attempt before computing results. At most one bounded SOL matrix in that iteration, with train-only selections frozen before evaluation and all outcomes retained.

If the single consolidated Bybit packet arrives first, prioritize unchanged013. No new prospective cohort, order or account authorization is implied. Full BTC/XRP021 outcomes must be completed/preserved before starting this next batch.
