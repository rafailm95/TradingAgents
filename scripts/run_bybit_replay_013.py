"""Pinned, offline two-stage013research. Audit a single returned014or013ZIP.

Train and persist selection first. Evaluation requires that manifest's external
SHA256. No live market/order API, credentials, automatic tuning or paid services.
"""
import argparse
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from tradingagents import bybit_replay as engine
from tradingagents.bybit_history import assemble, utc_ms, DAY
import audit_bybit_complete as audit14
import audit_bybit_history as audit13
import bybit_complete as collection

FREEZE = ROOT / 'research/experiments/013/engine-freeze-v1.json'
DESIGN = ROOT / 'docs/BYBIT_PERPETUAL_REPLAY_013.json'


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1_000_000), b''): digest.update(part)
    return digest.hexdigest()


def write_new(path, data):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def verify_engine(expected):
    if not re.fullmatch('[0-9a-f]{64}', expected) or file_sha(FREEZE) != expected:
        raise ValueError('External engine freeze hash mismatch')
    pin = json.loads(FREEZE.read_bytes())
    for name, digest in pin['source_hashes'].items():
        if file_sha(ROOT / name) != digest: raise ValueError('Frozen source changed: ' + name)
    for name, digest in pin['preserved_files'].items():
        if file_sha(ROOT / name) != digest: raise ValueError('Preserved contract changed: ' + name)
    if '.'.join(map(str, sys.version_info[:2])) != pin['runtime']['python_major_minor']:
        raise ValueError('Python runtime differs from engine freeze')
    for name, version in pin['runtime']['packages'].items():
        if importlib.metadata.version(name) != version:
            raise ValueError('Dependency runtime differs: ' + name)
    return pin


def load_archive(path, expected_sha):
    """Original collectors/auditors unchanged. Only complete013core is replayable.
    Supplements may be incomplete and still remain in the comprehensive receipt.
    """
    path = Path(path)
    if path.stat().st_size > 600_000_000 or not re.fullmatch('[0-9a-f]{64}', expected_sha) or file_sha(path) != expected_sha:
        raise ValueError('Input archive hash mismatch or oversized')
    with zipfile.ZipFile(path) as z:
        unified = 'core_protocol.json' in z.namelist()
    if not unified:
        receipt, datasets = audit13.audit(path, expected_sha)
        if receipt['validation']['status'] != 'COMPLETE':
            raise ValueError('Incomplete013history; no strategy calculation allowed')
    else:
        receipt = audit14.audit(path, expected_sha)
        # Reopen only the already bounded/audited flat files, never execute ZIP code.
        with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory(prefix='bybit-replay-input-') as tmp:
            folder = Path(tmp)
            for info in z.infolist():
                if info.filename in ('session.json', 'plan.json', 'core_protocol.json') or re.fullmatch(
                        r'(request_[0-9]{6}\.json|response_[0-9]{6}\.bin)', info.filename):
                    (folder / info.filename).write_bytes(z.read(info.filename))
            journal = collection.Journal(folder, (ROOT / 'docs/BYBIT_COMPLETE_014.json').read_bytes(),
                         (ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes(), collection.sources(), offline=True)
            validation, datasets = assemble(journal.core, journal.get)
            if validation['status'] != 'COMPLETE':
                raise ValueError('Incomplete014core; no strategy calculation allowed')
            receipt['replay_core_validation'] = validation
    if file_sha(path) != expected_sha:
        raise ValueError('Input archive changed during audit')
    return receipt, datasets


def save_result(folder, name, result):
    path = folder / (name + '.json.gz')
    # Exclusive write + deterministic gzip; no overwrite/resume of accepted results.
    with path.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as z:
            z.write(json.dumps(result, separators=(',', ':'), allow_nan=False).encode())
    return {'file': path.name, 'sha256': file_sha(path), 'status': result['status'],
            'metrics': result['metrics']}


def read_result(folder, record):
    name = record['file']
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.json\.gz', name): raise ValueError('Unsafe result path')
    path = folder / name
    if path.stat().st_size > 100_000_000 or file_sha(path) != record['sha256']:
        raise ValueError('Training result hash mismatch')
    with gzip.open(path, 'rb') as f:
        raw = f.read(300_000_001)
    if len(raw) > 300_000_000: raise ValueError('Oversized result')
    return json.loads(raw)


def bounds(design, name):
    start, final = design[name]
    return utc_ms(start + 'T00:00:00Z'), utc_ms(final + 'T00:00:00Z') + DAY


def train(markets, design, folder, input_sha, freeze_sha):
    start, end = bounds(design, 'training')
    records, selections = {}, {}
    for symbol, market in markets.items():
        training, records[symbol] = {}, {}
        for candidate in engine.CANDIDATES:
            sig = engine.make_signals(market, candidate, end)
            training[candidate], records[symbol][candidate] = {}, {}
            for cost in engine.COSTS:
                result = engine.replay(market, start, end, candidate=candidate, cost=cost, prepared_signals=sig)
                name = f'train_{symbol}_{candidate}_{cost}'
                records[symbol][candidate][cost] = save_result(folder, name, result)
                # Selection consumes compact train-only summaries, not evaluation results.
                training[candidate][cost] = {k: result[k] for k in ('status', 'metrics', 'independent_wealth_audit')}
            print('Training complete: ' + symbol + ' ' + candidate, flush=True)
        selections[symbol] = engine.select_training(training)
    manifest = {'schema': 'bybit013_training_manifest_v1', 'input_sha256': input_sha,
                'engine_freeze_sha256': freeze_sha, 'training_bounds': [start, end],
                'selection': selections, 'results': records,
                'historical_strategy_simulations': len(markets) * len(engine.CANDIDATES) * len(engine.COSTS),
                'evaluation_computed': False, 'real_orders': 0}
    write_new(folder / 'selection.json', manifest)
    return manifest


def verify_selection(folder, expected_sha, input_sha, freeze_sha, design):
    path = folder / 'selection.json'
    if not re.fullmatch('[0-9a-f]{64}', expected_sha) or file_sha(path) != expected_sha:
        raise ValueError('External training selection hash mismatch')
    manifest = json.loads(path.read_bytes())
    if (manifest['schema'] != 'bybit013_training_manifest_v1' or manifest['input_sha256'] != input_sha
            or manifest['engine_freeze_sha256'] != freeze_sha or manifest['evaluation_computed'] is not False
            or manifest['training_bounds'] != list(bounds(design, 'training'))
            or set(manifest['results']) != set(design['symbols'])
            or set(manifest['selection']) != set(design['symbols'])):
        raise ValueError('Training/input/freeze identity mismatch')
    for symbol, records in manifest['results'].items():
        data = {}
        for candidate, pair in records.items():
            data[candidate] = {}
            for cost, record in pair.items():
                result = read_result(folder, record)
                if (result['symbol'] != symbol or result['candidate'] != candidate or result['cost'] != cost
                        or result['lag_days'] != 0 or result['adverse_funding_5bps'] is not False
                        or [result['start_ms'], result['end_exclusive_ms']] != manifest['training_bounds']):
                    raise ValueError('Wrong training scenario')
                engine.audit_wealth(result)
                if result['metrics'] != record['metrics'] or result['status'] != record['status']:
                    raise ValueError('Training summary mismatch')
                data[candidate][cost] = {k: result[k] for k in ('status', 'metrics', 'independent_wealth_audit')}
        if engine.select_training(data) != manifest['selection'][symbol]:
            raise ValueError('Train-only selection mismatch')
    return manifest


def evaluate(markets, design, folder, selection, selection_sha, input_sha, freeze_sha):
    start, end = bounds(design, 'evaluation')
    records, gates, benchmarks, opportunities = {}, {}, {}, []
    for symbol, market in markets.items():
        records[symbol], gates[symbol], benchmarks[symbol] = {}, {}, {}
        for candidate in engine.CANDIDATES:
            sig = engine.make_signals(market, candidate, end)
            summaries, records[symbol][candidate] = [], []
            for cost in engine.COSTS:
                for lag in (0, 1, 2):
                    for adverse in (False, True):
                        result = engine.replay(market, start, end, candidate=candidate, cost=cost,
                            lag=lag, adverse_funding=adverse, prepared_signals=sig)
                        name = f'eval_{symbol}_{candidate}_{cost}_lag{lag}_adverse{int(adverse)}'
                        records[symbol][candidate].append(save_result(folder, name, result))
                        summaries.append({k: result[k] for k in ('status', 'metrics', 'cost', 'lag_days',
                                                               'adverse_funding_5bps', 'independent_wealth_audit')})
            gate = engine.evaluation_gate(summaries); gates[symbol][candidate] = gate
            all_complete = all(r['status'] == 'COMPLETE' for r in summaries)
            worst = min(summaries, key=lambda r: engine.D(r['metrics']['net_return_pct'])) if all_complete else None
            opportunities.append({'symbol': symbol, 'candidate': candidate,
                'historical_screen_pass': gate['historical_screen_pass'],
                'all_scenarios_complete': all_complete,
                'worst_net_return_pct': worst['metrics']['net_return_pct'] if worst else None,
                'worst_net_profit_usdt': worst['metrics']['net_profit_usdt'] if worst else None,
                'nominal_lag0': summaries[0]['metrics'], 'failed_scenarios': gate['failed_scenarios'],
                'selected_by_training': selection['selection'][symbol]['selected'] == candidate})
            print('Evaluation complete: ' + symbol + ' ' + candidate, flush=True)
        scenarios = [('cash', 'venue_assumption', False)] + [('buy_hold50', c, a) for c in engine.COSTS for a in (False, True)]
        for benchmark, cost, adverse in scenarios:
            name = f'benchmark_{symbol}_{benchmark}_{cost}_adverse{int(adverse)}'
            result = engine.replay(market, start, end, benchmark=benchmark, cost=cost, adverse_funding=adverse)
            benchmarks[symbol][name] = save_result(folder, name, result)
    opportunities.sort(key=lambda r: (not r['all_scenarios_complete'],
        -float(r['worst_net_return_pct']) if r['all_scenarios_complete'] else 0, r['symbol'], r['candidate']))
    manifest = {'schema': 'bybit013_evaluation_manifest_v1', 'input_sha256': input_sha,
                'engine_freeze_sha256': freeze_sha, 'selection_sha256': selection_sha,
                'frozen_train_selection': selection['selection'], 'evaluation_bounds': [start, end],
                'results': records, 'gates': gates, 'benchmarks': benchmarks,
                'opportunity_comparison': opportunities,
                'opportunity_ranking_classification': 'Post-hoc descriptive ranking; no change to training selection or forward cohorts.',
                'historical_strategy_simulations': len(markets) * len(engine.CANDIDATES) * len(engine.COSTS) * 3 * 2,
                'benchmark_simulations': len(markets) * 5,
                'independent_10000usdt_accounts': True, 'real_orders': 0}
    write_new(folder / 'evaluation.json', manifest)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True); p.add_argument('--sha256', required=True)
    p.add_argument('--engine-freeze-sha256', required=True)
    p.add_argument('--stage', choices=['train', 'evaluate'], required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--training-directory', type=Path); p.add_argument('--selection-sha256')
    a = p.parse_args()
    if a.output.exists(): p.error('Output directory must be new; no overwrite of accepted/partial evidence')
    if a.stage == 'evaluate' and (not a.training_directory or not a.selection_sha256):
        p.error('Evaluation requires existing training selection and its external SHA256')
    verify_engine(a.engine_freeze_sha256)
    design = json.loads(DESIGN.read_bytes())
    a.output.mkdir(parents=True)
    write_new(a.output / 'intent.json', {'stage': a.stage, 'input_sha256': a.sha256,
              'engine_freeze_sha256': a.engine_freeze_sha256, 'real_orders': 0})
    try:
        receipt, datasets = load_archive(a.input, a.sha256)
        write_new(a.output / 'input-audit.json', receipt)
        markets = {s: engine.prepare(datasets[s], s) for s in design['symbols']}
        # Require the entire originally frozen historical interval, never silently shorten it.
        core = json.loads((ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes())
        if any(m.start != utc_ms(core['start_utc']) or m.end != utc_ms(core['end_exclusive_utc']) for m in markets.values()):
            raise ValueError('Full frozen history interval is required')
        if a.stage == 'train':
            train(markets, design, a.output, a.sha256, a.engine_freeze_sha256)
            target = a.output / 'selection.json'
        else:
            selected = verify_selection(a.training_directory, a.selection_sha256, a.sha256,
                                        a.engine_freeze_sha256, design)
            evaluate(markets, design, a.output, selected, a.selection_sha256, a.sha256, a.engine_freeze_sha256)
            target = a.output / 'evaluation.json'
        print(json.dumps({'status': 'COMPLETE', 'manifest': str(target), 'sha256': file_sha(target)}))
    except Exception as e:
        write_new(a.output / 'stopped.json', {'status': 'STOPPED_REVIEW_REQUIRED',
                  'error': type(e).__name__ + ': ' + str(e), 'partial_results_preserved': True})
        raise


if __name__ == '__main__':
    main()
