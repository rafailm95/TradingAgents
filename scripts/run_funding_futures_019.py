"""Bounded funding family and capital-continuous annual WFA; no network/orders."""
import argparse
from decimal import Decimal as D, localcontext
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from tradingagents import futures_replay_019 as engine
from tradingagents import binance_archive as old
from tradingagents.funding_signal_019 import NEW_CANDIDATES
from tradingagents.bybit_history import utc_ms, DAY
from tradingagents.bybit_cashflow import drawdown
from tradingagents.strategy_lab import bootstrap_max_mean
from run_binance_replay_017 import file_sha, write_new, save_result, load_archive

FREEZE = ROOT / 'research/experiments/019/freeze.json'
ARCHIVE_SHA = '676079438cd5b4b1d3bb768368bf9ba02518687461fa98f2c85f4bb671f53236'
INPUT_SHA = 'cccf3ff868465439ede973dd505c95d906c9e6eb9a9c31263c040fd053ccd00e'
T0 = utc_ms('2023-01-01T00:00:00Z')
T1 = utc_ms('2024-01-01T00:00:00Z')
T2 = utc_ms('2025-01-01T00:00:00Z')
T3 = utc_ms('2026-01-01T00:00:00Z')


def verify_freeze(expected):
    if file_sha(FREEZE) != expected:
        raise ValueError('External freeze hash mismatch')
    pin = json.loads(FREEZE.read_bytes())
    for group in ('source_hashes', 'preserved_files'):
        for path, digest in pin[group].items():
            if file_sha(ROOT / path) != digest:
                raise ValueError('Changed frozen file: ' + path)
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Python3.12 required')
    for name, version in pin['runtime'].items():
        if importlib.metadata.version(name) != version:
            raise ValueError('Runtime package mismatch')
    return pin


def compact(r):
    return {k: r[k] for k in ('status', 'metrics', 'independent_wealth_audit')}


def old_result(z, folder, record):
    raw = z.read(folder + '/' + record['file'])
    if hashlib.sha256(raw).hexdigest() != record['sha256']:
        raise ValueError('Preserved017 result hash mismatch')
    r = json.loads(gzip.decompress(raw))
    old.audit_wealth(r)
    if r['metrics'] != record['metrics'] or r['status'] != record['status']:
        raise ValueError('Preserved017 summary mismatch')
    return r


def old_manifest(z, name):
    raw = z.read('binance-017-' + name + '/' + ('selection.json' if name == 'training' else 'evaluation.json'))
    expected = ('5a60dfc9c11d3cb286adea86a62533be2231dbcf314598f9560791b763012895'
                if name == 'training' else '71e492e15aca6cd9086466a31761807636b6a6938acfe705263ee941059fd4dc')
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Preserved017 manifest mismatch')
    return json.loads(raw)


def read_selection(folder, digest, freeze, stage):
    p = Path(folder) / 'selection.json'
    if file_sha(p) != digest:
        raise ValueError('Selection external hash mismatch')
    s = json.loads(p.read_bytes())
    if s['stage'] != stage or s['freeze_sha256'] != freeze or s['input_sha256'] != INPUT_SHA:
        raise ValueError('Selection identity mismatch')
    if s['selection'] != engine.select_training(s['training']):
        raise ValueError('Selection algorithm mismatch')
    for record in s['new_results'].values():
        p = Path(folder) / record['file']
        if file_sha(p) != record['sha256']:
            raise ValueError('Training file integrity mismatch')
        r = json.loads(gzip.decompress(p.read_bytes()))
        engine.audit_wealth(r)
        candidate, cost = r['candidate'], r['cost']
        if compact(r) != s['training'][candidate][cost]:
            raise ValueError('Training result/summary mismatch')
    return s


def train(market, z, folder, freeze, stage, prior=None):
    end = T1 if stage == 'train1' else T2
    training, records, reused = {}, {}, []
    previous = old_manifest(z, 'training')
    for candidate in engine.CANDIDATES:
        training[candidate] = {}
        sig = engine.make_signals(market, candidate, end)
        for cost in engine.COSTS:
            key = candidate + '_' + cost
            if stage == 'train1' and candidate in old.CANDIDATES:
                record = previous['results']['ETHUSDT'][candidate][cost]
                r = old_result(z, 'binance-017-training', record)
                reused.append(record)
            else:
                r = engine.replay(market, T0, end, candidate=candidate, cost=cost, prepared_signals=sig)
                records[key] = save_result(folder, stage + '_' + key, r)
            training[candidate][cost] = compact(r)
        print(stage + ': ' + candidate, flush=True)
    result = {'stage': stage, 'freeze_sha256': freeze, 'input_sha256': INPUT_SHA,
              'training_bounds': [T0, end], 'selection': engine.select_training(training),
              'training': training, 'new_results': records, 'reused017': reused,
              'new_simulations': len(records), 'evaluation_computed': False,
              'prior_selection_sha256': prior}
    write_new(folder / 'selection.json', result)
    return result


def daily_returns(result):
    # The last hour_close at the UTC boundary precedes following-day funding.
    daily = [D(x['equity_usdt']) for x in result['curve']
             if x['phase'] == 'hour_close' and x['timestamp_ms'] % DAY == 0]
    expected = (result['end_exclusive_ms'] - result['start_ms']) // DAY
    if len(daily) != expected or result['status'] != 'COMPLETE':
        raise ValueError('Incomplete daily comparison path')
    values = np.array([float(result['metrics']['initial_usdt'])] + list(map(float, daily)))
    return values[1:] / values[:-1] - 1


def combine_folds(folds):
    if not folds or any(r['status'] != 'COMPLETE' for r in folds):
        return {'status': 'INCOMPLETE', 'passed': False}
    with localcontext() as ctx:
        ctx.prec = 128
        initial = D(folds[0]['metrics']['initial_usdt'])
        if initial != 10000:
            raise ValueError('WFA opening capital mismatch')
        for before, after in zip(folds, folds[1:]):
            if (before['end_exclusive_ms'] != after['start_ms'] or
                D(before['metrics']['final_cash_usdt']) != D(after['metrics']['initial_usdt']) or
                D(before['metrics']['open_quantity']) != 0):
                raise ValueError('Capital/date continuity mismatch')
        net = D(folds[-1]['metrics']['final_cash_usdt']) - initial
        sums = {k: str(sum((D(r['metrics'][k]) for r in folds), D(0)))
                for k in ('fees_usdt', 'funding_usdt', 'operating_expense_usdt', 'realized_price_pnl_usdt')}
        if net != D(sums['realized_price_pnl_usdt']) - D(sums['fees_usdt']) + D(sums['funding_usdt']) - D(sums['operating_expense_usdt']):
            raise ValueError('WFA cashflow reconciliation failed')
        exits = sum(r['metrics']['signal_exits'] for r in folds)
        metrics = {'net_profit_usdt': str(net), 'net_return_pct': str(net / initial * 100),
                   'initial_usdt': str(initial), 'final_cash_usdt': folds[-1]['metrics']['final_cash_usdt'],
                   'signal_exits': exits, **sums,
                   **drawdown([p['equity_usdt'] for r in folds for p in r['curve']], initial=initial)}
        failures = []
        if net <= 0: failures.append('NONPOSITIVE_NET')
        if D(metrics['max_drawdown_pct']) > 35: failures.append('DRAWDOWN_OVER_35PCT')
        if exits < 20: failures.append('FEWER_THAN_20_SIGNAL_EXITS')
        return {'status': 'COMPLETE', 'metrics': metrics, 'failed_gates': failures, 'passed': not failures}


def evaluate(market, z, folder, freeze, s1, s2, selection_hashes):
    comparisons, gates, new_records, curves, audits = {}, {}, {}, {}, []
    prior = old_manifest(z, 'evaluation')
    for candidate in engine.CANDIDATES:
        rows, summaries = [], []
        sig = engine.make_signals(market, candidate, T3)
        for cost in engine.COSTS:
            for lag in (0, 1, 2):
                for adverse in (False, True):
                    if candidate in old.CANDIDATES:
                        name = f'eval_ETHUSDT_{candidate}_{cost}_lag{lag}_adverse{int(adverse)}.json.gz'
                        record = next(x for x in prior['results']['ETHUSDT'][candidate] if x['file'] == name)
                        r = old_result(z, 'binance-017-evaluation', record)
                    else:
                        r = engine.replay(market, T1, T3, candidate=candidate, cost=cost,
                                          lag=lag, adverse_funding=adverse, prepared_signals=sig)
                        record = save_result(folder, f'eval_{candidate}_{cost}_lag{lag}_adverse{int(adverse)}', r)
                        new_records[record['file']] = record
                    audits.append({'file': record['file'], 'new': candidate in NEW_CANDIDATES,
                                   **r['independent_wealth_audit']})
                    rows.append({**record, 'cost': cost, 'lag_days': lag, 'adverse_funding_5bps': adverse})
                    summaries.append({**compact(r), 'cost': cost, 'lag_days': lag, 'adverse_funding_5bps': adverse})
                    if lag == 0 and not adverse:
                        curves[(candidate, cost)] = daily_returns(r)
        comparisons[candidate] = rows
        gates[candidate] = engine.evaluation_gate(summaries)
        print('evaluation: ' + candidate, flush=True)
    benchmarks = {}
    for name, record in prior['benchmarks']['ETHUSDT'].items():
        r = old_result(z, 'binance-017-evaluation', record)
        benchmarks[name] = record
        if not r['adverse_funding_5bps']:
            curves[(r['benchmark'], r['cost'])] = daily_returns(r)
    multiplicity = {}
    for cost in engine.COSTS:
        panel = np.column_stack([curves[(c, cost)] for c in engine.CANDIDATES])
        for benchmark in ('cash', 'buy_hold50'):
            base = np.zeros(len(panel)) if benchmark == 'cash' else curves[(benchmark, cost)]
            diagnostic = bootstrap_max_mean(panel, base, block=30, repeats=2000, seed=20261017)
            diagnostic['operating_costs_included'] = True
            diagnostic['note'] = 'Eight comparable native-perpetual variants; excludes40 spot-only variants and all prior family/design search. Exploratory conditional test, not validation.'
            multiplicity[cost + '_' + benchmark] = diagnostic
    wfa = {}
    for cost in engine.COSTS:
        for lag in (0, 1, 2):
            for adverse in (False, True):
                key = f'{cost}_lag{lag}_adverse{int(adverse)}'
                capital = '10000'
                fold_results, fold_records = [], []
                for year, start, end, selection in ((2024, T1, T2, s1), (2025, T2, T3, s2)):
                    chosen = selection['selection']['selected']
                    kwargs = {'benchmark': 'cash', 'managed_cash': True} if chosen == 'cash' else {'candidate': chosen, 'lag': lag}
                    if chosen != 'cash':
                        kwargs['prepared_signals'] = engine.make_signals(market, chosen, end)
                    r = engine.replay(market, start, end, cost=cost, adverse_funding=adverse,
                                      initial_usdt=capital, **kwargs)
                    record = save_result(folder, f'wfa_{year}_{key}', r)
                    new_records[record['file']] = record
                    fold_results.append(r)
                    fold_records.append({'year': year, 'chosen': chosen, **record})
                    capital = r['metrics']['final_cash_usdt']
                    audits.append({'file': record['file'], 'new': True, **r['independent_wealth_audit']})
                    if r['status'] != 'COMPLETE': break
                wfa[key] = {'folds': fold_records, **combine_folds(fold_results)}
                print('walk-forward: ' + key, flush=True)
    selected = s1['selection']['selected']
    selected_rows = comparisons[selected] if selected != 'cash' else [next(v for k, v in benchmarks.items() if '_cash_' in k)]
    result = {'experiment': '019', 'freeze_sha256': freeze, 'input_sha256': INPUT_SHA,
              'selection_hashes': selection_hashes, 'comparisons_all8': comparisons,
              'gates_all8': gates, 'reused017_benchmarks': benchmarks,
              'main_train_selected': selected, 'main_selected_results': selected_rows,
              'expanding_training_selections': [s1['selection'], s2['selection']],
              'walk_forward': wfa, 'multiplicity': multiplicity, 'audits': audits,
              'new_results': new_records, 'new_simulations_this_stage': len(new_records),
              'classification': 'Exploratory reused Binance history, no prospective evidence, no real orders'}
    write_new(folder / 'evaluation.json', result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--reference-archive', type=Path, required=True)
    p.add_argument('--freeze-sha256', required=True)
    p.add_argument('--stage', choices=['train1', 'train2', 'evaluate'], required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--train1', type=Path); p.add_argument('--selection1-sha256')
    p.add_argument('--train2', type=Path); p.add_argument('--selection2-sha256')
    a = p.parse_args()
    if a.output.exists(): p.error('Output must be new, preserve every attempt')
    verify_freeze(a.freeze_sha256)
    if file_sha(a.reference_archive) != ARCHIVE_SHA:
        raise ValueError('Reference archive external pin failed')
    _, datasets = load_archive(a.input, INPUT_SHA)
    if set(datasets) != {'ETHUSDT'}:
        raise ValueError('Frozen asset mismatch')
    market = old.prepare(datasets['ETHUSDT'], 'ETHUSDT')
    if market.start != old.START or market.end != old.END:
        raise ValueError('Coverage mismatch')
    a.output.mkdir(parents=True)
    write_new(a.output / 'intent.json', vars(a) | {'input': str(a.input), 'reference_archive': str(a.reference_archive),
              'output': str(a.output), 'train1': str(a.train1), 'train2': str(a.train2)})
    try:
        with zipfile.ZipFile(a.reference_archive) as z:
            if a.stage == 'train1':
                train(market, z, a.output, a.freeze_sha256, a.stage)
            else:
                s1 = read_selection(a.train1, a.selection1_sha256, a.freeze_sha256, 'train1')
                if a.stage == 'train2':
                    train(market, z, a.output, a.freeze_sha256, a.stage, a.selection1_sha256)
                else:
                    s2 = read_selection(a.train2, a.selection2_sha256, a.freeze_sha256, 'train2')
                    if s2['prior_selection_sha256'] != a.selection1_sha256:
                        raise ValueError('Training checkpoint chain mismatch')
                    evaluate(market, z, a.output, a.freeze_sha256, s1, s2,
                             [a.selection1_sha256, a.selection2_sha256])
    except Exception as exc:
        write_new(a.output / 'failure.json', {'type': type(exc).__name__, 'message': str(exc)})
        raise


if __name__ == '__main__':
    main()

