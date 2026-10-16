"""Synthetic tests before observing any015historical strategy outcomes."""
import copy
import numpy as np
import pandas as pd
import pytest
from tradingagents import relative_strength as relative
from scripts.run_weekly_confirmation_lab import simulate
from tests.test_strategy_backtest import frame_for


def frames(n=500):
    return {symbol: frame_for(100 + np.arange(n) * slope) for symbol,slope in zip(relative.PRODUCTS, (.2,.4,.1))}


def test_manual_relative_return_leader_and_nonpositive_cash():
    data = frames(); result = relative.signals(data)
    for i in (60, 100, 250):
        ratios = {p: data[p].Close.iloc[i] / data[p].Close.iloc[i-28] - 1 for p in relative.PRODUCTS}
        leader = max(relative.PRODUCTS, key=lambda p: ratios[p])
        assert result[leader].entry.iloc[i]
        for p in relative.PRODUCTS:
            assert result[p].momentum28.iloc[i] == pytest.approx(ratios[p])
            assert bool(result[p].entry.iloc[i]) == (p == leader)
    declining = {p: frame_for(1000 - np.arange(500) * .5) for p in relative.PRODUCTS}
    assert all(not sig.entry.any() and sig.exit.iloc[60:].all() for sig in relative.signals(declining).values())


def test_exact_ties_fixed_order_independent_of_dictionary_order():
    data = {p: frame_for(100 + np.arange(500)) for p in reversed(relative.PRODUCTS)}
    result = relative.signals(data)
    assert result['BTC-USD'].entry.iloc[60:].all()
    assert not result['ETH-USD'].entry.any() and not result['LTC-USD'].entry.any()


@pytest.mark.parametrize('cut', [28, 59, 60, 200, 320, 499])
def test_all_peer_prefixes_ignore_future_prices(cut):
    data = frames(); prefix = {p:f.iloc[:cut+1].copy() for p,f in data.items()}
    expected = relative.signals(prefix)
    changed = copy.deepcopy(data)
    changed['BTC-USD'].loc[cut+1:, ['Open','High','Low','Close']] *= 1000
    after = relative.signals(changed)
    for p in relative.PRODUCTS: pd.testing.assert_frame_equal(expected[p], after[p].iloc[:cut+1])


def test_only_closed_peer_change_affects_rank_without_changing_own_price():
    data = frames(); before = relative.signals(data)
    data['BTC-USD'].loc[350, 'Close'] = 1000
    after = relative.signals(data)
    assert before['ETH-USD'].entry.iloc[350] and after['ETH-USD'].exit.iloc[350]
    assert after['BTC-USD'].entry.iloc[350]
    pd.testing.assert_frame_equal(before['ETH-USD'].iloc[:350], after['ETH-USD'].iloc[:350])


@pytest.mark.parametrize('problem', ['missing_peer','missing_day','shifted_day','wrong_index','nan','negative'])
def test_missing_or_misaligned_peers_are_never_filled(problem):
    data = frames()
    if problem == 'missing_peer': data.pop('LTC-USD')
    elif problem == 'missing_day': data['LTC-USD'] = data['LTC-USD'].drop(index=250)
    elif problem == 'shifted_day': data['LTC-USD'].Date += pd.Timedelta(days=1)
    elif problem == 'wrong_index': data['LTC-USD'].index += 1
    elif problem == 'nan': data['LTC-USD'].loc[250,'Close'] = np.nan
    else: data['LTC-USD'].loc[250,'Close'] = -1
    with pytest.raises(ValueError): relative.signals(data)


@pytest.mark.parametrize('sizing', relative.SIZINGS)
@pytest.mark.parametrize('lag', [0,1,2])
def test_next_open_delays_cash_conservation_and_terminal_close(sizing, lag):
    data = frames(); frame = data['ETH-USD']; sig = relative.signals(data)['ETH-USD']
    sig['entry'] = False; sig.loc[300,'entry'] = True
    result,audit = simulate(frame, str(frame.Date.iloc[295].date()), str(frame.Date.iloc[340].date()),
        relative.Candidate(relative.FAMILY,sizing), {relative.FAMILY:sig}, {'fee':120,'slippage':25}, lag=lag)
    assert result['fills'][0]['date'] == str(frame.Date.iloc[301+lag].date())
    assert result['fills'][0]['signal_date'] == str(frame.Date.iloc[300].date())
    assert result['fills'][0]['price'] == pytest.approx(frame.Open.iloc[301+lag] * 1.0025)
    assert result['curve'][-1]['asset_quantity'] == 0
    assert audit['max_usd_error'] < 1e-8
    assert result['metrics']['signal_exits'] == 0


def test_training_selection_requires_both_costs_and_cash_fallback():
    good = {'profit_after_operating_usd':100,'max_close_drawdown_pct':10,'closed_trades':10,'annualized_after_operating_pct':2}
    training = {c.id:{cost:dict(good) for cost in ('base','stress')} for c in relative.CANDIDATES}
    assert relative.select(training)['selected'] == min(training)
    for pair in training.values(): pair['stress']['profit_after_operating_usd'] = -1
    assert relative.select(training)['selected'] == 'cash'
    training.pop(relative.CANDIDATES[0].id)
    with pytest.raises(ValueError): relative.select(training)


def test_gate_retains_a_single_failed_delay():
    good = {'profit_after_operating_usd':10,'max_close_drawdown_pct':10,'closed_trades':30}
    name = relative.CANDIDATES[0].id
    matrix = {f'{w}__{c}__{name}':{'metrics':dict(good)} for w in ('full','validation','recent') for c in ('base','stress')}
    delays = {f'lag{l}__{c}__{name}':{'metrics':dict(good)} for l in (1,2) for c in ('base','stress')}
    assert relative.assess(matrix,delays,name)['robust_pass']
    delays[f'lag2__stress__{name}']['metrics']['profit_after_operating_usd'] = -1
    result = relative.assess(matrix,delays,name)
    assert result['historical_pass'] and not result['robust_pass']
    assert result['delay_failed'] == ['lag2_stress_positive']


def test_warmup_zero_momentum_and_exclusive_entry_conditions():
    data = frames(); result = relative.signals(data)
    entries = np.column_stack([s.entry for s in result.values()])
    assert not entries[:60].any() and (entries.sum(axis=1) <= 1).all()
    assert all(not (s.entry & s.exit).any() for s in result.values())
    flat = {p: frame_for(np.full(500,100.)) for p in relative.PRODUCTS}
    assert not any(s.entry.any() for s in relative.signals(flat).values())
