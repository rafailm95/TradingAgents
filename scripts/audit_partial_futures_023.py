"""Offline audit of preserved partial023 collection; never computes PnL or fills gaps."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tradingagents import futures_extension_023 as b

def audit(root):
    root=Path(root);assets={}
    for symbol in b.SYMBOLS:
        folder=root/symbol;records=[];counts={k:0 for k in ('trade_hours','mark_hours','funding_events')};gaps=[];fund_errors=[];times={k:[] for k in counts}
        for receipt in sorted(folder.rglob('*.receipt.json')):
            r=json.loads(receipt.read_bytes());path=folder/r['relative'];check=Path(str(path)+'.CHECKSUM')
            if b.sha(path)!=r['sha256'] or b.sha(check)!=r['checksum_sha256'] or check.read_text().split()!=[r['sha256'],path.name]:raise ValueError('Archived source integrity failure')
            rows=b.csv_rows(path.read_bytes(),path.name[:-4]+'.csv');a,e=b.month_bounds(r['period']);k=r['kind']
            if k=='fundingRate':
                counts['funding_events']+=len(rows);times['funding_events'] += [int(x[0]) for x in rows]
                try:b.parse_funding(rows,start=a,end=e)
                except ValueError as exc:fund_errors.append({'period':r['period'],'reason':str(exc)})
            else:
                parsed=b.parse_bars(rows,kind=k,start=a,end=e,allow_gaps=True);key='trade_hours' if k=='klines' else 'mark_hours'
                counts[key]+=len(parsed);times[key]+=[int(x[0]) for x in parsed]
                missing=sorted(set(range(a,e,b.HOUR))-{int(x[0]) for x in parsed})
                if missing:gaps.append({'period':r['period'],'kind':k,'missing_hours':missing})
            records.append({**r,'rows':len(rows),'receipt_sha256':b.sha(receipt)})
        failure=json.loads((folder/'stopped.json').read_bytes())
        assets[symbol]={'status':'INELIGIBLE_INCOMPLETE_FROZEN_WINDOW','verified_archives':len(records),'observed_rows':counts,'expected_full_rows':{'trade_hours':6552,'mark_hours':6552,'funding_events':819},'coverage_fraction':{k:counts[k]/(819 if k=='funding_events' else 6552) for k in counts},'source_time_bounds_ms':{k:[min(v),max(v)] if v else None for k,v in times.items()},'missing_within_downloaded_candle_months':gaps,'funding_schedule_errors_in_available_months':fund_errors,'failure':failure,'verified_receipts':records,'strategy_simulations':0}
    return {'experiment':'023','status':'BLOCKED_DATA_NO_STRATEGY_OUTCOMES','assets':assets,'verified_archives':sum(a['verified_archives'] for a in assets.values()),'new_strategy_simulations':0,'data_eligibility_passes':0,'data_eligibility_failures':3,'strategy_passes':None,'strategy_failures':None,'shortened_window_tested':False,'network_retries':0,'no_interpolation':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=audit(a.input)
    with a.output.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps({s:{k:v[k] for k in ('verified_archives','observed_rows','coverage_fraction','funding_schedule_errors_in_available_months','missing_within_downloaded_candle_months')} for s,v in value['assets'].items()},indent=2))
if __name__=='__main__':main()
