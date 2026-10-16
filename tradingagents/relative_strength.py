"""Experiment015: causal relative-strength leader filter, no shared portfolio.
Exactly one family and two existing sizings. No network or execution capability.
"""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from tradingagents.opportunity_discovery import curve_diagnostics, pareto_tiers

PRODUCTS = ('BTC-USD', 'ETH-USD', 'LTC-USD')
FAMILY = 'relative_leader28'
SIZINGS = ('fixed50', 'vol15_cap50')


@dataclass(frozen=True)
class Candidate:
    family: str
    sizing: str

    def __post_init__(self):
        if self.family != FAMILY or self.sizing not in SIZINGS:
            raise ValueError('Unregistered015 candidate')

    @property
    def id(self): return f'{self.family}__{self.sizing}'


CANDIDATES = tuple(Candidate(FAMILY, size) for size in SIZINGS)


def signals(frames):
    """Rank only simultaneously closed UTC candles. Never fill a missing peer.

    Every column has the same date grid. Lexical tie order is fixed in PRODUCTS.
    An asset is eligible only when it is leader and its28dayreturn is positive.
    Warmup requires all three60day volatility features as well as28day returns.
    Output is a per-asset eligibility filter, not transfers among shared accounts.
    """
    if set(frames) != set(PRODUCTS): raise ValueError('All three registered assets required')
    dates, index = None, None
    close = {}
    for symbol in PRODUCTS:
        frame = frames[symbol]
        stamps = pd.DatetimeIndex(frame.Date)
        if (len(stamps) == 0 or stamps.tz is None or str(stamps.tz) != 'UTC'
                or not stamps.is_unique or not stamps.is_monotonic_increasing
                or not stamps.equals(stamps.normalize())
                or (len(stamps) > 1 and not ((stamps[1:] - stamps[:-1]) == pd.Timedelta(days=1)).all())):
            raise ValueError('Complete consecutive UTC daily candles required')
        if dates is not None and (not dates.equals(stamps) or not index.equals(frame.index)):
            raise ValueError('Peer date/index alignment mismatch')
        dates, index = stamps, frame.index
        values = frame.Close.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any(): raise ValueError('Invalid peer close')
        close[symbol] = pd.Series(values, index=index)
    prices = pd.DataFrame(close, index=index)
    momentum = prices / prices.shift(28) - 1
    volatility = prices.pct_change(fill_method=None).rolling(60, min_periods=60).std(ddof=1) * math.sqrt(365.25)
    ready = momentum.notna().all(axis=1) & volatility.notna().all(axis=1)
    # argmax chooses the first equal value in fixed lexical column order.
    leader = pd.Series(np.array(PRODUCTS)[momentum.fillna(-np.inf).to_numpy().argmax(axis=1)], index=index).where(ready)
    output = {}
    for symbol in PRODUCTS:
        eligible = ready & leader.eq(symbol) & momentum[symbol].gt(0)
        output[symbol] = pd.DataFrame({'entry': eligible.astype(bool),
            'exit': (ready & ~eligible).astype(bool), 'vol60': volatility[symbol], 'max_hold': 0,
            'momentum28': momentum[symbol], 'leader': leader, 'ready': ready})
    return output


def select(training):
    if set(training) != {c.id for c in CANDIDATES} or any(set(v) != {'base', 'stress'} for v in training.values()):
        raise ValueError('Both new candidates and costs required')
    ranked = []
    for candidate in CANDIDATES:
        pair = training[candidate.id]
        if all(m['profit_after_operating_usd'] > 0 and m['max_close_drawdown_pct'] <= 35
               and m['closed_trades'] >= 10 for m in pair.values()):
            m = pair['stress']
            ranked.append({'id': candidate.id, 'score': m['annualized_after_operating_pct'] / max(m['max_close_drawdown_pct'], 1.)})
    ranked.sort(key=lambda r: (-r['score'], r['id']))
    return {'selected': ranked[0]['id'] if ranked else 'cash', 'eligible': ranked,
            'selection_universe': 'Only the two preregistered015variants; old42selection/cohorts unchanged.'}


def assess(matrix, delays, candidate):
    checks, lag_checks = {}, {}
    for cost in ('base', 'stress'):
        for window in ('full', 'validation', 'recent'):
            m = matrix[f'{window}__{cost}__{candidate}']['metrics']
            checks[f'{window}_{cost}_positive'] = m['profit_after_operating_usd'] > 0
            if window == 'full':
                checks[f'full_{cost}_drawdown'] = m['max_close_drawdown_pct'] <= 35
                checks[f'full_{cost}_20trades'] = m['closed_trades'] >= 20
            elif window == 'validation': checks[f'validation_{cost}_5trades'] = m['closed_trades'] >= 5
        for lag in (1, 2):
            m = delays[f'lag{lag}__{cost}__{candidate}']['metrics']
            lag_checks[f'lag{lag}_{cost}_positive'] = m['profit_after_operating_usd'] > 0
            lag_checks[f'lag{lag}_{cost}_drawdown'] = m['max_close_drawdown_pct'] <= 35
    return {'id': candidate, 'historical_pass': all(checks.values()),
        'robust_pass': all(checks.values()) and all(lag_checks.values()), 'checks': checks,
        'delay_checks': lag_checks, 'failed': [k for k,v in checks.items() if not v],
        'delay_failed': [k for k,v in lag_checks.items() if not v]}


def opportunity_row(symbol, candidate, matrix, delays, assessment, selection):
    scenarios = []
    for lag in (0, 1, 2):
        for cost in ('base', 'stress'):
            result = matrix[f'evaluation__{cost}__{candidate}'] if lag == 0 else delays[f'lag{lag}__{cost}__{candidate}']
            m = result['metrics']
            scenarios.append({'lag_days': lag, 'cost': cost, 'return_pct': m['return_after_operating_pct'],
                'pnl_usd': m['profit_after_operating_usd'], 'signal_exits': m['signal_exits'],
                'closed_trades': m['closed_trades'], **curve_diagnostics(result)})
    worst = min(scenarios, key=lambda x: x['return_pct'])
    return {'product': symbol, 'id': candidate, 'family': FAMILY,
        'classification': 'POST_HOC_SPOT_DISCOVERY_NOT_PERPETUAL_VALIDATION',
        'historical_robust_pass': assessment['robust_pass'],
        'failed': assessment['failed'] + assessment['delay_failed'],
        'selected_within_new_family_by_training': selection['selected'] == candidate,
        'worst_return_pct': worst['return_pct'], 'worst_pnl_usd': worst['pnl_usd'],
        'worst_return_scenario': {'lag_days': worst['lag_days'], 'cost': worst['cost']},
        'worst_drawdown_pct': max(s['max_drawdown_pct'] for s in scenarios),
        'min_signal_exits': min(s['signal_exits'] for s in scenarios), 'scenarios': scenarios}


def compare(old_rows, new_rows):
    rows = [dict(r) for r in old_rows + new_rows]
    if len(rows) != 44 or len({r['id'] for r in rows}) != 44: raise ValueError('All44 distinct candidates required')
    pareto_tiers(rows)
    rows.sort(key=lambda r: (not r['historical_robust_pass'], r['pareto_tier'],
                            -r['worst_return_pct'] / max(r['worst_drawdown_pct'], 1), r['id']))
    for index, row in enumerate(rows): row['review_rank'] = index + 1
    return rows
