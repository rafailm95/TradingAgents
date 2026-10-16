"""Frozen015spot batch: two new variants, all three assets,174new simulations.
Reuses authenticated011reference results without rerunning their42strategies.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tradingagents import relative_strength as new, strategy_lab as legacy
from tradingagents.strategy_backtest import load_daily
from tradingagents.opportunity_discovery import rank_asset, drawdown
from scripts.run_weekly_confirmation_lab import simulate, returns

FREEZE = ROOT / 'research/experiments/015/freeze.json'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as f: json.dump(value, f, indent=2, allow_nan=False)


def compressed(path, value):
    with path.open('xb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as z:
        z.write(json.dumps(value, separators=(',', ':'), allow_nan=False).encode())


def verify(freeze_sha, reference_root):
    if sha(FREEZE) != freeze_sha: raise ValueError('External freeze hash mismatch')
    freeze = json.loads(FREEZE.read_bytes())
    for name, digest in freeze['source_hashes'].items():
        if sha(ROOT / name) != digest: raise ValueError('Source changed: ' + name)
    for name, digest in freeze['preserved_files'].items():
        if sha(ROOT / name) != digest: raise ValueError('Preserved source changed: ' + name)
    for product, item in freeze['inputs'].items():
        if sha(ROOT / item['path']) != item['sha256']: raise ValueError('Input changed: ' + product)
    for path, digest in freeze['reference_results'].items():
        if sha(reference_root / path) != digest: raise ValueError('Reference changed: ' + path)
    if '.'.join(map(str, sys.version_info[:2])) != freeze['runtime']['python_major_minor']:
        raise ValueError('Python runtime mismatch')
    for package, version in freeze['runtime']['packages'].items():
        if importlib.metadata.version(package) != version: raise ValueError('Package mismatch: ' + package)
    return freeze


def evaluate_asset(product, frame, features, common, output, reference_root):
    output.mkdir()
    matrix, delays, training, audits = {}, {}, {}, []
    for window in common['windows']:
        for cost in common['costs']:
            for candidate in new.CANDIDATES:
                result, audit = simulate(frame, window['start'], window['end'], candidate, features, cost)
                key = f"{window['name']}__{cost['name']}__{candidate.id}"
                result['product'] = product; matrix[key] = result; audits.append({'id': key, **audit})
                if window['name'] == 'train': training.setdefault(candidate.id, {})[cost['name']] = result['metrics']
        if window['name'] == 'train':
            selected = new.select(training)
            write(output / 'selection_before_evaluation.json', selected)
        print('Completed ' + product + ' ' + window['name'], flush=True)
    for lag in (1, 2):
        for cost in common['costs']:
            for candidate in new.CANDIDATES:
                result, audit = simulate(frame, '2024-01-01', common['data_end'], candidate, features, cost, lag=lag)
                key = f"lag{lag}__{cost['name']}__{candidate.id}"
                result['product'] = product; delays[key] = result; audits.append({'id': key, **audit})
    assessments = [new.assess(matrix, delays, c.id) for c in new.CANDIDATES]
    rows = [new.opportunity_row(product, c.id, matrix, delays, a, selected) for c,a in zip(new.CANDIDATES, assessments)]
    # Authenticated old artifacts, no old strategy recalculation.
    old_matrix = json.loads(gzip.decompress((reference_root / product / 'matrix.json.gz').read_bytes()))
    old_delays = json.loads(gzip.decompress((reference_root / product / 'delays.json.gz').read_bytes()))
    old_assessment = json.loads((ROOT / 'research/experiments/011' / product / 'assessment.json').read_bytes())
    old_rows = rank_asset(product, old_matrix, old_delays, old_assessment)['rows']
    comparison = new.compare(old_rows, rows)
    names = sorted({r['id'] for r in comparison})
    panel = np.column_stack([returns((matrix if name in {c.id for c in new.CANDIDATES} else old_matrix)[f'evaluation__base__{name}']) for name in names])
    reference_dates = [p['Date'] for p in old_matrix['evaluation__base__cash']['curve']]
    for result in [matrix[f'evaluation__base__{c.id}'] for c in new.CANDIDATES]:
        if [p['Date'] for p in result['curve']] != reference_dates: raise ValueError('Bootstrap date mismatch')
    multiplicity = [{'benchmark': benchmark, 'candidate_count': 44,
        **legacy.bootstrap_max_mean(panel, returns(old_matrix[f'evaluation__base__{benchmark}']), block=block)}
        for benchmark in ('cash', 'buy_hold50') for block in (30, 60)]
    del old_matrix, old_delays
    wf_training, folds = {}, []
    balances = {'base': 10000., 'stress': 10000.}; joined = {'base': [], 'stress': []}
    for year in range(2022, 2027):
        candidates = {}
        for candidate in new.CANDIDATES:
            candidates[candidate.id] = {}
            for cost in common['costs']:
                result, audit = simulate(frame, '2020-01-01', f'{year-1}-12-31', candidate, features, cost)
                key = f"train{year}__{cost['name']}__{candidate.id}"
                wf_training[key] = result; candidates[candidate.id][cost['name']] = result['metrics']
                audits.append({'id': key, **audit})
        selection = new.select(candidates)
        item = next((c for c in new.CANDIDATES if c.id == selection['selected']), 'cash')
        write(output / f'wf_selection_{year}.json', selection)  # persisted before that fold
        end = f'{year}-12-31' if year < 2026 else common['data_end']
        fold = {'year': year, 'selection': selection, 'results': {}}
        for cost in common['costs']:
            name = cost['name']
            result, audit = simulate(frame, f'{year}-01-01', end, item, features, cost,
                                     initial=balances[name], operating=120)
            balances[name] = result['metrics']['final_usd'] - result['metrics']['operating_cost_usd']
            if balances[name] <= 0: raise ArithmeticError('Insolvent WFA book')
            net = [dict(point) for point in result['curve']]
            net[-1]['equity'] = net[-1]['cash'] = balances[name]
            joined[name].extend(net)
            result['operating_debit'] = {'date': end, 'amount_usd': result['metrics']['operating_cost_usd'], 'cash_after': balances[name]}
            fold['results'][name] = result; audits.append({'id': f'wf{year}_{name}', **audit})
        folds.append(fold)
    wf_summary = {name: {'final_after_operating_usd': balances[name], 'net_profit_usd': balances[name] - 10000,
        'net_return_pct': (balances[name] / 10000 - 1) * 100,
        **drawdown([p['equity'] for p in joined[name]], 10000)} for name in balances}
    summary = {'product': product, 'selection': selected, 'assessments': assessments,
        'new_opportunities': rows, 'comparison44': [{k:v for k,v in row.items() if k != 'scenarios'} for row in comparison],
        'multiplicity': multiplicity, 'walk_forward_summary': wf_summary,
        'walk_forward_choices': [{'year': f['year'], 'selected': f['selection']['selected']} for f in folds],
        'metrics': {k:v['metrics'] for k,v in matrix.items()}, 'delay_metrics': {k:v['metrics'] for k,v in delays.items()},
        'simulation_count': len(matrix) + len(delays) + len(wf_training) + 2 * len(folds),
        'audit_cases': len(audits), 'audit_days': sum(a['days'] for a in audits),
        'max_wealth_error_usd': max(a['max_usd_error'] for a in audits)}
    if summary['simulation_count'] != 58 or summary['audit_cases'] != 58: raise ValueError('Incomplete batch')
    write(output / 'assessment.json', summary); write(output / 'audits.json', audits)
    for name, content in [('matrix', matrix), ('delays', delays), ('wf_training', wf_training), ('walk_forward', folds)]:
        compressed(output / (name + '.json.gz'), content)
    print('Completed ' + product + ':58runs', flush=True)
    return summary


def run(output, reference_root, freeze_sha):
    frozen = verify(freeze_sha, reference_root)
    common = json.loads((ROOT / 'docs/CROSS_ASSET_PROTOCOL.json').read_bytes())
    frames = {product: load_daily(ROOT / item['path']) for product,item in frozen['inputs'].items()}
    for frame in frames.values():
        if len(frame) != 2845 or str(frame.Date.iloc[0].date()) != '2019-01-01' or str(frame.Date.iloc[-1].date()) != '2026-10-15':
            raise ValueError('Frozen input coverage mismatch')
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'run_manifest.json', {'started_utc': datetime.now(timezone.utc).isoformat(), 'freeze_sha256': freeze_sha,
        'inputs': frozen['inputs'], 'reference_result_hashes': frozen['reference_results'], 'orders': 0})
    try:
        features = new.signals(frames)
        results = {product: evaluate_asset(product, frames[product],
            {new.FAMILY: features[product], 'breakout20': features[product]}, common, output / product, reference_root)
            for product in new.PRODUCTS}
        result = {'experiment': 'relative_strength_015_v1', 'completed_utc': datetime.now(timezone.utc).isoformat(),
            'freeze_sha256': freeze_sha, 'new_families': 1, 'new_variants': 2, 'historical_simulations': 174,
            'cumulative_historical_simulations': 7164, 'cumulative_unique_variants': 44, 'cumulative_families': 22,
            'historical_scope': 'Reused correlated Coinbase USD spot dates; exploratory, not Bybit/future performance.',
            'assets': {p: {k:v for k,v in s.items() if k not in ('metrics', 'delay_metrics', 'comparison44')} for p,s in results.items()},
            'cross_asset_robust_passes': [c.id for c in new.CANDIDATES if all(next(a for a in s['assessments'] if a['id'] == c.id)['robust_pass'] for s in results.values())],
            'audit_cases': sum(s['audit_cases'] for s in results.values()), 'audit_days': sum(s['audit_days'] for s in results.values()),
            'max_wealth_error_usd': max(s['max_wealth_error_usd'] for s in results.values()), 'real_orders': 0}
        write(output / 'summary.json', result)
        hashes = {str(path.relative_to(output)): sha(path) for path in sorted(output.rglob('*')) if path.is_file()}
        write(output / 'full_result_hashes.json', hashes)
        print(json.dumps({'status': 'COMPLETE', 'new_runs': 174, 'cross_asset_robust_passes': result['cross_asset_robust_passes']}), flush=True)
        return result
    except Exception as error:
        write(output / 'stopped.json', {'error': type(error).__name__ + ': ' + str(error), 'partial_results_preserved': True})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--reference-root', type=Path, required=True)
    parser.add_argument('--freeze-sha', required=True)
    args = parser.parse_args(); run(args.output, args.reference_root, args.freeze_sha)
