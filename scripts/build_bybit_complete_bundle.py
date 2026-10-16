"""Deterministic portable export of the unified public Bybit collector."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ['START_ALL.cmd', 'scripts/collect_bybit_complete.py', 'scripts/audit_bybit_complete.py',
         'scripts/collect_bybit_history.py', 'tradingagents/bybit_complete.py',
         'tradingagents/bybit_history.py', 'tradingagents/bybit_depth.py',
         'docs/BYBIT_COMPLETE_014.json', 'docs/BYBIT_HISTORY_013.json', 'docs/BYBIT_ALL_DATA_README_EL.txt']


def build(target, source_commit):
    if not re.fullmatch('[0-9a-f]{40}', source_commit): raise ValueError('Exact source commit required')
    data = {name: (ROOT / name).read_bytes() for name in FILES}
    data['READ_ME_EL.txt'] = data['docs/BYBIT_ALL_DATA_README_EL.txt']
    receipt = {'repository': 'rafailm95/TradingAgents', 'branch': 'codex/research-continuation-20261016',
               'source_commit': source_commit,
               'freeze_sha256': hashlib.sha256((ROOT / 'research/collection-014/freeze.json').read_bytes()).hexdigest(),
               'purpose': 'Unified public-data collection code export; no trading or account access'}
    data['SOURCE.json'] = (json.dumps(receipt, indent=2) + '\n').encode()
    data['SHA256SUMS.txt'] = ''.join(hashlib.sha256(value).hexdigest() + '  ' + name + '\n'
                                   for name, value in sorted(data.items())).encode()
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in sorted(data.items()):
            info = zipfile.ZipInfo('Bybit_All_Data/' + name, (2026, 10, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
            z.writestr(info, value)
    return {**receipt, 'filename': target.name, 'size_bytes': target.stat().st_size,
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'entries': len(data)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--source-commit', required=True)
    a = p.parse_args(); print(json.dumps(build(a.output, a.source_commit), indent=2))
