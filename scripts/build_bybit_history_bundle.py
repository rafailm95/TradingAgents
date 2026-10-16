"""Build a deterministic portable code export from the versioned repository."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ['START_HISTORY.cmd', 'scripts/collect_bybit_history.py', 'scripts/audit_bybit_history.py',
         'tradingagents/bybit_depth.py', 'tradingagents/bybit_history.py', 'tradingagents/bybit_cashflow.py',
         'docs/BYBIT_HISTORY_013.json', 'docs/BYBIT_PERPETUAL_REPLAY_013.json',
         'docs/BYBIT_HISTORY_COLLECTOR_EL.txt']


def build(output, source_commit):
    if not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError('Exact source commit required')
    data = {name: (ROOT / name).read_bytes() for name in FILES}
    data['READ_ME_EL.txt'] = data['docs/BYBIT_HISTORY_COLLECTOR_EL.txt']
    receipt = {'repository': 'rafailm95/TradingAgents', 'branch': 'codex/research-continuation-20261016',
               'source_commit': source_commit, 'freeze_sha256': hashlib.sha256((ROOT / 'research/experiments/013/freeze.json').read_bytes()).hexdigest(),
               'purpose': 'Versioned source-code export; public historical data collector, no trading.'}
    data['SOURCE.json'] = (json.dumps(receipt, indent=2) + '\n').encode()
    data['SHA256SUMS.txt'] = ''.join(hashlib.sha256(raw).hexdigest() + '  ' + name + '\n'
                                   for name, raw in sorted(data.items())).encode()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(data.items()):
            info = zipfile.ZipInfo('Bybit_History_Collector/' + name, (2026, 10, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    return {**receipt, 'file_name': output.name, 'size_bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'file_count': len(data)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-commit', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.output, a.source_commit), indent=2))
