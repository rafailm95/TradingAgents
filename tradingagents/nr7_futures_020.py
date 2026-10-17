"""Preregistered daily-close NR7 adaptation; frozen019 accounting is reused."""
import math
import pandas as pd
from tradingagents import futures_replay_019 as ledger
from tradingagents.bybit_history import DAY

NEW_CANDIDATES = ('nr7_close10__fixed50', 'nr7_close10__vol15_cap50')
CANDIDATES = ledger.CANDIDATES + NEW_CANDIDATES
COSTS = ledger.COSTS
audit_wealth = ledger.audit_wealth
evaluation_gate = ledger.evaluation_gate


def nr7_signals(market, end):
    if end % DAY or not market.start < end <= market.end:
        raise ValueError('Invalid complete-day signal boundary')
    frame = market.frame.iloc[:(end-market.start)//DAY].copy().reset_index(drop=True)
    index = list(range(market.start, end, DAY))
    if list(frame.Date.astype('int64') // 1_000_000) != index:
        raise ValueError('Daily frame mismatch')
    width = frame.High - frame.Low
    narrow = (width > 0) & (width < width.shift(1).rolling(6, min_periods=6).min())
    entry = narrow.shift(1, fill_value=False) & (frame.Close > frame.High.shift(1))
    leave = frame.Close < frame.Low.shift(1)
    vol = frame.Close.pct_change(fill_method=None).rolling(60, min_periods=60).std(ddof=1)*math.sqrt(365.25)
    return pd.DataFrame({'entry': entry.to_numpy(dtype=bool), 'exit': leave.to_numpy(dtype=bool),
                         'vol60': vol.to_numpy(), 'max_hold': 10}, index=index)


def make_signals(market, candidate, end):
    if candidate not in CANDIDATES:
        raise ValueError('Unknown candidate')
    return nr7_signals(market, end) if candidate in NEW_CANDIDATES else ledger.make_signals(market, candidate, end)


def replay(market, start, end, *, candidate=None, prepared_signals=None, **kwargs):
    if candidate not in NEW_CANDIDATES:
        return ledger.replay(market, start, end, candidate=candidate, prepared_signals=prepared_signals, **kwargs)
    signals = make_signals(market, candidate, end) if prepared_signals is None else prepared_signals
    # With prepared signals, the old ID is used ONLY to dispatch unchanged sizing.
    # No old signal is computed, no old result is relabeled, and globals are untouched.
    dispatch = 'funding_carry7_momentum28__' + candidate.split('__')[1]
    result = ledger.replay(market, start, end, candidate=dispatch, prepared_signals=signals, **kwargs)
    result['candidate'] = candidate
    result['ledger_sizing_dispatch_id'] = dispatch
    result['signal_family_source'] = 'tradingagents/nr7_futures_020.py'
    result['independent_wealth_audit'] = audit_wealth(result)
    return result


def select_training(training):
    if set(training) != set(CANDIDATES) or any(set(v) != set(COSTS) for v in training.values()):
        raise ValueError('Incomplete training matrix')
    ranked = []
    for candidate in CANDIDATES:
        pair = training[candidate]
        if all(ledger.passes(r, 10) for r in pair.values()) and pair['stress_assumption']['metrics']['annualized_net_return_pct'] is not None:
            stress = pair['stress_assumption']['metrics']
            score = stress['annualized_net_return_pct'] / max(float(stress['max_drawdown_pct']), 1.)
            ranked.append({'id': candidate, 'score': score})
    ranked.sort(key=lambda r: (-r['score'], r['id']))
    return {'selected': ranked[0]['id'] if ranked else 'cash', 'eligible': ranked,
            'basis': 'Training only, both costs at lag0, nominal funding valuation; frozen before evaluation.'}
