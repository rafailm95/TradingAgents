"""Frozen023 new-date transfer; identical six strategies and offline accounting."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip,hashlib,importlib.metadata,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from tradingagents import futures_calendar_023 as assets
from tradingagents import futures_replay_019 as ledger
from tradingagents import bybit_replay as original
from tradingagents.strategy_lab import bootstrap_max_mean
from run_funding_futures_019 import compact,daily_returns
T0,T1,T3=assets.TRAIN_START,assets.SPLIT,assets.END
from run_nr7_futures_020 import save_result,read_result,file_sha,write_new
CANDIDATES=original.CANDIDATES
COSTS=original.COSTS
FREEZE=ROOT/'research/experiments/023/engine-freeze.json'


def verify_freeze(digest):
    if file_sha(FREEZE)!=digest:raise ValueError('External engine freeze mismatch')
    pin=json.loads(FREEZE.read_bytes())
    for group in ('source_hashes','preserved_files'):
        for name,sha in pin[group].items():
            if file_sha(ROOT/name)!=sha:raise ValueError('Frozen source changed: '+name)
    if sys.version_info[:2]!=(3,12):raise ValueError('Python3.12 required')
    for package,version in pin['runtime'].items():
        if importlib.metadata.version(package)!=version:raise ValueError('Runtime mismatch')
    return pin


def load_market(roots,symbol,pin):
    return assets.load_market(roots[0],roots[1],symbol,pin)


def selection_summary(training):return original.select_training(training)


def train_asset(job):
    data_root,folder,symbol,pin,stage=job;folder=Path(folder)/symbol;folder.mkdir()
    market=load_market(data_root,symbol,pin);end=T1
    training={};records={}
    for candidate in CANDIDATES:
        sig=ledger.make_signals(market,candidate,end);training[candidate]={}
        for cost in COSTS:
            result=ledger.replay(market,T0,end,candidate=candidate,cost=cost,prepared_signals=sig)
            record=save_result(folder,stage+'_'+candidate+'_'+cost,result)
            record['file']=symbol+'/'+record['file'];records[candidate+'_'+cost]=record
            training[candidate][cost]=compact(result)
        print(stage+' '+symbol+' '+candidate,flush=True)
    output={'symbol':symbol,'training':training,'selection':selection_summary(training),'new_results':records,'new_simulations':len(records),'bounds':[T0,end]}
    write_new(folder/'selection.json',output);return output


def read_selection(root,digest,pin,freeze,stage):
    if file_sha(root/'selection.json')!=digest:raise ValueError('External selection pin mismatch')
    s=json.loads((root/'selection.json').read_bytes())
    if s['stage']!=stage or s['freeze_sha256']!=freeze or set(s['assets'])!=set(pin['inputs']):raise ValueError('Selection identity mismatch')
    for symbol,data in s['assets'].items():
        if data['selection']!=selection_summary(data['training']):raise ValueError('Training selection differs')
        if data['bounds']!=[T0,T1]:raise ValueError('Training window differs')
        if len(data['new_results'])!=12:raise ValueError('Incomplete training')
        for record in data['new_results'].values():
            r=read_result(root/record['file'],record['sha256'],record['container_sha256'])
            if r['symbol']!=symbol or compact(r)!=data['training'][r['candidate']][r['cost']]:raise ValueError('Training summary mismatch')
    return s


def scenario_gate(gate,cost,lag,adverse):
    failures=[x for x in gate['failed_scenarios'] if (x['cost'],x['lag'],x['adverse_funding'])==(cost,lag,adverse)]
    if len(failures)>1:raise ValueError('Duplicate scenario failure')
    return {'passed':not failures,'failed_gates':failures[0]['reasons'] if failures else []}


def evaluate_asset(job):
    data_root,folder,symbol,pin,s1=job;folder=Path(folder)/symbol;folder.mkdir()
    market=load_market(data_root,symbol,pin)
    records={};comparisons={};gates={};curves={};benchmarks={};audits=[]
    def save(name,result):
        rec=save_result(folder,name,result);rec['file']=symbol+'/'+rec['file'];records[rec['file']]=rec
        audits.append({'file':rec['file'],**result['independent_wealth_audit']});return rec
    for candidate in CANDIDATES:
        sig=ledger.make_signals(market,candidate,T3);rows=[];summaries=[]
        for cost in COSTS:
            for lag in (0,1,2):
                for adverse in (False,True):
                    r=ledger.replay(market,T1,T3,candidate=candidate,cost=cost,lag=lag,adverse_funding=adverse,prepared_signals=sig)
                    rec=save(f'eval_{candidate}_{cost}_lag{lag}_adverse{int(adverse)}',r)
                    meta={'cost':cost,'lag_days':lag,'adverse_funding_5bps':adverse}
                    rows.append({**rec,**meta});summaries.append({**compact(r),**meta})
                    if lag==0 and not adverse:curves[candidate+'|'+cost]=daily_returns(r).tolist()
        comparisons[candidate]=rows;gates[candidate]=original.evaluation_gate(summaries)
        print('evaluation '+symbol+' '+candidate,flush=True)
    r=ledger.replay(market,T1,T3,benchmark='cash');benchmarks['cash']=save('benchmark_cash',r)
    for cost in COSTS:
        for adverse in (False,True):
            r=ledger.replay(market,T1,T3,benchmark='buy_hold50',cost=cost,adverse_funding=adverse)
            key=cost+'_adverse'+str(int(adverse));benchmarks[key]=save('benchmark_hold50_'+key,r)
            if not adverse:curves['buy_hold50|'+cost]=daily_returns(r).tolist()
    # The 2026 fold uses the exact already-computed candidate scenario.
    # Independently funded2026 is not compounded onto prior2024/2025 accounts.
    chosen=s1['selection']['selected'];selected={};managed=None
    if chosen=='cash':
        r=ledger.replay(market,T1,T3,benchmark='cash',managed_cash=True)
        managed=save('selected_managed_cash',r)
        managed_gate=original.evaluation_gate([{**compact(r),'cost':cost,'lag_days':lag,'adverse_funding_5bps':adverse}
            for cost in COSTS for lag in (0,1,2) for adverse in (False,True)])
    for cost in COSTS:
        for lag in (0,1,2):
            for adverse in (False,True):
                key=f'{cost}_lag{lag}_adverse{int(adverse)}'
                if chosen=='cash':record=managed
                else:record=next(x for x in comparisons[chosen] if x['cost']==cost and x['lag_days']==lag and x['adverse_funding_5bps']==adverse)
                # Matching frozen scenario gate, including every failed criterion.
                gate=managed_gate if chosen=='cash' else gates[chosen]
                selected[key]={'chosen':chosen,'record':record,'reused_without_replay':chosen!='cash','metrics':record['metrics'],'gate':scenario_gate(gate,cost,lag,adverse)}
    out={'symbol':symbol,'comparisons':comparisons,'gates':gates,'benchmarks':benchmarks,'selected_2026_fold':selected,'new_results':records,'new_simulations':len(records),'main_selection':s1['selection'],'daily_returns_for_diagnostics':curves,'audits':audits}
    write_new(folder/'evaluation.json',out);return out


def multiplicity(results):
    output={}
    for cost in COSTS:
        for benchmark in ('cash','buy_hold50'):
            panels=[]
            for symbol,data in results.items():
                curves=data['daily_returns_for_diagnostics'];panel=np.column_stack([curves[c+'|'+cost] for c in CANDIDATES])
                base=np.zeros(len(panel)) if benchmark=='cash' else np.array(curves['buy_hold50|'+cost])
                excess=panel-base[:,None];panels.append(excess)
                r=bootstrap_max_mean(excess,np.zeros(len(panel)),block=30,repeats=2000,seed=20261017)
                r.update(operating_costs_included=True,compatible_asset_candidate_pairs=6,prior_search_corrected=False)
                output[symbol+'|'+cost+'|'+benchmark]=r
            panel=np.column_stack(panels)
            r=bootstrap_max_mean(panel,np.zeros(len(panel)),block=30,repeats=2000,seed=20261017)
            r.update(operating_costs_included=True,compatible_asset_candidate_pairs=panel.shape[1],prior_search_corrected=False,note='Shareddateblocks preservecrossassetdependence. Reuseddesign and50priorvariantsearchnotcorrected; nofuturevalidation.')
            output['joint|'+cost+'|'+benchmark]=r
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior-root',type=Path,required=True);p.add_argument('--extension-root',type=Path,required=True)
    p.add_argument('--freeze-sha256',required=True);p.add_argument('--stage',choices=['train','evaluate'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--training',type=Path);p.add_argument('--selection-sha256')
    a=p.parse_args();pin=verify_freeze(a.freeze_sha256)
    if a.output.exists():raise ValueError('New output directory required; preserve every attempt')
    if not pin['inputs'] or not set(pin['inputs'])<=set(assets.SYMBOLS):raise ValueError('No eligible frozen assets')
    a.output.mkdir(parents=True);write_new(a.output/'intent.json',{k:str(v) for k,v in vars(a).items()})
    try:
        selection=None
        if a.stage=='evaluate':selection=read_selection(a.training,a.selection_sha256,pin,a.freeze_sha256,'train')
        roots=(str(a.prior_root),str(a.extension_root))
        with ProcessPoolExecutor(max_workers=min(3,len(pin['inputs']))) as pool:
            if a.stage=='train':
                values=list(pool.map(train_asset,[(roots,str(a.output),s,pin,'train') for s in pin['inputs']]))
                result={'stage':'train','freeze_sha256':a.freeze_sha256,'assets':{v['symbol']:v for v in values},'new_simulations':sum(v['new_simulations'] for v in values),'evaluation_computed':False}
                write_new(a.output/'selection.json',result)
            else:
                values=list(pool.map(evaluate_asset,[(roots,str(a.output),s,pin,selection['assets'][s]) for s in pin['inputs']]))
                result={'experiment':'023','freeze_sha256':a.freeze_sha256,'assets':{v['symbol']:v for v in values},'selection_sha256':a.selection_sha256,'new_simulations':sum(v['new_simulations'] for v in values),'new_unique_variants':0,'total_unique_variants':50}
                result['multiplicity']=multiplicity(result['assets'])
                write_new(a.output/'evaluation.json',result)
    except Exception as exc:
        write_new(a.output/'failure.json',{'type':type(exc).__name__,'message':str(exc)});raise

if __name__=='__main__':main()
