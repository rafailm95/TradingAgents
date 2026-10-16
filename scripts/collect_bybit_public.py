"""Standalone stdlib collector for Bybit Global public USDT perpetual data.
GET-only, no key, no orders, no account calls, no retries or alternate hosts.
Run from the repository or the provided portable bundle.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,sys,time,urllib.request,urllib.parse,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tradingagents.bybit_depth import analyze,instrument,response,funding_summary,dec

ENDPOINTS={'instrument':'/v5/market/instruments-info','ticker':'/v5/market/tickers',
           'funding':'/v5/market/funding/history','book':'/v5/market/orderbook'}
HOST='https://api.bybit.com'


def write(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Unexpected redirect; stopping')


class Collector:
    def __init__(self,out):self.out=out;self.records=[]
    def get(self,kind,symbol,**extra):
        url=HOST+ENDPOINTS[kind]+'?'+urllib.parse.urlencode({'category':'linear','symbol':symbol,**extra})
        rec={'url':url,'request_utc':datetime.now(timezone.utc).isoformat()}
        started=time.monotonic();index=len(self.records);self.records.append(rec)
        try:
            req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'TradingAgents-Public-Research/012'})
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as f:
                raw=f.read(15000001);rec['http_status']=f.status
                if len(raw)>15000000:raise ValueError('Response exceeds15MB')
            name=f'{index:04d}_{symbol}_{kind}.response';(self.out/name).write_bytes(raw)
            rec.update(raw_file=name,sha256=hashlib.sha256(raw).hexdigest())
            received=int(time.time()*1000);rec['received_ms']=received
            try:payload=json.loads(raw)
            except (ValueError,UnicodeError):raise ValueError('Non-JSON response; no market data accepted')
            response(payload,received)
            rec['accepted_api_response']=True
            return payload,received
        except Exception as exc:
            rec['error']=type(exc).__name__+': '+str(exc)
            raise
        finally:
            rec['response_utc']=datetime.now(timezone.utc).isoformat()
            rec['elapsed_seconds']=time.monotonic()-started
            write(self.out/'requests.json',self.records)


def collect(out,rounds=12,interval=10):
    out.mkdir(parents=True,exist_ok=False);c=Collector(out)
    manifest={'schema':'bybit_public_012_v1','host':HOST,'category':'linear','started_utc':datetime.now(timezone.utc).isoformat(),
      'capital_assumption_usdt':10000,'rounds_requested':rounds,'interval_seconds':interval,
      'status':'IN_PROGRESS','snapshots':[],'funding':{},'orders':0,'private_api_calls':0,
      'fee_bps_scenarios':[5.5,10],'account_fee_verified':False,
      'limit_note':'Snapshot diagnostics only; no funding-adjusted strategy result, no intrabar/liquidation model.'}
    metadata={}
    try:
        for symbol in ('BTCUSDT','ETHUSDT','LTCUSDT'):
            p,t=c.get('instrument',symbol);metadata[symbol]=instrument(p,symbol,t)
            p,t=c.get('funding',symbol,limit=200);manifest['funding'][symbol]=funding_summary(p,symbol,t)
        for i in range(rounds):
            for symbol in metadata:
                p,t=c.get('ticker',symbol);r=response(p,t)
                if r.get('category')!='linear' or len(r['list'])!=1 or r['list'][0]['symbol']!=symbol:
                    raise ValueError('Invalid ticker identity')
                ticker=r['list'][0]
                for key in ('markPrice','indexPrice'):dec(ticker[key],True)
                p,t=c.get('book',symbol,limit=1000)
                item={'round':i+1,'symbol':symbol,'received_ms':t,'ticker_received_ms':c.records[-2]['received_ms'],
                      'mark_price':ticker['markPrice'],'index_price':ticker['indexPrice'],
                      'current_funding_rate':ticker['fundingRate'],'next_funding_time':ticker['nextFundingTime'],
                      'open_interest':ticker.get('openInterest'),'open_interest_definition':'both sides per current API docs',
                      'scenarios':[]}
                for target in (1000,5000):
                    for fee in ('5.5','10'):
                        try:item['scenarios'].append(analyze(p,metadata[symbol],t,target,10000,fee))
                        except ValueError as e:item['scenarios'].append({'target_notional_usdt':target,'fee_bps':fee,'rejected':str(e)})
                # Book validity independent of whether the smallest scenario is executable.
                from tradingagents.bybit_depth import parse_book
                parse_book(p,symbol,t,metadata[symbol]['priceFilter']['tickSize'])
                manifest['snapshots'].append(item)
            write(out/'summary.json',manifest);print(f'Round {i+1}/{rounds} saved',flush=True)
            if i+1<rounds:time.sleep(interval)
        manifest['status']='COLLECTED_PUBLIC_SNAPSHOTS'
    except Exception as e:
        manifest.update(status='BLOCKED_OR_INVALID_DATA',error=type(e).__name__+': '+str(e))
        print(manifest['error'],flush=True)
    finally:
        manifest['completed_utc']=datetime.now(timezone.utc).isoformat()
        manifest['valid_snapshot_count']=len(manifest['snapshots'])
        manifest['unique_book_timestamps']=len({(s['symbol'],s['scenarios'][0].get('source_ts_ms')) for s in manifest['snapshots'] if 'source_ts_ms' in s['scenarios'][0]})
        manifest['actual_order_fills']=0
        write(out/'summary.json',manifest)
        with zipfile.ZipFile(out.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(out.iterdir()):z.write(p,p.name)
        print('Evidence: '+str(out.with_suffix('.zip').resolve()),flush=True)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('bybit_measurements_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')))
    p.add_argument('--rounds',type=int,default=12);p.add_argument('--interval',type=int,default=10)
    a=p.parse_args()
    if not 1<=a.rounds<=60 or not 2<=a.interval<=60:p.error('rounds1..60, interval2..60seconds')
    result=collect(a.output,a.rounds,a.interval)
    sys.exit(0 if result['status']=='COLLECTED_PUBLIC_SNAPSHOTS' else 2)
