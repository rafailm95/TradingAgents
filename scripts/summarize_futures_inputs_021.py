"""Read-only full raw coverage diagnostic, including excluded assets. No PnL."""
import argparse,collections,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tradingagents import binance_assets_021 as a


def main():
 p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();out={}
 if args.output.exists():raise ValueError('Preserve existing diagnostic')
 for symbol in a.SYMBOLS:
  root=args.data_root/symbol;manifest_path=root/'manifest.json'
  if not manifest_path.exists():manifest_path=root/'monthly-manifest.json'
  if not manifest_path.exists():out[symbol]={'status':'INCOMPLETE_COLLECTION','stop':json.loads((root/'stopped.json').read_bytes())};continue
  manifest=json.loads(manifest_path.read_bytes());counts=collections.Counter();intervals=collections.Counter();gaps=[];changes=[];errors=[];prev=None;fund=[]
  for item in sorted(manifest['files'],key=lambda x:(x['kind'],x['period'])):
   path=root/item['relative'];raw=path.read_bytes()
   if a.sha(path)!=item['sha256']:raise ValueError('Raw SHA mismatch')
   if a.sha(str(path)+'.CHECKSUM')!=item['checksum_sha256']:raise ValueError('Checksum SHA mismatch')
   if Path(str(path)+'.CHECKSUM').read_text().split()!=[item['sha256'],path.name]:raise ValueError('Published checksum mismatch')
   rows=a.csv_rows(raw,path.name[:-4]+'.csv');start,end=a.month_bounds(item['period']);kind=item['kind']
   if kind=='fundingRate':
    try:a.parse_funding(rows,start=start,end=end)
    except ValueError as e:errors.append({'period':item['period'],'kind':kind,'strict_auditor_failure':str(e)})
    for r in rows:
     if len(r)!=3:raise ValueError('Malformed funding shape')
     ts=a.integer(r[0]);interval=a.integer(r[1]);rate=a.inherited.decimal(r[2]);slot=ts//a.HOUR*a.HOUR
     if not start<=ts<end or not 0<=ts-slot<60000:raise ValueError('Out-of-window/jitter funding')
     intervals[interval]+=1;fund.append(slot)
     if prev is None or interval!=prev[1]:changes.append({'actual_utc':datetime.fromtimestamp(ts/1000,timezone.utc).isoformat(),'interval_hours_column':interval,'gap_from_prior_event_hours':None if prev is None else (slot-prev[0])/a.HOUR})
     prev=(slot,interval)
    counts[kind]+=len(rows)
   else:
    parsed=a.parse_bars(rows,kind=kind,start=start,end=end,allow_gaps=True);counts[kind]+=len(parsed)
    missing=sorted(set(range(start,end,a.HOUR))-{int(r[0]) for r in parsed})
    if missing:gaps.append({'kind':kind,'period':item['period'],'missing_hours':len(missing),'utc_days':sorted({datetime.fromtimestamp(t/1000,timezone.utc).date().isoformat() for t in missing})})
  if fund!=sorted(set(fund)):raise ValueError('Duplicate/unordered funding')
  status='COMPLETE' if (root/'complete.json').exists() else 'EXCLUDED_BEFORE_PNL'
  out[symbol]={'status':status,'monthly_archives_verified':len(manifest['files']),'monthly_row_counts':dict(counts),'raw_funding_interval_hours_counts':dict(intervals),'interval_changes':changes,'monthly_candle_gaps':gaps,'strict_funding_failures':errors,'completed_audit':json.loads((root/'audit.json').read_bytes()) if (root/'audit.json').exists() else None,'stop':json.loads((root/'stopped.json').read_bytes()) if (root/'stopped.json').exists() else None,'manifest_sha256':a.sha(manifest_path),'strategy_pnl_computed':False}
 args.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({s:{k:v for k,v in d.items() if k in ('status','monthly_row_counts','raw_funding_interval_hours_counts','stop')} for s,d in out.items()},indent=2))

if __name__=='__main__':main()
