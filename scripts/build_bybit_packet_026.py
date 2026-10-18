"""Deterministic portable026 export, with original013/014 sources unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=['tradingagents/bybit_packet_026.py','tradingagents/bybit_history.py','tradingagents/bybit_depth.py',
       'scripts/collect_bybit_packet_026.py','scripts/audit_bybit_packet_026.py','scripts/verify_bybit_packet_026.py',
       'scripts/collect_bybit_history.py','docs/BYBIT_PACKET_026.json','docs/BYBIT_HISTORY_013.json',
       'research/collection-026/freeze.json']


def build(target, source_commit):
    if not re.fullmatch('[0-9a-f]{40}',source_commit):raise ValueError('Exact source commit required')
    data={name:(ROOT/name).read_bytes() for name in FILES}
    data['START_ALL.cmd']=(ROOT/'collectors/bybit_packet_026/START_ALL.cmd').read_bytes()
    data['OPTIONAL_SETTINGS.json']=(ROOT/'collectors/bybit_packet_026/OPTIONAL_SETTINGS.json').read_bytes()
    data['READ_ME_EL.txt']=(ROOT/'docs/BYBIT_PACKET_026_README_EL.txt').read_bytes()
    receipt={'repository':'rafailm95/TradingAgents','branch':'codex/research-continuation-20261016',
             'source_commit':source_commit,'freeze_sha256':hashlib.sha256(data['research/collection-026/freeze.json']).hexdigest(),
             'purpose':'Public collection code, no credentials/orders. Optional settings are the only user-editable file.'}
    data['SOURCE.json']=(json.dumps(receipt,indent=2)+'\n').encode()
    data['PACKAGE_FILES.json']=(json.dumps({k:hashlib.sha256(v).hexdigest() for k,v in sorted(data.items()) if k!='OPTIONAL_SETTINGS.json'},indent=2)+'\n').encode()
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for name,value in sorted(data.items()):
            info=zipfile.ZipInfo('Bybit_Complete_Packet/'+name,(2026,10,18,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,value)
    with zipfile.ZipFile(target) as z:
        if z.testzip():raise ValueError('Portable ZIP CRC error')
        for name,value in data.items():
            if z.read('Bybit_Complete_Packet/'+name)!=value:raise ValueError('ZIP content mismatch')
    return {**receipt,'filename':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'members':len(data)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-commit',required=True)
    a=p.parse_args();print(json.dumps(build(a.output,a.source_commit),indent=2))
