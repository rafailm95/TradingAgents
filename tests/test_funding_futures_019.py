"""Synthetic tests only: no archived market outcomes read before freeze."""
import copy
from dataclasses import replace
from decimal import Decimal as D, localcontext
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_bybit_replay import dataset, signals, START, FIRST
from tradingagents import bybit_replay as original
from tradingagents import futures_replay_019 as new
from tradingagents.funding_signal_019 import funding_signals, NEW_CANDIDATES
from tradingagents.bybit_history import DAY, HOUR
from run_funding_futures_019 import combine_folds, daily_returns


def market(days=240):
    d = dataset(days=days)
    for i, row in enumerate(d['trade']):
        p = 100 + i / 240
        row[1:5] = list(map(str, [p, p+2, p-2, p+1]))
    d['mark'] = [r[:5] for r in d['trade']]
    return original.prepare(d, 'BTCUSDT')


@pytest.mark.parametrize('candidate', original.CANDIDATES)
@pytest.mark.parametrize('cost', original.COSTS)
def test_derivative_identical_accounting_to_frozen_engine(candidate, cost):
    m = market(204)
    sig = signals(m, (199,), (201,), vol=.7)
    kwargs = dict(candidate=candidate, cost=cost, prepared_signals=sig, adverse_funding=True)
    a = original.replay(m, FIRST, m.end, **kwargs)
    b = new.replay(m, FIRST, m.end, **kwargs)
    for key in ('metrics', 'events', 'curve', 'fills', 'trades', 'funding_events', 'independent_wealth_audit'):
        assert a[key] == b[key]


def test_funding_and_price_prefix_causality():
    m = market()
    end = START + 220 * DAY
    full = funding_signals(m, m.end)
    cut = funding_signals(m, end)
    pd.testing.assert_frame_equal(cut, full.loc[full.index < end])
    changed = copy.deepcopy(m)
    changed.frame.loc[220:, 'Close'] = 1e6
    for t in changed.funding:
        if t >= end: changed.funding[t] = D('100')
    pd.testing.assert_frame_equal(cut, funding_signals(changed, end))


@pytest.mark.parametrize('rate,enter', [('.0001', True), ('.00010000001', False), ('-.0001', True)])
def test_exact_decimal_funding_threshold(rate, enter):
    m = market()
    m = replace(m, funding={t:D(rate) for t in m.funding})
    s = funding_signals(m, m.end)
    assert bool(s.iloc[200].entry) is enter
    assert bool(s.iloc[200].exit) is not enter


def test_funding_last_window_includes_only_closed_days():
    m = market()
    target = START + 210 * DAY
    baseline = funding_signals(m, m.end)
    m.funding[target + DAY] = D('1')  # Next midnight cannot affect target day.
    altered = funding_signals(m, m.end)
    pd.testing.assert_series_equal(baseline.loc[target], altered.loc[target])
    assert not altered.loc[target + DAY, 'entry']


def test_missing_funding_rejects_instead_of_zero_fill():
    m = market()
    del m.funding[START + 199 * DAY + 8 * HOUR]
    with pytest.raises(KeyError): funding_signals(m, m.end)


def test_nonpositive_momentum_exits_and_warmup_is_neutral():
    m = market()
    m.frame['Close'] = 100.
    s = funding_signals(m, m.end)
    assert not s.entry.any()
    assert not s.iloc[:28].exit.any()
    assert s.iloc[28:].exit.all()


@pytest.mark.parametrize('initial', ['5000', '12500', '9879.876543210987654321012345678901234567890'])
def test_explicit_cash_carry_and_expense_oracle(initial):
    m = market(204)
    r = new.replay(m, FIRST, m.end, benchmark='cash', managed_cash=True, initial_usdt=initial)
    with localcontext() as ctx:
        ctx.prec = 128
        expense = (D(120)*4/D('365.25')).quantize(D('1e-18'))
        assert D(r['metrics']['final_cash_usdt']) == D(initial)-expense
        assert D(r['metrics']['max_drawdown_pct']) == expense / D(initial)*100
        assert D(r['metrics']['cash_at_max_pct_drawdown_usdt']) == expense
    assert not r['fills']


def test_fold_capital_and_independent_combined_cashflow():
    m = market(208)
    a = new.replay(m, FIRST, FIRST+4*DAY, benchmark='cash', managed_cash=True, initial_usdt='10000')
    b = new.replay(m, FIRST+4*DAY, m.end, benchmark='cash', managed_cash=True,
                   initial_usdt=a['metrics']['final_cash_usdt'])
    c = combine_folds([a,b])
    with localcontext() as ctx:
        ctx.prec = 128
        assert D(c['metrics']['net_profit_usdt']) == -2*D(a['metrics']['operating_expense_usdt'])
        assert D(c['metrics']['cash_at_max_pct_drawdown_usdt']) == -D(c['metrics']['net_profit_usdt'])
    b['metrics']['initial_usdt'] = '10000'
    with pytest.raises(ValueError, match='continuity'): combine_folds([a,b])


@pytest.mark.parametrize('lag', [0,1,2])
def test_new_family_uses_existing_size_and_actual_delay(lag):
    m = market(204)
    sig = signals(m, (199,), (201,), max_hold=20, vol=.6)
    a = new.replay(m, FIRST, m.end, candidate=NEW_CANDIDATES[0], prepared_signals=sig, lag=lag)
    b = new.replay(m, FIRST, m.end, candidate=NEW_CANDIDATES[1], prepared_signals=sig, lag=lag)
    assert a['fills'][0]['fraction'] == '0.5'
    assert b['fills'][0]['fraction'] == '0.25'
    assert a['fills'][0]['timestamp_ms'] == FIRST+lag*DAY+HOUR


def test_full_capital_fold_chain_with_positions_not_scaled_returns():
    m = market(208)
    sig = signals(m, (199,203,204), (201,206), vol=.3)
    a = new.replay(m, FIRST, FIRST+4*DAY, candidate=NEW_CANDIDATES[0],
                   prepared_signals=sig.iloc[:204])
    b = new.replay(m, FIRST+4*DAY, m.end, candidate=NEW_CANDIDATES[0],
                   prepared_signals=sig, initial_usdt=a['metrics']['final_cash_usdt'])
    assert a['metrics']['open_quantity'] == '0'
    assert b['metrics']['initial_usdt'] == a['metrics']['final_cash_usdt']
    assert combine_folds([a,b])['status'] == 'COMPLETE'
    assert len(daily_returns(a)) == 4


def test_tampered_accounting_and_capital_fail_oracle():
    m = market(204)
    r = new.replay(m,FIRST,m.end,benchmark='cash',managed_cash=True,initial_usdt='9000')
    r['metrics']['initial_usdt'] = '10000'
    with pytest.raises(ValueError): new.audit_wealth(r)


def test_selection_has_no_future_input_and_enforces_all_candidates():
    m = market(204)
    r = new.replay(m,FIRST,m.end,benchmark='cash',managed_cash=True)
    training = {c:{cost:r for cost in new.COSTS} for c in new.CANDIDATES}
    assert new.select_training(training)['selected'] == 'cash'
    training.pop(NEW_CANDIDATES[0])
    with pytest.raises(ValueError): new.select_training(training)


@pytest.mark.parametrize('initial', ['NaN', 'Infinity', '0', '-1'])
def test_invalid_opening_capital_rejected(initial):
    m = market(204)
    with pytest.raises(ValueError): new.replay(m,FIRST,m.end,benchmark='cash',initial_usdt=initial)

