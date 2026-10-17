"""Audit captured SOLcandles separately; never accept changed funding or run PnL."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tradingagents import binance_assets_021 as a


def main():
 p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 if args.output.exists():raise ValueError('Preserve previous diagnostic')
 root=args.data_root/'SOLUSDT';m=json.loads((root/'manifest.json').read_bytes());repairs={};added=overlap=0;counts={}
 for r in m['supplemental_daily']:
  name=f"SOLUSDT-1h-{r['day']}.zip";path=root/r['relative'];url=f"https://data.binance.vision/data/futures/um/daily/{r['kind']}/SOLUSDT/1h/{name}"
  if r['url']!=url or r['relative']!=f"daily-repairs/{r['kind']}/{name}":raise ValueError('Daily provenance')
  if a.sha(path)!=r['sha256'] or a.sha(str(path)+'.CHECKSUM')!=r['checksum_sha256'] or Path(str(path)+'.CHECKSUM').read_text().split()!=[r['sha256'],name]:raise ValueError('Daily hash')
  day=a.utc_ms(r['day']+'T00:00:00Z');repairs.setdefault((r['kind'],r['day'][:7]),[]).append((day,a.csv_rows(path.read_bytes(),name[:-4]+'.csv')))
 for kind in ('klines','markPriceKlines'):
  combined=[]
  for r in sorted([r for r in m['files'] if r['kind']==kind],key=lambda r:r['period']):
   path=root/r['relative']
   if a.sha(path)!=r['sha256']:raise ValueError('Monthly hash')
   rows=a.csv_rows(path.read_bytes(),path.name[:-4]+'.csv');start,end=a.month_bounds(r['period'])
   if (kind,r['period']) in repairs:
    bars,d=a.recover_bars(rows,repairs[(kind,r['period'])],kind=kind,start=start,end=end);added+=d['added_hours'];overlap+=d['matched_overlap_hours']
   else:bars=a.parse_bars(rows,kind=kind,start=start,end=end)
   combined.extend(bars)
  if [int(r[0]) for r in combined]!=list(range(a.START,a.END,a.HOUR)):raise ValueError('Incomplete combined grid')
  counts[kind]=len(combined)
 out={'status':'CANDLES_COMPLETE_FUNDING_SCHEDULE_UNVALIDATED','symbol':'SOLUSDT','counts':counts,'recovered_real_hours':added,'matched_overlap_hours':overlap,'manifest_sha256':a.sha(root/'manifest.json'),'raw_funding_events_captured':4458,'strict_funding_auditor_still_failed':True,'strategy_pnl_computed':False,'note':'Additionalread-only candleaudit,not correctionoforiginalfundingcontract. No funding rates fabricated/aggregated. NoSOLsimulationauthorizedbythisdiagnostic.'}
 args.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
