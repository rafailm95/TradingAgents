"""Persist all019 accepted results, both failures and recovery transports.
Run after package verifier succeeds. Never replace an existing evidence archive.
"""
import base64,hashlib,json,os,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT.parent
OUT=ROOT/'research/experiments/019'


def main():
    verification=json.loads((OUT/'verification.json').read_bytes())
    if verification['status']!='PASS':raise ValueError('Verification not complete')
    paths=[]
    for folder in ['funding019-train1','funding019-train2','funding019-evaluation',
                   'funding019-result-recovery','funding019-result-recovery-v2']:
        paths += [(p,str(p.relative_to(WORK))) for p in (WORK/folder).rglob('*') if p.is_file()]
    paths += [(WORK/'binance-017-normalized.json.gz','binance-017-normalized.json.gz'),
              (WORK/'Futures_019_Funding_EL.html','Futures_019_Funding_EL.html')]
    repo_paths=[p for p in OUT.iterdir() if p.is_file()]
    repo_paths += [ROOT/p for p in [
        'docs/FUNDING_FUTURES_019.json','docs/FUNDING_FUTURES_019_RESULTS.md',
        'tradingagents/funding_signal_019.py','tradingagents/futures_replay_019.py',
        'tradingagents/bybit_replay.py','tradingagents/bybit_cashflow.py',
        'tradingagents/bybit_history.py','tradingagents/binance_archive.py',
        'tradingagents/strategy_lab.py','tradingagents/strategy_families.py',
        'scripts/run_funding_futures_019.py','scripts/package_funding_futures_019.py',
        'scripts/recover_funding_results_019.py','scripts/recover_funding_result_019_v2.py',
        'scripts/archive_funding_019.py','scripts/run_binance_replay_017.py',
        'tests/test_funding_futures_019.py','requirements-research.txt']]
    paths += [(p,'repository/'+str(p.relative_to(ROOT))) for p in repo_paths]
    archive=WORK/'Futures_019_Funding_Evidence.zip'
    with archive.open('xb') as f:
        with zipfile.ZipFile(f,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p,name in paths:z.write(p,name)
        f.flush();os.fsync(f.fileno())
    records=json.loads((OUT/'full_result_hashes.json').read_bytes())
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad:raise ValueError('Archive CRC failed: '+bad)
        for rec in records:
            raw=z.read(rec['path'])
            if hashlib.sha256(raw).hexdigest()!=rec['container_sha256']:
                raise ValueError('Archived container hash failed')
            if rec['encoding']=='base64+gzip':raw=base64.b64decode(json.loads(raw)['data'],validate=True)
            if hashlib.sha256(raw).hexdigest()!=rec['sha256']:
                raise ValueError('Archived decoded result hash failed')
    receipt={'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
             'bytes':archive.stat().st_size,'entries':len(paths),'accepted_results_verified':len(records),
             'zero_byte_originals_preserved':4,'zero_byte_first_recovery_preserved':1,'status':'PASS'}
    (OUT/'archive-verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()

