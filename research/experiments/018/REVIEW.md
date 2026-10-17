# Outcome review

All 77 archived evaluation paths were authenticated and analyzed successfully,
including all 72 candidate scenarios and five benchmarks. The unchanged wealth
oracle checked 7,149,777 events with zero Decimal discrepancy. A separate
fill/funding reconstruction checked 664 trade records across repeated scenarios;
these are not 664 independent trades or observations.

The additional descriptive filter passed 28/72 candidate scenarios and failed
44/72. No candidate passed all 12: Aroon 0/12, CCI 8/12, Keltner 4/12, OBV 8/12,
regression 8/12 and SMA200 0/12. Original full research gates remain 0/6.

OBV's baseline total net was 2,019.82 USDT, but its largest positive trade
contribution was 2,118.55 USDT. The static remainder is -98.73 USDT (-0.9873%
of initial capital); the worst of 12 such remainders is -203.44 USDT (-2.0344%).
Calendar2025 was also negative: -159.81 USDT, or -1.3121% of that year's starting
equity. The two-year profit and its attribution are not invalidated, but the
result depends strongly on a small number of events.

Keltner and CCI retain positive baseline remainders after their largest positive
trade contributions: 713.04 USDT (+7.1304%) and 926.42 USDT (+9.2642%). Under
stress costs at lag0/nominal funding these remainders remain 621.06 and 709.10
USDT. Across all delayed/adverse scenarios their worst remainders are negative:
-788.45 and -1,620.77 USDT. Preserve these strengths alongside the failures.

These are fixed-record attribution calculations, NOT missing-fill simulations
or revised strategy returns. Removing a real trade would alter subsequent
cash and sizing. The inverse winner concentration is not an independent-sample
count. No diagnostic threshold was tuned after these outcomes.

Training selection remains cash. No new expanding walk-forward was performed;
calendar attribution is explicitly not walk-forward validation. The next useful
bounded experiment is a separately preregistered expanding-window futures
selection study, with capital continuity/reset policy, annual expense treatment,
all costs/delays/funding cases and train-before-evaluation checkpoints specified
before calculation. Prioritize the unchanged Bybit013 replay if its unified
packet arrives first. No new paper cohort or live orders.
