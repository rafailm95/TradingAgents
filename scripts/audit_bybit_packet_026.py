"""Offline integrity and semantic audit of a returned unified Bybit evidence ZIP."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tradingagents'))
import bybit_packet_026 as b


def comparable(value):
    if isinstance(value, dict): return {k: comparable(v) for k, v in value.items() if k != 'error'}
    if isinstance(value, list): return [comparable(v) for v in value]
    return value


def audit(path, expected_sha, *, plan_raw=None, core_raw=None, source_hashes=None, return_core=False):
    path = Path(path)
    if path.stat().st_size > 480_000_000 or b.file_sha(path) != expected_sha: raise ValueError('Archive size/hash mismatch')
    plan_raw = plan_raw or (ROOT / 'docs/BYBIT_PACKET_026.json').read_bytes()
    core_raw = core_raw or (ROOT / 'docs/BYBIT_HISTORY_013.json').read_bytes()
    source_hashes = b.sources() if source_hashes is None else source_hashes
    with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory(prefix='bybit-complete-audit-') as tmp:
        infos = z.infolist(); names = [i.filename for i in infos]
        allowed = {'session.json', 'plan.json', 'core_protocol.json', 'state.json', 'summary.json',
                   'STATUS_EL.txt', 'FILES.json', 'import_013_session.json', 'operator_settings.json'}
        if (len(infos) > 80020 or len(set(names)) != len(names) or sum(i.file_size for i in infos) > 1_480_000_000
                or any(i.is_dir() or i.flag_bits & 1 or i.file_size > 20_000_000 for i in infos)
                or any(n not in allowed and not re.fullmatch(r'(request_[0-9]{6}\.json|response_[0-9]{6}\.bin\.gz)', n) for n in names)):
            raise ValueError('Unsafe, duplicate or oversized archive')
        manifest = json.loads(z.read('FILES.json'))
        if set(manifest) != set(names) - {'FILES.json'}: raise ValueError('Archive inventory mismatch')
        out = Path(tmp)
        for info in infos:
            raw = z.read(info.filename)  # Bounded flat files; no archive code is executed.
            if info.filename != 'FILES.json' and manifest[info.filename] != {'bytes': len(raw), 'sha256': b.sha(raw)}:
                raise ValueError('Archive member hash mismatch')
            (out / info.filename).write_bytes(raw)
        j = b.Journal(out, plan_raw, core_raw, source_hashes, offline=True)
        state = json.loads((out / 'state.json').read_bytes()) if (out / 'state.json').exists() else {}
        if state.get('history'):
            actual = b.historical(j)
            if comparable(actual) != comparable(state['history']): raise ValueError('Historical summary mismatch')
        checked = 0
        rounds = state.get('rounds', [])
        for index, r in enumerate(rounds):
            if r['id'] != index: raise ValueError('Round ordering mismatch')
            if index and r['started_ms'] < rounds[index - 1]['started_ms'] + j.plan['live_interval_seconds'] * 1000:
                raise ValueError('Observation cadence violated')
            if set(r['assets']) != set(b.SYMBOLS): raise ValueError('Incomplete round identity')
            for symbol, reported in r['assets'].items():
                if reported.get('status') == 'VALID':
                    observed = b.live_asset(j, symbol, r['id'])
                    if observed != reported: raise ValueError('Depth observation summary mismatch')
                    if min(observed['received_ms']) < r['started_ms']: raise ValueError('Old observation reused as new')
                    checked += 1
        if 'extension' in state:
            actual = b.component(lambda: b.extension(j, state['extension_end_ms']))
            if comparable(actual) != comparable(state['extension']): raise ValueError('Extension summary mismatch')
        if 'final_risk' in state:
            actual = {s: b.component(lambda sym=s: b.risk_snapshot(j, sym, 'final-risk')) for s in b.SYMBOLS}
            if comparable(actual) != comparable(state['final_risk']): raise ValueError('Risk summary mismatch')
        reported = json.loads((out / 'summary.json').read_bytes())
        calculated = b.status_summary(j, reported.get('error'))
        if calculated != reported: raise ValueError('Overall summary mismatch')
        result = {'input_sha256': expected_sha, 'raw_responses_verified': sum(bool(r.get('raw_file')) for r in j.records),
                  'live_assets_recomputed': checked, 'summary': calculated, 'independent_exchange_attestation': False}
        if return_core:
            validation, datasets = b.assemble(j.core, j.get)
            if validation['status'] != 'COMPLETE':
                raise ValueError('Incomplete frozen013 core; no replay input export')
            result['replay_core_validation'] = validation
            result['datasets'] = datasets
            result['bridge_note'] = 'Original013 validator and raw rows unchanged; no strategy execution. New026 container adapter must be pinned by the next replay invocation before PnL.'
        return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True); p.add_argument('--sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): p.error('Output must be new')
    result = audit(a.input, a.sha256)
    b.write(a.output, result)
    print(json.dumps({'status': result['summary']['status'], 'verified': result['raw_responses_verified']}))
