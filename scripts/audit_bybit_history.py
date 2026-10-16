"""Offline audit of a returned history ZIP against an external SHA256 and protocol.
Never executes archive contents or connects to an API. Optional normalized output
is allowed only after all three symbols pass complete coverage checks.
"""
import argparse
import gzip
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tradingagents'))
from collect_bybit_history import Session, PROTOCOL, sources, write
from bybit_history import assemble, daily_trade, sha


def audit(path, expected_sha, protocol_raw=None, source_hashes=None):
    protocol_raw = PROTOCOL.read_bytes() if protocol_raw is None else protocol_raw
    source_hashes = sources() if source_hashes is None else source_hashes
    if path.stat().st_size > 150_000_000 or sha(path.read_bytes()) != expected_sha:
        raise ValueError('Archive size/hash mismatch')
    with zipfile.ZipFile(path) as z:
        infos = z.infolist(); names = [p.filename for p in infos]
        if (len(infos) > 2000 or len(names) != len(set(names)) or
                sum(p.file_size for p in infos) > 200_000_000 or
                any('/' in n or '\\' in n or n in ('.', '..') for n in names)):
            raise ValueError('Unsafe, duplicate, or oversized ZIP entries')
        if any(p.file_size > 20_000_000 or p.flag_bits & 1 or p.is_dir() for p in infos):
            raise ValueError('Oversized/encrypted/directory entry')
        if z.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        state = json.loads(z.read('session.json'))
        known = {'session.json', 'protocol.json', 'summary.json'} | {r['raw_file'] for r in state['requests'] if 'raw_file' in r}
        if set(names) != known:
            raise ValueError('Unregistered archive entry')
        # Flat, bounded, pre-validated names only; scripts and links are not included.
        with tempfile.TemporaryDirectory(prefix='bybit-history-audit-') as folder:
            root = Path(folder)
            for name in names:
                (root / name).write_bytes(z.read(name))
            session = Session(root, protocol_raw, source_hashes, offline=True)
            validation, datasets = assemble(json.loads(protocol_raw), session.get)
            reported = json.loads((root / 'summary.json').read_bytes())
            if reported.get('validation') != validation or reported.get('status') != validation['status']:
                raise ValueError('Reported coverage does not match recomputation')
            if session.used != set(session.cache):
                raise ValueError('Unexpected successful requests')
            receipt = {'input_sha256': expected_sha, 'protocol_sha256': sha(protocol_raw),
                       'raw_responses_verified': sum('raw_file' in r for r in state['requests']),
                       'successful_pages': len(session.cache), 'validation': validation,
                       'independent_exchange_attestation': False, 'real_strategy_simulations': 0}
            if validation['status'] == 'COMPLETE':
                for dataset in datasets.values():
                    dataset['daily_trade'] = daily_trade(dataset['trade'])
            return receipt, datasets


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--normalized', type=Path)
    a = p.parse_args()
    if a.output.exists() or (a.normalized and a.normalized.exists()):
        p.error('Output must be new; accepted evidence is never overwritten')
    receipt, datasets = audit(a.input, a.sha256)
    write(a.output, receipt)
    if receipt['validation']['status'] != 'COMPLETE':
        p.exit(2, 'Coverage/schedule review required. No normalized replay input emitted.\n')
    if a.normalized:
        with gzip.open(a.normalized, 'wt', encoding='utf-8') as f:
            json.dump({'source_receipt': receipt, 'data': datasets}, f, allow_nan=False)
    print(json.dumps({'status': 'COMPLETE', 'raw_responses_verified': receipt['raw_responses_verified']}))
