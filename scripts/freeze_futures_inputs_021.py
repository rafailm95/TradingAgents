"""Create final021 input pin after strict audit, before any strategy outcome."""
import argparse,hashlib,json,shutil,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from tradingagents import binance_assets_021 as a
from run_futures_assets_021 import load_market


def main():
 p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);args=p.parse_args();out=ROOT/'research/experiments/021';target=out/'engine-freeze.json'
 if target.exists():raise ValueError('Preserve original freeze')
 source=json.loads((out/'engine-source-freeze.json').read_bytes());summary=json.loads((args.data_root/'collection-summary.json').read_bytes());inputs={};excluded={}
 for r in summary['assets']:
  symbol=r['symbol'];root=args.data_root/symbol
  if r['status']=='COMPLETE':
   if a.sha(root/'normalized.json.gz')!=r['normalized_sha256'] or a.sha(root/'manifest.json')!=r['manifest_sha256']:raise ValueError('Input pin mismatch')
   inputs[symbol]={k:r[k] for k in ('normalized_sha256','manifest_sha256','audit')}
   load_market(args.data_root,symbol,{'inputs':inputs})
  else:
   excluded[symbol]={'reason':'Πραγματική αλλαγή funding σε 4 και 2 ώρες τον Νοέμβριο 2022· ο παγωμένος έλεγχος απαιτεί 8 ώρες. Διατηρούνται 4.458 πραγματικά γεγονότα, χωρίς προσομοίωση SOL.','raw_error':r['error'],'status':'EXCLUDED_BEFORE_PNL','verified_monthly_archives':r['verified_monthly_archives'],'verified_daily_archives':r['verified_daily_archives']}
  for name in ('complete.json','stopped.json','manifest.json','monthly-manifest.json','daily-recovery-plan.json'):
   if (root/name).exists():shutil.copyfile(root/name,out/(symbol+'-'+name))
 shutil.copyfile(args.data_root/'collection-summary.json',out/'collection-summary.json')
 for group in ('source_hashes','preserved_files'):
  for name,digest in source[group].items():
   if a.sha(ROOT/name)!=digest:raise ValueError('Earlier frozen file changed: '+name)
 extra=['scripts/freeze_futures_inputs_021.py','scripts/summarize_futures_inputs_021.py','scripts/audit_sol_candles_021.py','research/experiments/021/SOLUSDT-candle-audit.json','research/experiments/021/engine-source-freeze.json','research/experiments/021/input-coverage.json','research/experiments/021/sol-funding-observation.json']
 pin={**source,'stage':'EXACT_REAL_INPUTS_FROZEN_BEFORE_TRAINING','created_utc':datetime.now(timezone.utc).isoformat(),'source_commit':'a43e8d415b04d1c93ac68c3ba7902de199babbe9','source_hashes':{**source['source_hashes'],**{n:a.sha(ROOT/n) for n in extra}},'inputs':inputs,'excluded_assets':excluded,'actual_max_new_scenarios':125*len(inputs),'new_real_strategy_executions':0,'change_note':'No changes to frozen sources, strategy rules, windows, costs or gates. Ineligible assets excluded under original contract before PnL.'}
 target.write_text(json.dumps(pin,indent=2)+'\n');print(json.dumps({'freeze_sha256':a.sha(target),'eligible':list(inputs),'excluded':excluded,'max_scenarios':125*len(inputs)},indent=2))

if __name__=='__main__':main()
