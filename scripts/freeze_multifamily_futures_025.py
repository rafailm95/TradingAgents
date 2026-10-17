"""Freeze025 exact sources/tests/input contracts before real strategy outcomes."""
import argparse,hashlib,importlib.metadata,json,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tradingagents.multifamily_futures_025 import FAMILIES,NEW_CANDIDATES,CANDIDATES

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,ensure_ascii=False);f.write('\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();w=a.workspace;o=ROOT/'research/experiments/025';o.mkdir();now=datetime.now(timezone.utc).isoformat()
    rules=[
      ('RVI=sum10(sym4(C-O))/sum10(sym4(H-L));sym4 uses current/previous3 weights1,2,2,1 divided6. Signal=sym4(RVI). Zero range neutral0.','RVI crosses above signal AND C>SMA200.','RVI<signal OR C<SMA200.',20,'Normalized candle body relative to range; distinct from Heikin recursion and price-only momentum.','https://www.tradingview.com/support/solutions/43000591593-relative-vigor-index/'),
      ('DeMax=max(H-Hprev,0);DeMin=max(Lprev-L,0);DeM=SMA14(DeMax)/(SMA14(DeMax)+SMA14(DeMin));zero denominator neutral.5.','DeM crosses above.3 AND C>SMA200.','DeM>.7 OR C<SMA200.',10,'Asymmetric high/low changes, rather than RSI close changes or stochastic close position.','https://www.metatrader4.com/en/trading-platform/help/analytics/tech_indicators/demarker'),
      ('Mass=sum25(EMA9(H-L)/EMA9(EMA9(H-L)));zero denominator ratio1.','maxMass over previous20days>27 AND Mass_t<26.5<=Mass_t-1 AND C>Cprev AND C>SMA200.','C<SMA20 OR C<SMA200.',20,'Range-expansion reversal with explicit20day bulge expiry and bullish recovery hypothesis. Source is non-directional; our uptrend filter is an unvalidated adaptation.','https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/mass-index'),
      ('DD_t=100*(C_t/maxC14_t-1);Ulcer=sqrt(SMA14(DD^2)).','Ulcer_t<5<=Ulcer_t-1 AND C>SMA200.','Ulcer>10 OR C<SMA200.',20,'Depth-and-duration downside recovery, distinct from variance level and breakout.','https://www.tradingview.com/support/solutions/43000773115-ulcer-index/'),
      ('TRIX=100*one-day pctchange of EMA18(EMA18(EMA18(C)));signalEMA9(TRIX).','TRIX crosses above signal whileTRIX<0 AND C>SMA200.','TRIX<signal OR C<SMA200.',20,'Triple-filter rate-of-change rebound, distinct formula but likely correlated with MACD/TSI; not independent evidence.','https://www.tradingview.com/support/solutions/43000502331-trix/'),
      ('T=+1 if H+L+C increases else-1;initialT=-1. dm=H-L;cm0=dm0;cm=cmPrev+dm ifsameT else dmPrev+dm. VF=V*2*(dm/cm-1)*T*100;cm0 =>VF0. KO=EMA34(VF)-EMA55(VF);signalEMA13(KO).','KO crosses above signal AND C>SMA200.','KO<signal OR C<SMA200.',20,'Range-run volume-force oscillator. Exact signed formula as printed in cited documentation; no claim of equivalence to platforms using absolute-value VF conventions.','https://www.tradingview.com/support/solutions/43000589157-klinger-oscillator/'),
      ('NVI0=1000;add100*(C/Cprev-1) only whenV<Vprev, else unchanged;signalEMA255(NVI). Explicit additive-percent convention, not compoundedNVI.','NVI crosses above signal AND C>SMA200.','NVI<signal OR C<SMA200.',20,'Conditional low-volume-day accumulation, distinct from all-dayOBV and VWMA. Original indicator use in equityindices does not validate crypto.','https://www.tradingview.com/support/solutions/43000773005-negative-volume-index-nvi/'),
      ('UTC weekday of fullyclosed signalday. Friday=4,Sunday=6.','Friday AND C>SMA200.','Sunday OR C<SMA200.',10,'Fixed calendar participation hypothesis prompted by observed weekday/weekend activity differences. Source supports activity seasonality only, not positive weekend returns. Lag delays BOTH entry and exit, so lag1/2 deliberately shifts weekend exposure into weekdays.','https://www.kaiko.com/resources/btc-etfs-impact-on-spot-market-structure?page=4'),
      ('b_t=10000*(lastclosedhour tradeClose/markClose-1);z=(b-current previous60daymean)/previous60day sampleSD(ddof1);zeroSD =>NaN.','z<-2 AND C>SMA200.','z>=0 OR C<SMA200.',10,'Long trade-price discount relative to mark; mark is valuation reference, not tradable hedge or assured fair value/convergence. No basis-arbitrage claim.','https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data'),
      ('Hourly r=ln(tradeClose/previoushourClose);veryfirsthour uses its ownopen. DailyRV=sum24(r^2),downRV=sum24(r^2 forr<0). q=sum14(downRV)/sum14(RV);zeroRV neutral.5.','q_t<.5<=q_t-1 AND maximumq overprevious14days>.6 AND C>SMA200.','q>.6 OR C<SMA200.',10,'Recovery in downside fraction of intraday squared moves; research adaptation of realised semivariance. Hourly observations are coarse, not tick-level estimator or proven alpha.','https://shephard.scholars.harvard.edu/publications/measuring-downside-risk-realised-semivariance')]
    families=[]
    for name,row in zip(FAMILIES,rules):
        formula,entry,leave,hold,rationale,url=row
        families.append({'id':name,'indicator':formula,'entry_after_closed_day':entry,'exit_after_closed_day':leave,'max_actual_holding_days':hold,'distinct_rationale':rationale,'source':url,'source_retrieved_utc_date':'2026-10-17','source_scope':'Primary software documentation or original data/research provider. Exact strategy thresholds/filters are preregistered hypotheses; sources do not establish profitability.'})
    protocol=json.loads((ROOT/'docs/MULTIFAMILY_FUTURES_024.json').read_bytes())
    protocol.update(experiment='025',families=families,new_candidates=NEW_CANDIDATES,all_compatible_candidates_per_asset=CANDIDATES,total_unique_variants_after_completion=90,total_families_after_completion=45)
    protocol['authorization']['interpretation']='Latest repeated explicit10to30newstrategy request authorizes one new batch10distinct families*2existing sizings=20variants, beyond completed024. Olderonefamily/max6cap superseded onlyforthisbatch. Allpublication/preservation/financialcontrols remain.'
    protocol['selection']='All46compatible candidates;52oldtrainresults reusedperasset/stage from024. Bothcosts nominalfunding lag0 COMPLETE,net>0,DD<=35%,>=10signal/timeexits,auditPASS. Rankstressannualizedreturn/max(stressDD,1%),lexicographicIDtie;elsecash. Publishselection1 beforetrain2,selection2 beforeevaluation. No PnL-driven changes.'
    protocol['matrix'].update(all_compatible_asset_candidate_pairs=138,reused_old_training_results=312,reused_old_evaluation_scenarios=936)
    protocol['multiplicity']='All46perasset/joint138matched731dailyreturns vsidlecash/matchedhold50,opex included;30daycircularblocks,2000resamples,seed20261017. Prior70variants/35families/8941knownexecutions and family/asset choices notfullycorrected. Reused dates and correlated variants notindependent discoveries; oldETH/spotincompatiblehistoriesdisclosed separately.'
    protocol['preserve']='Every prior trackedfile except mutable registry;013/014/023/024freezes andprospectivepins unchanged;noPHOENIX/main/upstream/PRs.'
    protocol['hourly_feature_timing']='Allfeatures consumeonlyfirstdays*24completehours matching requestedcloseddayprefix. Basis uses23:00hourclose;semivariance usesclose-to-closehours. No futurehours, missingforwardfills or fabricatedOHLCpaths. Allfills remain genuine trade-price hourlyopen withfrozenfees/slippage.'
    protocol['source_convention_notes']='MassIndex uses single/doubleEMA as explicitStockCharts formula, resolving conflicting printedTradingView equation. Klinger follows exactsignedVF printedbyTradingView, NVI follows additivepercent convention; neither silently switched afterresults. Calendar source is2024andtherefore reinforces non-pristine historical hypothesisdesign limitation.'
    write(ROOT/'docs/MULTIFAMILY_FUTURES_025.json',protocol)
    logs=[]
    for source,name,n in [('research025-tests-attempt1.log','signals-preflight-attempt1.log',114),('research025-runner-tests-attempt2.log','runner-preflight-attempt2.log',3)]:
        raw=(w/source).read_bytes()
        if (str(n)+' passed').encode() not in raw or b'FAILED' in raw:raise ValueError('Preflight incomplete/failure: preserve and correct')
        (o/name).write_bytes(raw);logs.append({'path':str((o/name).relative_to(ROOT)),'sha256':sha(o/name),'passed':n})
    write(o/'preflight.json',{'new_tests':117,'passed':117,'initial_failures':[{'tests_failed':2,'correction':'research/corrections/025-preflight/correction.json','phase':'Synthetic only; before real PnL and freeze'}],'logs':logs,'commands':['python -m pytest --noconftest -q tests/test_multifamily_futures_025.py','python -m pytest --noconftest -q tests/test_multifamily_runner_025.py'],'fixtures':'Synthetic only.10familyprefix/futurehourmutation,independentmath/UTCcalendar,20new*3lagaccounting,all26old dispatchidentity,46candidate selection,138pairbootstrap,fullrunneroldreuse/changedWFAcapital. No realstrategyPnL.'})
    old=json.loads((ROOT/'research/experiments/024/freeze.json').read_bytes());inputs=old['inputs'];refs={}
    e=json.loads((ROOT/'research/experiments/024/evaluation.json').read_bytes())
    for symbol in inputs:
        for fn,key in [('normalized.json.gz','normalized_sha256'),('manifest.json','manifest_sha256')]:
            if sha(w/'futures-023-base'/symbol/fn)!=inputs[symbol][key]:raise ValueError('Frozen input changed')
        for row in e['assets'][symbol]['walk_forward'].values():
            for r in row['folds']:
                rel='futures-024-evaluation/'+r['file']
                if sha(w/rel)!=r['container_sha256']:raise ValueError('Reference changed')
                refs[rel]={'container_sha256':r['container_sha256'],'decoded_sha256':r['sha256'],'durable_artifact_receipts':'research/experiments/024/artifact_receipts.json'}
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines();preserved={p:sha(ROOT/p) for p in tracked if p!='research/registry.json'}
    sources=['tradingagents/multifamily_futures_025.py','scripts/run_multifamily_futures_025.py','scripts/freeze_multifamily_futures_025.py','tests/test_multifamily_futures_025.py','tests/test_multifamily_runner_025.py','docs/MULTIFAMILY_FUTURES_025.json','research/experiments/025/preflight.json']
    sources += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'research/corrections/025-preflight').glob('*'))]
    freeze={'experiment':'025','created_utc':now,'starting_remote_head':'6f23b8c0726ee9450535ac888db78921d85b7595','source_hashes':{p:sha(ROOT/p) for p in sources},'preserved_files':preserved,'inputs':inputs,'reference_files':refs,'runtime':{n:importlib.metadata.version(n) for n in ('numpy','pandas','python-dotenv','pytest')},'python':'3.12','data_source_receipts':['research/experiments/021/artifact_receipts.json','research/experiments/022/artifact_receipts.json'],'prior_design_executions':8934,'prior_integrity_replays':7,'new_real_strategy_pnl_computed':False,'new_variants':20,'families':10,'maximum_new_executions':1035}
    write(o/'freeze.json',freeze)
    path=ROOT/'research/registry.json';reg=json.loads(path.read_bytes())
    if reg['active_experiment'] is not None or any(x['id']=='025' for x in reg['completed']):raise ValueError('Registry conflict')
    reg.update(updated_utc=now,active_experiment={'id':'025','attempt':'025-initial','status':'PREREGISTERED_AWAITING_REMOTE_CHECKPOINT','new_families':10,'new_variants':20,'planned_total_variants':90,'protocol':'docs/MULTIFAMILY_FUTURES_025.json','freeze_sha256':sha(o/'freeze.json'),'maximum_new_executions':1035,'new_historical_simulations':0,'software_tests':117,'latest_user_scope_override':'Latest2026-10-17request10to30morestrategies;onebatch20variants/10families.'},next_action='Publish025freeze beforePnL;train1,publishselection1;train2,publishselection2;evaluateall20newvariants/all3assets/all12cases. Reuse26compatibleoldresults unchanged.013priorityifpacketarrives;023remainsblocked.')
    path.write_text(json.dumps(reg,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'freeze_sha256':sha(o/'freeze.json'),'preserved_files':len(preserved),'reference_files':len(refs),'inputs':list(inputs),'tests':117}))
if __name__=='__main__':main()
