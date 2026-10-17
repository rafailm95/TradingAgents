"""Synthetic-only 018 tests; no archived outcome inspection."""
import copy
from decimal import Decimal as D
import pytest
from tradingagents.futures_concentration import (
    contribution_diagnostics, audit_trade_components, calendar_diagnostics,
    month_boundary, number, sampled_drawdown,
)


def test_hand_calculated_static_attribution_and_full_expense():
    r = contribution_diagnostics(['300', '-100', '200'], '40', '10000')
    assert r['net']['usdt'] == '360'
    assert r['net']['pct_initial'] == '3.600'
    assert r['without_best_positive_trade']['usdt'] == '60'
    assert r['without_two_best_positive_trades']['usdt'] == '-140'
    assert r['single_trade_removals'][1]['usdt'] == '460'
    assert r['largest_share_of_gross_positive_pct'] == '60.0'
    assert r['profit_factor_before_operating'] == '5'


@pytest.mark.parametrize('values', [[], ['-1'], ['0'], ['-3', '-4']])
def test_no_positive_contribution_never_removes_a_loss(values):
    r = contribution_diagnostics(values, '10', '10000')
    assert r['net'] == r['without_best_positive_trade'] == r['without_two_best_positive_trades']
    assert r['inverse_winner_concentration'] is None
    assert r['largest_share_of_gross_positive_pct'] is None


def test_single_winner_and_tied_winners():
    single = contribution_diagnostics(['100'], '5', '10000')
    assert single['without_best_positive_trade']['usdt'] == '-5'
    assert single['inverse_winner_concentration'] == '1'
    equal = contribution_diagnostics(['100', '100'], '5', '10000')
    assert equal['inverse_winner_concentration'] == '2'
    assert equal['without_two_best_positive_trades']['usdt'] == '-5'


def test_no_input_mutation_and_scale_invariance():
    values = ['300', '-100', '200']
    original = list(values)
    a = contribution_diagnostics(values, '40', '10000')
    b = contribution_diagnostics(['600', '-200', '400'], '80', '20000')
    assert values == original
    assert D(a['net']['pct_initial']) == D(b['net']['pct_initial'])
    assert a['inverse_winner_concentration'] == b['inverse_winner_concentration']


@pytest.mark.parametrize('bad', ['NaN', 'Infinity', '-Infinity', 1.0, True])
def test_invalid_numbers_refused(bad):
    with pytest.raises(ValueError):
        number(bad)


@pytest.mark.parametrize('expense,initial', [('-1', '10000'), ('0', '0'), ('1', '-100')])
def test_invalid_budget_refused(expense, initial):
    with pytest.raises(ValueError):
        contribution_diagnostics(['1'], expense, initial)


def trade_fixture():
    return {
        'status': 'COMPLETE', 'start_ms': 0, 'end_exclusive_ms': 100,
        'fills': [
            {'timestamp_ms': 10, 'side': 'buy', 'quantity': '2', 'price': '100', 'fee_usdt': '1', 'reason': 'entry'},
            {'timestamp_ms': 30, 'side': 'sell', 'quantity': '2', 'price': '110', 'fee_usdt': '1', 'reason': 'signal_exit'},
            {'timestamp_ms': 50, 'side': 'buy', 'quantity': '1', 'price': '100', 'fee_usdt': '1', 'reason': 'entry'},
            {'timestamp_ms': 90, 'side': 'sell', 'quantity': '1', 'price': '90', 'fee_usdt': '1', 'reason': 'scheduled_terminal_close'},
        ],
        'funding_events': [
            {'timestamp_ms': 0, 'quantity_before': '0', 'cashflow_usdt': '0'},
            {'timestamp_ms': 20, 'quantity_before': '2', 'cashflow_usdt': '-3'},
            {'timestamp_ms': 40, 'quantity_before': '0', 'cashflow_usdt': '0'},
            {'timestamp_ms': 60, 'quantity_before': '1', 'cashflow_usdt': '2'},
        ],
        'trades': [
            {'entry_ms': 10, 'exit_ms': 30, 'reason': 'signal_exit', 'price_pnl_usdt': '20', 'fees_usdt': '2', 'funding_usdt': '-3', 'net_before_operating_usdt': '15'},
            {'entry_ms': 50, 'exit_ms': 90, 'reason': 'scheduled_terminal_close', 'price_pnl_usdt': '-10', 'fees_usdt': '2', 'funding_usdt': '2', 'net_before_operating_usdt': '-10'},
        ],
        'metrics': {'open_quantity': '0', 'realized_price_pnl_usdt': '10', 'fees_usdt': '4', 'funding_usdt': '-1',
                    'operating_expense_usdt': '4', 'net_profit_usdt': '1', 'closed_trades': 2, 'signal_exits': 1},
    }


def test_independent_fill_and_funding_reconstruction_with_terminal_trade():
    result = trade_fixture()
    untouched = copy.deepcopy(result)
    rows = audit_trade_components(result)
    assert [r['net_before_operating_usdt'] for r in rows] == ['15', '-10']
    assert [r['funding_events'] for r in rows] == [1, 1]
    assert result == untouched


@pytest.mark.parametrize('mutation', ['fee', 'quantity', 'side', 'funding', 'duplicate_funding', 'orphan_funding',
                                       'same_time_funding', 'trade_time', 'net', 'signal_count', 'partial', 'open'])
def test_corruption_stops_attribution(mutation):
    r = trade_fixture()
    if mutation == 'fee': r['fills'][0]['fee_usdt'] = '2'
    if mutation == 'quantity': r['fills'][1]['quantity'] = '3'
    if mutation == 'side': r['fills'][0]['side'] = 'sell'
    if mutation == 'funding': r['funding_events'][1]['cashflow_usdt'] = '-4'
    if mutation == 'duplicate_funding': r['funding_events'].insert(1, copy.deepcopy(r['funding_events'][0]))
    if mutation == 'orphan_funding': r['funding_events'][0]['cashflow_usdt'] = '1'
    if mutation == 'same_time_funding': r['funding_events'][1]['timestamp_ms'] = 10
    if mutation == 'trade_time': r['trades'][0]['entry_ms'] = 11
    if mutation == 'net': r['metrics']['net_profit_usdt'] = '2'
    if mutation == 'signal_count': r['metrics']['signal_exits'] = 2
    if mutation == 'partial': r['status'] = 'STOPPED'
    if mutation == 'open': r['metrics']['open_quantity'] = '1'
    with pytest.raises(ValueError): audit_trade_components(r)


def calendar_fixture():
    curve = [{'timestamp_ms': month_boundary(2024, 1), 'phase': 'before_funding', 'equity_usdt': '10000'}]
    for i in range(1, 25):
        year, month = 2024 + i // 12, i % 12 + 1
        curve.append({'timestamp_ms': month_boundary(year, month), 'phase': 'hour_close', 'equity_usdt': str(10000 + 100 * i)})
        if i == 12:
            curve.append({'timestamp_ms': month_boundary(year, month), 'phase': 'after_funding', 'equity_usdt': '8500'})
    return curve


def test_calendar_boundaries_use_hour_close_before_next_year_funding():
    r = calendar_diagnostics(calendar_fixture(), '10000', month_boundary(2024, 1), month_boundary(2026, 1))
    assert len(r['months']) == 24 and len(r['years']) == 2
    assert r['years'][0]['pnl_usdt'] == '1200'
    assert r['years'][1]['pnl_usdt'] == '1200'
    assert D(r['years'][0]['sampled_drawdown']['pct']) == 0
    assert D(r['years'][1]['sampled_drawdown']['cash_at_max_pct_usdt']) == 2700
    assert r['without_best_positive_month']['usdt'] == '2300'


@pytest.mark.parametrize('mutation', ['missing_boundary', 'duplicate_close', 'unordered', 'wrong_initial', 'wrong_end'])
def test_invalid_calendar_curve_refused(mutation):
    c = calendar_fixture()
    if mutation == 'missing_boundary': c.pop(2)
    if mutation == 'duplicate_close': c.insert(2, copy.deepcopy(c[1]))
    if mutation == 'unordered': c[1], c[2] = c[2], c[1]
    if mutation == 'wrong_initial': c[0]['equity_usdt'] = '9999'
    if mutation == 'wrong_end': c[-1]['timestamp_ms'] += 1
    with pytest.raises(ValueError):
        calendar_diagnostics(c, '10000', month_boundary(2024, 1), month_boundary(2026, 1))


def test_drawdown_cash_is_measured_from_actual_peak():
    r = sampled_drawdown(['10000', '15000', '12000'])
    assert D(r['pct']) == 20
    assert D(r['cash_at_max_pct_usdt']) == 3000
    assert D(r['cash_at_max_pct_usdt']) != D(r['pct']) * 100
