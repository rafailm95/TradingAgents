"""Reconstruct only four zero-byte019 files; require original byte hashes.
Original zero-byte evidence is never overwritten. No strategy/rule correction.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from tradingagents import futures_replay_019 as engine
from tradingagents import binance_archive as old
from run_funding_futures_019 import verify_freeze,load_archive,INPUT_SHA,T1,T2,T3
from run_binance_replay_017 import file_sha,save_result,write_new


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--evaluation',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Fresh recovery directory required')
    intent=json.loads((ROOT/'research/experiments/019/recovery-intent.json').read_bytes())
    verify_freeze(intent['original_freeze_sha256'])
    if file_sha(a.evaluation/'evaluation.json')!=intent['original_evaluation_sha256']:
        raise ValueError('Original manifest changed')
    e=json.loads((a.evaluation/'evaluation.json').read_bytes())
    _,datasets=load_archive(a.input,INPUT_SHA)
    m=old.prepare(datasets['ETHUSDT'],'ETHUSDT')
    a.output.mkdir()
    write_new(a.output/'intent.json',intent)
    recovered=[]
    for item in intent['failed_files']:
        name=item['file']
        if (a.evaluation/name).read_bytes()!=b'':raise ValueError('Original failed file changed')
        match=[]
        for key,path in e['walk_forward'].items():
            for fold in path['folds']:
                if fold['file']==name:match.append((key,fold))
        if len(match)!=1:raise ValueError('Ambiguous original scenario')
        key,fold=match[0];cost,tail=key.rsplit('_lag',1)
        lag,adverse=tail.split('_adverse')
        start,end=(T1,T2) if fold['year']==2024 else (T2,T3)
        candidate=fold['chosen']
        sig=engine.make_signals(m,candidate,end)
        r=engine.replay(m,start,end,candidate=candidate,cost=cost,lag=int(lag),
            adverse_funding=bool(int(adverse)),prepared_signals=sig,
            initial_usdt=fold['metrics']['initial_usdt'])
        record=save_result(a.output,name.removesuffix('.json.gz'),r)
        if record['sha256']!=item['expected_sha256'] or r['metrics']!=fold['metrics']:
            write_new(a.output/'mismatch.json',{'original':item,'reconstructed':record})
            raise ValueError('Recovery did not match original output bytes')
        recovered.append({'file':name,'original_zero_byte_path':str(a.evaluation/name),
            'sha256':record['sha256'],'byte_identical_to_original_manifest':True,
            'independent_wealth_audit':r['independent_wealth_audit']})
        print('Exact hash recovered: '+name,flush=True)
    write_new(a.output/'receipt.json',{'status':'PASS','recovered':recovered,'additional_integrity_replays':len(recovered),
        'cause':'Unknown zero-byte truncation after initial result hash was recorded. No source/input/rule/metric changes.',
        'original_zero_files_retained':True})


if __name__=='__main__':main()

