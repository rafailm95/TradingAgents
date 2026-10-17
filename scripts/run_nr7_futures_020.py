"""One frozen NR7 family, hash-verified reference reuse and annual WFA. Offline only."""
import argparse
import base64
from decimal import Decimal as D
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from tradingagents import nr7_futures_020 as engine
from tradingagents import binance_archive as old
from tradingagents.strategy_lab import bootstrap_max_mean
from run_funding_futures_019 import (compact, old_result, old_manifest, daily_returns,
    combine_folds, T0, T1, T2, T3, INPUT_SHA, ARCHIVE_SHA)
from run_binance_replay_017 import file_sha, write_new, load_archive

FREEZE = ROOT / 'research/experiments/020/freeze.json'
PART_SHAS = ('71443bab8d0159f4cae8c887e7c027c8b32d920d0ac2f99f3e2216fe978515d7',
             '5f586b73e1fe4b9b599d1ba12ce0fc407695b2836d26896056900df828119986',
             '00bd8a95856112b16814a22e65ddef2b855770ce2172aa35703a17fac98ae8ca')


def verify_freeze(expected):
    if file_sha(FREEZE) != expected: raise ValueError('External freeze hash mismatch')
    pin = json.loads(FREEZE.read_bytes())
    for group in ('source_hashes', 'preserved_files'):
        for path, digest in pin[group].items():
            if file_sha(ROOT/path) != digest: raise ValueError('Changed frozen file: '+path)
    if sys.version_info[:2] != (3, 12): raise ValueError('Python3.12 required')
    for name, version in pin['runtime'].items():
        if importlib.metadata.version(name) != version: raise ValueError('Runtime package mismatch')
    return pin


def save_result(folder, name, result):
    audit = engine.audit_wealth(result)
    payload = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    raw = gzip.compress(payload, mtime=0)
    digest = hashlib.sha256(raw).hexdigest()
    envelope = {'encoding': 'base64+gzip', 'decoded_sha256': digest,
                'decoded_bytes': len(raw), 'payload_base64': base64.b64encode(raw).decode()}
    path = folder/(name+'.envelope.json')
    with path.open('xb') as f:
        f.write((json.dumps(envelope, sort_keys=True)+'\n').encode()); f.flush(); os.fsync(f.fileno())
    check = read_result(path, digest)
    if check != result: raise ValueError('Persistence roundtrip mismatch')
    return {'file': path.name, 'sha256': digest, 'container_sha256': file_sha(path),
            'bytes': path.stat().st_size, 'encoding': 'base64+gzip', **compact(result), 'audit': audit}


def read_result(path, digest, container_sha=None):
    if container_sha and file_sha(path) != container_sha: raise ValueError('Container hash mismatch')
    envelope = json.loads(path.read_bytes())
    raw = base64.b64decode(envelope['payload_base64'], validate=True)
    if hashlib.sha256(raw).hexdigest() != digest or envelope['decoded_sha256'] != digest:
        raise ValueError('Decoded result hash mismatch')
    result = json.loads(gzip.decompress(raw)); engine.audit_wealth(result)
    return result


class References:
    def __init__(self, archive, parts):
        if file_sha(archive) != ARCHIVE_SHA: raise ValueError('017 archive mismatch')
        if len(parts) != 3 or tuple(map(file_sha, parts)) != PART_SHAS: raise ValueError('019 parts mismatch')
        self.z017 = zipfile.ZipFile(archive)
        self.parts = [zipfile.ZipFile(p) for p in parts]
        self.members = {}
        for z in self.parts:
            for name in z.namelist():
                if name in self.members: raise ValueError('Duplicate archive member')
                self.members[name] = z
        self.resolved = {x['original_path']: x for x in json.loads((ROOT/'research/experiments/019/full_result_hashes.json').read_bytes())}
        self.train1 = self.manifest('funding019-train1/selection.json', '569510dbbe40d2a121d55cfe5ba2fd553719a31e2c80cb8e1bbcd04e3cd975bc')
        self.train2 = self.manifest('funding019-train2/selection.json', '841a467ecff8f93cfe276b366ba6a01eb8d37abdf4f928d722230179353b8f9f')
        self.evaluation = self.manifest('funding019-evaluation/evaluation.json', '9b71fc05e3ab4f12b7036bba7e802e696e6b2e8057f7ed3d5a816a9c08df865c')

    def manifest(self, path, sha):
        raw = self.members[path].read(path)
        if hashlib.sha256(raw).hexdigest() != sha: raise ValueError('019 manifest mismatch')
        return json.loads(raw)

    def result019(self, original, expected):
        record = self.resolved[original]; path = record['path']
        raw = self.members[path].read(path)
        if hashlib.sha256(raw).hexdigest() != record['container_sha256']: raise ValueError('019 container mismatch')
        if record['encoding'] == 'base64+gzip':
            envelope = json.loads(raw)
            raw = base64.b64decode(envelope['data'], validate=True)
        if hashlib.sha256(raw).hexdigest() != record['sha256'] or record['sha256'] != expected['sha256']:
            raise ValueError('019 result mismatch')
        result = json.loads(gzip.decompress(raw)); engine.audit_wealth(result)
        if result['metrics'] != expected['metrics'] or result['status'] != expected['status']: raise ValueError('019 summary mismatch')
        return result

    def training(self, stage, candidate, cost):
        previous = self.train1 if stage == 'train1' else self.train2
        key = candidate+'_'+cost
        if stage == 'train1' and candidate in old.CANDIDATES:
            rec = old_manifest(self.z017, 'training')['results']['ETHUSDT'][candidate][cost]
            result = old_result(self.z017, 'binance-017-training', rec)
        else:
            rec = previous['new_results'][key]
            result = self.result019('funding019-'+stage+'/'+rec['file'], rec)
        if compact(result) != previous['training'][candidate][cost]: raise ValueError('Training reference mismatch')
        return result, rec

    def evaluation_result(self, candidate, cost, lag, adverse):
        rec = next(r for r in self.evaluation['comparisons_all8'][candidate]
                   if (r['cost'],r['lag_days'],r['adverse_funding_5bps']) == (cost,lag,adverse))
        if candidate in old.CANDIDATES:
            result = old_result(self.z017, 'binance-017-evaluation', rec)
        else: result = self.result019('funding019-evaluation/'+rec['file'], rec)
        return result, rec


def read_selection(folder, digest, freeze, stage):
    p = folder/'selection.json'
    if file_sha(p) != digest: raise ValueError('Selection external hash mismatch')
    s = json.loads(p.read_bytes())
    if (s['stage'],s['freeze_sha256'],s['input_sha256']) != (stage,freeze,INPUT_SHA): raise ValueError('Selection identity mismatch')
    if s['selection'] != engine.select_training(s['training']): raise ValueError('Selection algorithm mismatch')
    for rec in s['new_results'].values():
        r = read_result(folder/rec['file'], rec['sha256'], rec['container_sha256'])
        if compact(r) != s['training'][r['candidate']][r['cost']]: raise ValueError('Training summary mismatch')
    return s


def train(market, refs, folder, freeze, stage, prior=None):
    end = T1 if stage == 'train1' else T2
    training, records, reused = {}, {}, []
    for candidate in engine.CANDIDATES:
        training[candidate] = {}
        sig = engine.make_signals(market,candidate,end) if candidate in engine.NEW_CANDIDATES else None
        for cost in engine.COSTS:
            if candidate in engine.NEW_CANDIDATES:
                r = engine.replay(market,T0,end,candidate=candidate,cost=cost,prepared_signals=sig)
                records[candidate+'_'+cost] = save_result(folder,stage+'_'+candidate+'_'+cost,r)
            else:
                r, rec = refs.training(stage,candidate,cost); reused.append(rec)
            training[candidate][cost] = compact(r)
        print(stage+': '+candidate,flush=True)
    result = {'stage':stage,'freeze_sha256':freeze,'input_sha256':INPUT_SHA,'training_bounds':[T0,end],
              'selection':engine.select_training(training),'training':training,'new_results':records,
              'reused_results':reused,'new_simulations':len(records),'evaluation_computed':False,
              'prior_selection_sha256':prior}
    write_new(folder/'selection.json',result)


def reusable_fold(result, *, chosen, capital, start, end, cost, lag, adverse):
    identity = result['candidate'] if result['candidate'] else result['benchmark']
    return (identity == chosen and D(result['metrics']['initial_usdt']) == D(capital)
            and result['start_ms'] == start and result['end_exclusive_ms'] == end
            and result['cost'] == cost and result['adverse_funding_5bps'] == adverse
            and result['lag_days'] == (0 if chosen == 'cash' else lag)
            and result['status'] == 'COMPLETE')


def evaluate(market, refs, folder, freeze, s1, s2, selection_hashes):
    comparisons,gates,records,curves,audits = {},{},{},{},[]
    for candidate in engine.CANDIDATES:
        rows,summaries = [],[]
        sig = engine.make_signals(market,candidate,T3) if candidate in engine.NEW_CANDIDATES else None
        for cost in engine.COSTS:
            for lag in (0,1,2):
                for adverse in (False,True):
                    new = candidate in engine.NEW_CANDIDATES
                    if new:
                        r = engine.replay(market,T1,T3,candidate=candidate,cost=cost,lag=lag,adverse_funding=adverse,prepared_signals=sig)
                        rec = save_result(folder,f'eval_{candidate}_{cost}_lag{lag}_adverse{int(adverse)}',r)
                        records[rec['file']] = rec
                    else: r,rec = refs.evaluation_result(candidate,cost,lag,adverse)
                    audits.append({'file':rec['file'],'new':new,**r['independent_wealth_audit']})
                    row = {**rec,'cost':cost,'lag_days':lag,'adverse_funding_5bps':adverse,'new_execution':new}
                    rows.append(row); summaries.append({**compact(r),**{k:row[k] for k in ('cost','lag_days','adverse_funding_5bps')}})
                    if lag == 0 and not adverse: curves[(candidate,cost)] = daily_returns(r)
        comparisons[candidate]=rows; gates[candidate]=engine.evaluation_gate(summaries)
        print('evaluation: '+candidate,flush=True)
    benchmarks = {}
    for name,rec in refs.evaluation['reused017_benchmarks'].items():
        r = old_result(refs.z017,'binance-017-evaluation',rec); benchmarks[name]=rec
        if not r['adverse_funding_5bps']: curves[(r['benchmark'],r['cost'])]=daily_returns(r)
    multiplicity = {}
    for cost in engine.COSTS:
        panel = np.column_stack([curves[(c,cost)] for c in engine.CANDIDATES])
        for benchmark in ('cash','buy_hold50'):
            base = np.zeros(len(panel)) if benchmark == 'cash' else curves[(benchmark,cost)]
            diagnostic = bootstrap_max_mean(panel,base,block=30,repeats=2000,seed=20261017)
            diagnostic.update(operating_costs_included=True,note='Ten compatible native futures variants; excludes40spot-only variants and prior search/design choices. Conditional exploratory diagnostic, not independent confirmation.')
            multiplicity[cost+'_'+benchmark]=diagnostic
    wfa = {}; reuse_count=0
    for cost in engine.COSTS:
        for lag in (0,1,2):
            for adverse in (False,True):
                key=f'{cost}_lag{lag}_adverse{int(adverse)}'; capital='10000'; results=[]; rows=[]
                for year,start,end,selection in ((2024,T1,T2,s1),(2025,T2,T3,s2)):
                    chosen=selection['selection']['selected']
                    oldrec=next(r for r in refs.evaluation['walk_forward'][key]['folds'] if r['year']==year)
                    previous=refs.result019('funding019-evaluation/'+oldrec['file'],oldrec)
                    reuse=reusable_fold(previous,chosen=chosen,capital=capital,start=start,end=end,cost=cost,lag=lag,adverse=adverse)
                    if reuse:
                        r,rec=previous,oldrec; reuse_count+=1
                    else:
                        kwargs={'benchmark':'cash','managed_cash':True} if chosen=='cash' else {'candidate':chosen,'lag':lag,'prepared_signals':engine.make_signals(market,chosen,end)}
                        r=engine.replay(market,start,end,cost=cost,adverse_funding=adverse,initial_usdt=capital,**kwargs)
                        rec=save_result(folder,f'wfa_{year}_{key}',r); records[rec['file']]=rec
                    rows.append({**rec,'year':year,'chosen':chosen,'new_execution':not reuse}); results.append(r)
                    audits.append({'file':rec['file'],'new':not reuse,**r['independent_wealth_audit']})
                    capital=r['metrics']['final_cash_usdt']
                    if r['status']!='COMPLETE': break
                wfa[key]={'folds':rows,**combine_folds(results)}
                print('walk-forward: '+key,flush=True)
    selected=s1['selection']['selected']
    result={'experiment':'020','freeze_sha256':freeze,'input_sha256':INPUT_SHA,'selection_hashes':selection_hashes,
            'comparisons_all10':comparisons,'gates_all10':gates,'reused_benchmarks':benchmarks,
            'main_train_selected':selected,'main_selected_results':comparisons.get(selected,benchmarks),
            'expanding_training_selections':[s1['selection'],s2['selection']], 'walk_forward':wfa,
            'multiplicity':multiplicity,'audits':audits,'new_results':records,
            'new_simulations_this_stage':len(records),'reused_wfa_folds':reuse_count,
            'classification':'Exploratory reused Binance history; no prospective evidence or orders'}
    write_new(folder/'evaluation.json',result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True); p.add_argument('--reference-archive',type=Path,required=True)
    p.add_argument('--reference-parts',nargs=3,type=Path,required=True); p.add_argument('--freeze-sha256',required=True)
    p.add_argument('--stage',choices=['train1','train2','evaluate'],required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--train1',type=Path); p.add_argument('--selection1-sha256'); p.add_argument('--train2',type=Path); p.add_argument('--selection2-sha256')
    a=p.parse_args()
    if a.output.exists(): p.error('Output must be new; preserve all attempts')
    verify_freeze(a.freeze_sha256); refs=References(a.reference_archive,a.reference_parts)
    _,datasets=load_archive(a.input,INPUT_SHA)
    if set(datasets)!={'ETHUSDT'}: raise ValueError('Asset mismatch')
    market=old.prepare(datasets['ETHUSDT'],'ETHUSDT')
    if (market.start,market.end)!=(old.START,old.END): raise ValueError('Coverage mismatch')
    a.output.mkdir(parents=True); write_new(a.output/'intent.json',{k:str(v) for k,v in vars(a).items()})
    try:
        if a.stage=='train1': train(market,refs,a.output,a.freeze_sha256,a.stage)
        else:
            s1=read_selection(a.train1,a.selection1_sha256,a.freeze_sha256,'train1')
            if a.stage=='train2': train(market,refs,a.output,a.freeze_sha256,a.stage,a.selection1_sha256)
            else:
                s2=read_selection(a.train2,a.selection2_sha256,a.freeze_sha256,'train2')
                if s2['prior_selection_sha256']!=a.selection1_sha256: raise ValueError('Selection chain mismatch')
                evaluate(market,refs,a.output,a.freeze_sha256,s1,s2,[a.selection1_sha256,a.selection2_sha256])
    except Exception as exc:
        write_new(a.output/'failure.json',{'type':type(exc).__name__,'message':str(exc)}); raise


if __name__=='__main__': main()
