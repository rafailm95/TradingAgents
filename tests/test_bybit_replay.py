"""Synthetic causality, independent accounting, risk guards and selection tests.
No historical strategy returns or network calls in this suite.
"""
import copy
from decimal import Decimal as D, localcontext
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradingagents import bybit_replay as r
from tradingagents.bybit_history import DAY, HOUR, utc_ms

START = utc_ms('2021-01-01T00:00:00Z')
FIRST = START + 200 * DAY


def dataset(days=204, symbol='BTCUSDT'):
    product = {'symbol': symbol, 'contractType': 'LinearPerpetual', 'quoteCoin': 'USDT',
               'settleCoin': 'USDT', 'status': 'Trading', 'fundingInterval': 480,
               'launchTime': str(START - DAY),
               'lotSizeFilter': {'qtyStep': '.1', 'minOrderQty': '.1',
                                 'maxMktOrderQty': '100000', 'minNotionalValue': '5'},
               'priceFilter': {'tickSize': '.01'}}
    times = range(START, START + days * DAY, HOUR)
    trade = [[str(t), '100', '101', '99', '100', '2', '200'] for t in times]
    mark = [x[:5] for x in trade]
    funds = [{'symbol': symbol, 'fundingRateTimestamp': str(t), 'fundingRate': '.0001'}
             for t in range(START - 8 * HOUR, START + days * DAY, 8 * HOUR)]
    return {'instrument': product, 'trade': trade, 'mark': mark,
            'funding': funds[1:], 'funding_anchor': funds[0]}


def signals(market, entry_days=(199,), exit_days=(), max_hold=0, vol=.30):
    index = range(market.start, market.end, DAY)
    return pd.DataFrame({'entry': [i in entry_days for i in range(len(index))],
                         'exit': [i in exit_days for i in range(len(index))],
                         'vol60': vol, 'max_hold': max_hold}, index=index)


def run(data=None, *, entry=(199,), exits=(), max_hold=0, vol=.30, **kwargs):
    market = r.prepare(data or dataset(), 'BTCUSDT')
    sig = signals(market, entry, exits, max_hold, vol)
    return r.replay(market, FIRST, market.end, candidate=r.CANDIDATES[0], prepared_signals=sig, **kwargs)


def test_hand_calculated_constant_price_cash_and_funding_oracle():
    result = run()
    assert result['status'] == 'COMPLETE'
    # Budget <5000 after one hour's opex: 49.9 base at100.02, close99.98.
    assert result['fills'][0]['quantity'] == '49.9'
    assert D(result['metrics']['realized_price_pnl_usdt']) == D('-1.996')
    assert D(result['metrics']['fees_usdt']) == D('5.489')
    # 12 settlements: first00UTC flat, remaining11*49.9*100*.0001.
    assert len(result['funding_events']) == 12
    assert D(result['metrics']['funding_usdt']) == D('-5.489')
    with localcontext() as ctx:
        ctx.prec = 80
        expense = (D(120) * 4 / D('365.25')).quantize(D('1e-18'))
        expected = D(10000) - D('1.996') - D('5.489') - D('5.489') - expense
        assert D(result['metrics']['final_cash_usdt']) == expected
    assert result['independent_wealth_audit']['status'] == 'PASS'
    assert result['fills'][-1]['reason'] == 'scheduled_terminal_close'
    assert result['fills'][-1]['timestamp_ms'] == START + 204 * DAY - 1
    assert result['metrics']['signal_exits'] == 0


@pytest.mark.parametrize('lag', [0, 1, 2])
def test_signal_lag_and_no_future_fill(lag):
    result = run(lag=lag)
    f = result['fills'][0]
    assert f['signal_day_ms'] == START + 199 * DAY
    assert f['timestamp_ms'] == FIRST + lag * DAY + HOUR
    assert all(f['timestamp_ms'] % DAY == HOUR for f in result['fills'] if f['reason'] != 'scheduled_terminal_close')
    assert f['timestamp_ms'] > f['signal_day_ms'] + DAY


def test_funding_uses_actual_position_and_hourly_mark_not_trade_price():
    data = dataset()
    for row in data['mark']:
        row[1:5] = ['120', '121', '119', '120']
    result = run(data, exits=(200,))
    held = [e for e in result['funding_events'] if D(e['quantity_before'])]
    assert len(held) == 3  #08,16, next00 before01 exit
    assert all(D(e['cashflow_usdt']) == -D('49.9') * 120 * D('.0001') for e in held)
    assert result['metrics']['signal_exits'] == 1
    assert result['fills'][1]['timestamp_ms'] == FIRST + DAY + HOUR


def test_adverse_funding_increases_payments_and_reduces_receipts():
    data = dataset()
    for index, f in enumerate(data['funding']):
        if index % 2: f['fundingRate'] = '-.0001'
    base = run(data); stress = run(data, adverse_funding=True)
    for a, b in zip(base['funding_events'], stress['funding_events']):
        assert D(b['cashflow_usdt']) <= D(a['cashflow_usdt'])
    assert D(stress['metrics']['final_cash_usdt']) < D(base['metrics']['final_cash_usdt'])


def test_max_hold_uses_actual_entry_after_signal_lag():
    data = dataset(days=216)
    result = run(data, max_hold=10, lag=2)
    assert result['trades'][0]['reason'] == 'time_exit'
    assert result['trades'][0]['exit_ms'] - result['trades'][0]['entry_ms'] == 10 * DAY


def test_exit_does_not_reenter_same_hour_and_missing_vol_blocks_entry():
    result = run(entry=(199, 201), exits=(200,))
    assert [f['timestamp_ms'] for f in result['fills'][:3]] == [FIRST + HOUR, FIRST + DAY + HOUR, FIRST + 2 * DAY + HOUR]
    blocked = run(vol=np.nan)
    assert not blocked['fills']
    assert blocked['entry_rejections'][0]['reason'] == 'MISSING_SIZING_VOLATILITY'


@pytest.mark.parametrize('field,value', [('maxMktOrderQty','1'), ('minOrderQty','60'), ('minNotionalValue','6000')])
def test_quantity_constraints_reject_without_resizing(field, value):
    data = dataset(); data['instrument']['lotSizeFilter'][field] = value
    result = run(data)
    assert not result['fills'] and len(result['entry_rejections']) == 1
    assert result['metrics']['open_quantity'] == '0'
    assert D(result['metrics']['fees_usdt']) == 0


def test_tick_rounding_is_always_adverse():
    assert r.fill_price(D('100.001'), D(2), D('.1'), True) == D('100.1')
    assert r.fill_price(D('100.001'), D(2), D('.1'), False) == D('99.9')


@pytest.mark.parametrize('problem', ['trade_gap', 'mark_gap', 'funding_gap', 'funding_duplicate', 'anchor', 'symbol', 'nan', 'volume'])
def test_incomplete_or_corrupt_inputs_never_replay(problem):
    data = dataset()
    if problem == 'trade_gap': data['trade'].pop()
    elif problem == 'mark_gap': data['mark'].pop(10)
    elif problem == 'funding_gap': data['funding'].pop(10)
    elif problem == 'funding_duplicate': data['funding'][10] = data['funding'][9]
    elif problem == 'anchor': data['funding_anchor'] = None
    elif problem == 'symbol': data['funding'][0]['symbol'] = 'LTCUSDT'
    elif problem == 'nan': data['mark'][0][1] = 'NaN'
    elif problem == 'volume': data['trade'][0][5] = '-1'
    with pytest.raises(ValueError): r.prepare(data, 'BTCUSDT')


def test_partial_daily_candles_and_wrong_window_rejected():
    m = r.prepare(dataset(), 'BTCUSDT')
    with pytest.raises(ValueError): r.replay(m, FIRST + HOUR, m.end, benchmark='cash')
    with pytest.raises(ValueError): r.replay(m, FIRST - DAY, m.end, benchmark='cash')


def test_cash_and_hold_have_separate_expense_and_no_signal_exit_credit():
    m = r.prepare(dataset(), 'BTCUSDT')
    cash = r.replay(m, FIRST, m.end, benchmark='cash')
    hold = r.replay(m, FIRST, m.end, benchmark='buy_hold50')
    assert D(cash['metrics']['final_cash_usdt']) == 10000
    assert D(cash['metrics']['operating_expense_usdt']) == 0
    assert hold['metrics']['signal_exits'] == 0
    assert hold['fills'][0]['timestamp_ms'] == FIRST + HOUR
    assert D(hold['metrics']['operating_expense_usdt']) > 0


def test_funding_margin_failure_stops_and_preserves_open_position():
    data = dataset(); target = FIRST + 8 * HOUR
    for f in data['funding']:
        if int(f['fundingRateTimestamp']) == target: f['fundingRate'] = '1.1'
    result = run(data)
    assert result['status'] == 'MARGIN_MODEL_UNSUPPORTED'
    assert result['failure']['phase'] == 'after_funding'
    assert result['failure']['timestamp_ms'] == target
    assert len(result['fills']) == 1 and not result['trades']
    assert result['metrics']['annualized_net_return_pct'] is None


def test_intrahour_guard_failure_is_not_erased_by_safe_close():
    data = dataset()
    # Funding leaves a small collateral surplus at the hourly open. A high mark
    # raises the exit-fee reserve above that surplus; the safe closing mark must
    # not erase the unsupported intrahour coverage state.
    for f in data['funding']:
        if int(f['fundingRateTimestamp']) == FIRST + 8 * HOUR: f['fundingRate'] = '.999'
    data['mark'][200 * 24 + 8][1:5] = ['100', '1000', '50', '100']
    result = run(data)
    assert result['status'] == 'MARGIN_MODEL_UNSUPPORTED'
    assert result['failure']['phase'] == 'intrahour_high_unknown_time'
    assert not any(f['reason'] == 'scheduled_terminal_close' for f in result['fills'])


def test_intrahour_excursion_is_separate_from_chronological_drawdown():
    data = dataset()
    for row in data['mark'][200 * 24 + 1:]: row[3] = '50'
    result = run(data)
    assert result['status'] == 'COMPLETE'
    assert D(result['intrahour_excursion']['max_excursion_pct']) > 20
    assert D(result['metrics']['max_drawdown_pct']) < 1
    assert all(D(x['mark']) == 100 for x in result['curve'])


@pytest.mark.parametrize('candidate', r.CANDIDATES)
def test_all_frozen_signals_are_prefix_causal_and_ignore_future_changes(candidate):
    data = dataset(days=260)
    for i, row in enumerate(data['trade']):
        price = 100 + (i // 24) * .05 + 5 * np.sin(i / (24 * 7))
        row[1:5] = list(map(str, [price, price + 2, price - 2, price + .5]))
    m = r.prepare(data, 'BTCUSDT')
    cut = START + 230 * DAY
    full = r.make_signals(m, candidate, m.end)
    prefix = r.make_signals(m, candidate, cut)
    pd.testing.assert_frame_equal(prefix, full.loc[full.index < cut])
    for row in data['trade'][230 * 24:]: row[1:5] = ['1000', '1100', '900', '1050']
    changed = r.make_signals(r.prepare(data, 'BTCUSDT'), candidate, m.end)
    pd.testing.assert_frame_equal(prefix, changed.loc[changed.index < cut])


def test_future_prices_do_not_change_earlier_fills_or_curve():
    original = run(entry=(199, 201), exits=(200,))
    data = dataset()
    for row in data['trade'][202 * 24:]: row[1:5] = ['120', '121', '119', '120']
    changed = run(data, entry=(199, 201), exits=(200,))
    cutoff = FIRST + 2 * DAY
    for key in ('fills', 'curve', 'funding_events'):
        assert [x for x in original[key] if x['timestamp_ms'] < cutoff] == [x for x in changed[key] if x['timestamp_ms'] < cutoff]


def test_independent_oracle_detects_edited_funding_and_equity():
    result = run()
    changed = copy.deepcopy(result)
    next(e for e in changed['events'] if e['kind'] == 'funding')['funding']['cashflow_usdt'] = '1'
    with pytest.raises(ValueError, match='funding mismatch'): r.audit_wealth(changed)
    changed = copy.deepcopy(result); changed['curve'][1]['equity_usdt'] = '999999'
    with pytest.raises(ValueError, match='curve mismatch'): r.audit_wealth(changed)


def fake_result(net='10', exits=20, dd='5', annual=2, status='COMPLETE'):
    return {'status': status, 'metrics': {'net_profit_usdt': net, 'signal_exits': exits,
            'max_drawdown_pct': dd, 'annualized_net_return_pct': annual},
            'independent_wealth_audit': {'status': 'PASS'}}


def test_train_only_selection_tie_cash_fallback_and_all_candidates_required():
    training = {c: {cost: fake_result() for cost in r.COSTS} for c in r.CANDIDATES}
    assert r.select_training(training)['selected'] == min(r.CANDIDATES)
    for pair in training.values(): pair['stress_assumption']['metrics']['net_profit_usdt'] = '-1'
    assert r.select_training(training)['selected'] == 'cash'
    training.pop(r.CANDIDATES[0])
    with pytest.raises(ValueError, match='Incomplete'): r.select_training(training)


def test_gate_retains_single_failed_sensitivity_and_checks_matrix():
    results = [dict(fake_result(), cost=c, lag_days=l, adverse_funding_5bps=a)
               for c in r.COSTS for l in (0, 1, 2) for a in (False, True)]
    assert r.evaluation_gate(results)['historical_screen_pass']
    results[-1]['metrics']['net_profit_usdt'] = '-1'
    gate = r.evaluation_gate(results)
    assert not gate['historical_screen_pass'] and len(gate['failed_scenarios']) == 1
    with pytest.raises(ValueError): r.evaluation_gate(results[:-1])


def test_daily_aggregation_exact_volume_high_low_and_final_close():
    data = dataset()
    data['trade'][3][2] = '120'; data['trade'][10][3] = '80'; data['trade'][23][4] = '100.5'
    frame = r.prepare(data, 'BTCUSDT').frame
    assert frame.iloc[0][['Open', 'High', 'Low', 'Close', 'Volume', 'Turnover']].tolist() == [100, 120, 80, 100.5, 48, 4800]


def test_fixed_sizing_ignores_unused_volatility_and_no_conflicting_signals():
    m = r.prepare(dataset(), 'BTCUSDT'); sig = signals(m, vol=np.nan)
    result = r.replay(m, FIRST, m.end, candidate=r.CANDIDATES[1], prepared_signals=sig)
    assert len(result['fills']) == 2
    sig.loc[START + 199 * DAY, 'exit'] = True
    with pytest.raises(ValueError, match='conflicting'):
        r.replay(m, FIRST, m.end, candidate=r.CANDIDATES[1], prepared_signals=sig)


def test_exit_hour_extremes_after_exit_do_not_affect_closed_position():
    data = dataset()
    data['mark'][201 * 24 + 1][1:5] = ['100', '100000000', '.0001', '100']
    result = run(data, exits=(200,))
    assert result['status'] == 'COMPLETE'
    assert D(result['intrahour_excursion']['max_excursion_pct']) < 1


def test_long_multiyear_decimal_accumulation_reconciles():
    m = r.prepare(dataset(days=2100), 'BTCUSDT')
    result = r.replay(m, FIRST, m.end, benchmark='buy_hold50')
    assert result['status'] == 'COMPLETE'
    assert result['independent_wealth_audit']['max_error_usdt'] in ('0', '0E-18')
    with localcontext() as ctx:
        ctx.prec = 128
        expected = (D(120) * 1900 / D('365.25')).quantize(D('1e-18'))
        assert D(result['metrics']['operating_expense_usdt']) == expected


def test_two_stage_synthetic_all_candidates_assets_and_hash_bound_selection(tmp_path):
    from scripts import run_bybit_replay_013 as runner
    markets = {s: r.prepare(dataset(symbol=s), s) for s in r.SYMBOLS}
    day = lambda n: pd.Timestamp(START + n * DAY, unit='ms', tz='UTC').strftime('%Y-%m-%d')
    design = {'symbols': list(r.SYMBOLS), 'training': [day(200), day(201)], 'evaluation': [day(202), day(203)]}
    train_dir, eval_dir = tmp_path / 'train', tmp_path / 'eval'
    train_dir.mkdir(); eval_dir.mkdir()
    trained = runner.train(markets, design, train_dir, 'a'*64, 'b'*64)
    assert trained['historical_strategy_simulations'] == 36 and not trained['evaluation_computed']
    assert all(s['selected'] == 'cash' for s in trained['selection'].values())
    assert not list(train_dir.glob('eval_*'))
    pin = runner.file_sha(train_dir / 'selection.json')
    checked = runner.verify_selection(train_dir, pin, 'a'*64, 'b'*64, design)
    evaluated = runner.evaluate(markets, design, eval_dir, checked, pin, 'a'*64, 'b'*64)
    assert evaluated['historical_strategy_simulations'] == 216
    assert evaluated['benchmark_simulations'] == 15
    assert len(evaluated['opportunity_comparison']) == 18
    assert all(not row['historical_screen_pass'] for row in evaluated['opportunity_comparison'])
    assert len(list(eval_dir.glob('*.json.gz'))) == 231
    with pytest.raises(ValueError, match='input/freeze'):
        runner.verify_selection(train_dir, pin, 'c'*64, 'b'*64, design)
    artifact = next(train_dir.glob('*.json.gz')); artifact.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        runner.verify_selection(train_dir, pin, 'a'*64, 'b'*64, design)


def test_single_packet_bridge_reuses_frozen_auditor_and_extracts_complete_core(monkeypatch, tmp_path):
    from scripts import run_bybit_replay_013 as runner
    from tests import test_bybit_complete as fixtures
    j, server, clock = fixtures.setup(tmp_path)
    fixtures.b.run(j)
    archive = tmp_path / 'synthetic.zip'; rec = fixtures.finalize(j, archive)
    root = tmp_path / 'repo'; (root / 'docs').mkdir(parents=True)
    (root / 'docs/BYBIT_COMPLETE_014.json').write_bytes(fixtures.raw(j.plan))
    (root / 'docs/BYBIT_HISTORY_013.json').write_bytes(fixtures.raw(j.core))
    actual_audit = runner.audit14.audit
    monkeypatch.setattr(runner.audit14, 'audit', lambda path, digest: actual_audit(path, digest,
                        plan_raw=fixtures.raw(j.plan), core_raw=fixtures.raw(j.core), source_hashes={'test': 'fixture'}))
    monkeypatch.setattr(runner, 'ROOT', root)
    monkeypatch.setattr(runner.collection, 'sources', lambda: {'test': 'fixture'})
    requests_before = len(server.calls)
    receipt, data = runner.load_archive(archive, rec['sha256'])
    assert receipt['replay_core_validation']['status'] == 'COMPLETE'
    assert len(data) == 3 and all(len(d['trade']) == 48 for d in data.values())
    assert len(server.calls) == requests_before
    with pytest.raises(ValueError, match='hash mismatch'): runner.load_archive(archive, '0'*64)


def test_frozen_engine_external_hash_source_and_runtime_required(monkeypatch, tmp_path):
    from scripts import run_bybit_replay_013 as runner
    import importlib.metadata
    file = tmp_path / 'source.py'; file.write_text('synthetic\n')
    manifest = {'source_hashes': {'source.py': runner.file_sha(file)}, 'preserved_files': {},
                'runtime': {'python_major_minor': '3.12', 'packages': {'pandas': importlib.metadata.version('pandas')}}}
    freeze = tmp_path / 'freeze.json'; freeze.write_text(json.dumps(manifest))
    monkeypatch.setattr(runner, 'ROOT', tmp_path); monkeypatch.setattr(runner, 'FREEZE', freeze)
    sha = runner.file_sha(freeze)
    assert runner.verify_engine(sha) == manifest
    with pytest.raises(ValueError, match='freeze hash'): runner.verify_engine('0'*64)
    file.write_text('changed\n')
    with pytest.raises(ValueError, match='Frozen source changed'): runner.verify_engine(sha)
