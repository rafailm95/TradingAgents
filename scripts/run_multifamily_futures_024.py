"""User-authorized20newvariants/10families on3assets; bounded offline024 research."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip,hashlib,importlib.metadata,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from tradingagents import binance_assets_021 as assets
from tradingagents import multifamily_futures_024 as ledger
from tradingagents import sol_funding_022 as sol
from tradingagents import bybit_replay as original
from tradingagents.strategy_lab import bootstrap_max_mean
from run_funding_futures_019 import compact,combine_folds,daily_returns,T0,T1,T2,T3
from run_nr7_futures_020 import save_result,read_result,file_sha,write_new
CANDIDATES=ledger.CANDIDATES
NEW_CANDIDATES=ledger.NEW_CANDIDATES
COSTS=original.COSTS
FREEZE=ROOT/'research/experiments/024/freeze.json'


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


def load_market(root,symbol,pin):
    p=root/symbol/'normalized.json.gz';expected=pin['inputs'][symbol]
    if file_sha(p)!=expected['normalized_sha256']:raise ValueError('Input SHA mismatch')
    if file_sha(root/symbol/'manifest.json')!=expected['manifest_sha256']:raise ValueError('Raw manifest mismatch')
    value=json.loads(gzip.decompress(p.read_bytes()))
    if value['schema']!=('binance022_normalized_v1' if symbol=='SOLUSDT' else 'binance021_normalized_v1') or set(value['datasets'])!={symbol} or value['audit']['status']!='COMPLETE':raise ValueError('Input identity mismatch')
    m=(sol if symbol=='SOLUSDT' else assets).prepare(value['datasets'][symbol],symbol)
    if (m.start,m.end)!=(assets.START,assets.END):raise ValueError('Frozen dates mismatch')
    return m


def selection_summary(training):return ledger.select_training(training)

def prior_summary(symbol,stage):
    batch='022' if symbol=='SOLUSDT' else '021'
    filename='evaluation.json' if stage=='evaluation' else 'selection-'+stage+'.json'
    path=ROOT/'research/experiments'/batch/filename
    return json.loads(path.read_bytes())['assets'][symbol],{'batch':batch,'path':path.relative_to(ROOT).as_posix(),'sha256':file_sha(path)}



def train_asset(job):
    data_root,folder,symbol,pin,stage=job;folder=Path(folder)/symbol;folder.mkdir()
    market=load_market(Path(data_root),symbol,pin);end=T1 if stage=='train1' else T2
    prior,origin=prior_summary(symbol,stage)
    training=dict(prior['training']);records={}
    for candidate in NEW_CANDIDATES:
        sig=ledger.make_signals(market,candidate,end);training[candidate]={}
        for cost in COSTS:
            result=ledger.replay(market,T0,end,candidate=candidate,cost=cost,prepared_signals=sig)
            record=save_result(folder,stage+'_'+candidate+'_'+cost,result)
            record['file']=symbol+'/'+record['file'];records[candidate+'_'+cost]=record
            training[candidate][cost]=compact(result)
        print(stage+' '+symbol+' '+candidate,flush=True)
    output={'symbol':symbol,'training':training,'selection':selection_summary(training),'new_results':records,'new_simulations':len(records),'bounds':[T0,end],'reused_training_source':origin,'reused_training_scenarios':12}
    write_new(folder/'selection.json',output);return output


def read_selection(root,digest,pin,freeze,stage):
    if file_sha(root/'selection.json')!=digest:raise ValueError('External selection pin mismatch')
    s=json.loads((root/'selection.json').read_bytes())
    if s['stage']!=stage or s['freeze_sha256']!=freeze or set(s['assets'])!=set(pin['inputs']):raise ValueError('Selection identity mismatch')
    for symbol,data in s['assets'].items():
        if data['selection']!=selection_summary(data['training']):raise ValueError('Training selection differs')
        if data['bounds']!=[T0,T1 if stage=='train1' else T2]:raise ValueError('Training window differs')
        if len(data['new_results'])!=40:raise ValueError('Incomplete training')
        for record in data['new_results'].values():
            r=read_result(root/record['file'],record['sha256'],record['container_sha256'])
            if r['symbol']!=symbol or compact(r)!=data['training'][r['candidate']][r['cost']]:raise ValueError('Training summary mismatch')
    return s


def evaluate_asset(job):
    data_root,reference_root,folder,symbol,pin,s1,s2=job;folder=Path(folder)/symbol;folder.mkdir()
    market=load_market(Path(data_root),symbol,pin)
    prior,origin=prior_summary(symbol,'evaluation')
    records={};comparisons=dict(prior['comparisons']);gates=dict(prior['gates']);curves=dict(prior['daily_returns_for_diagnostics']);benchmarks=dict(prior['benchmarks']);audits=[];reused_folds=[]
    def save(name,result):
        rec=save_result(folder,name,result);rec['file']=symbol+'/'+rec['file'];records[rec['file']]=rec
        audits.append({'file':rec['file'],**result['independent_wealth_audit']});return rec
    for candidate in NEW_CANDIDATES:
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
    selected_fixed={};chosen=s1['selection']['selected']
    if chosen=='cash':
        r=ledger.replay(market,T1,T3,benchmark='cash',managed_cash=True)
        managed=save('main_selected_managed_cash',r)
        selected_fixed={cost:managed for cost in COSTS}
    else:
        selected_fixed={cost:next(x for x in comparisons[chosen] if x['cost']==cost and x['lag_days']==0 and not x['adverse_funding_5bps']) for cost in COSTS}
    wfa={}
    for cost in COSTS:
        for lag in (0,1,2):
            for adverse in (False,True):
                key=f'{cost}_lag{lag}_adverse{int(adverse)}';capital='10000';folds=[];fold_records=[]
                for year,start,end,selection in ((2024,T1,T2,s1),(2025,T2,T3,s2)):
                    chosen=selection['selection']['selected']
                    kw={'benchmark':'cash','managed_cash':True} if chosen=='cash' else {'candidate':chosen,'lag':lag,'prepared_signals':ledger.make_signals(market,chosen,end)}
                    previous=next(f for f in prior['walk_forward'][key]['folds'] if f['year']==year)
                    if previous['chosen']==chosen and previous['metrics']['initial_usdt']==capital:
                        path=Path(reference_root)/('futures-'+origin['batch']+'-evaluation')/previous['file']
                        r=read_result(path,previous['sha256'],previous['container_sha256'])
                        if r['start_ms']!=start or r['end_exclusive_ms']!=end or r['metrics']['initial_usdt']!=capital:raise ValueError('Reused WFA identity mismatch')
                        rec={**previous,'reused':True,'source_batch':origin['batch']};reused_folds.append(rec)
                    else:
                        r=ledger.replay(market,start,end,cost=cost,adverse_funding=adverse,initial_usdt=capital,**kw)
                        rec=save(f'wfa_{year}_{key}',r)
                    folds.append(r);fold_records.append({'year':year,'chosen':chosen,**rec});capital=r['metrics']['final_cash_usdt']
                    if r['status']!='COMPLETE':break
                wfa[key]={'folds':fold_records,**combine_folds(folds)}
                print('WFA '+symbol+' '+key,flush=True)
    out={'symbol':symbol,'comparisons':comparisons,'gates':gates,'benchmarks':benchmarks,'walk_forward':wfa,'new_results':records,'new_simulations':len(records),'main_selection':s1['selection'],'second_selection':s2['selection'],'daily_returns_for_diagnostics':curves,'audits':audits,'reused_reference_source':origin,'reused_wfa_folds':reused_folds,'main_selected_fixed':selected_fixed}
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
                r.update(operating_costs_included=True,compatible_asset_candidate_pairs=len(CANDIDATES),prior_search_corrected=False)
                output[symbol+'|'+cost+'|'+benchmark]=r
            panel=np.column_stack(panels)
            r=bootstrap_max_mean(panel,np.zeros(len(panel)),block=30,repeats=2000,seed=20261017)
            r.update(operating_costs_included=True,compatible_asset_candidate_pairs=panel.shape[1],prior_search_corrected=False,note='Shareddateblocks preserve crossasset dependence. All26matched candidates perasset included; prior50variant search and family/asset choices notfullycorrected. Reusedhistoricaldates; notprospective validation.')
            output['joint|'+cost+'|'+benchmark]=r
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-root',type=Path,required=True);p.add_argument('--freeze-sha256',required=True)
    p.add_argument('--stage',choices=['train1','train2','evaluate'],required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference-root',type=Path);p.add_argument('--train1',type=Path);p.add_argument('--selection1-sha256');p.add_argument('--train2',type=Path);p.add_argument('--selection2-sha256')
    a=p.parse_args();pin=verify_freeze(a.freeze_sha256)
    if a.output.exists():raise ValueError('New output directory required; preserve every attempt')
    if not pin['inputs'] or not set(pin['inputs'])<=set(assets.SYMBOLS):raise ValueError('No eligible frozen assets')
    a.output.mkdir(parents=True);write_new(a.output/'intent.json',{k:str(v) for k,v in vars(a).items()})
    try:
        s1=s2=None
        if a.stage!='train1':s1=read_selection(a.train1,a.selection1_sha256,pin,a.freeze_sha256,'train1')
        if a.stage=='evaluate':
            s2=read_selection(a.train2,a.selection2_sha256,pin,a.freeze_sha256,'train2')
            if s2['prior_selection_sha256']!=a.selection1_sha256:raise ValueError('Selection chain mismatch')
        with ProcessPoolExecutor(max_workers=min(3,len(pin['inputs']))) as pool:
            if a.stage in ('train1','train2'):
                values=list(pool.map(train_asset,[(str(a.data_root),str(a.output),s,pin,a.stage) for s in pin['inputs']]))
                result={'stage':a.stage,'freeze_sha256':a.freeze_sha256,'assets':{v['symbol']:v for v in values},'new_simulations':sum(v['new_simulations'] for v in values),'prior_selection_sha256':a.selection1_sha256,'evaluation_computed':False}
                write_new(a.output/'selection.json',result)
            else:
                values=list(pool.map(evaluate_asset,[(str(a.data_root),str(a.reference_root),str(a.output),s,pin,s1['assets'][s],s2['assets'][s]) for s in pin['inputs']]))
                result={'experiment':'024','freeze_sha256':a.freeze_sha256,'assets':{v['symbol']:v for v in values},'selection_hashes':[a.selection1_sha256,a.selection2_sha256],'new_simulations':sum(v['new_simulations'] for v in values),'new_unique_variants':20,'total_unique_variants':70}
                result['multiplicity']=multiplicity(result['assets'])
                write_new(a.output/'evaluation.json',result)
    except Exception as exc:
        write_new(a.output/'failure.json',{'type':type(exc).__name__,'message':str(exc)});raise


if __name__=='__main__':main()
