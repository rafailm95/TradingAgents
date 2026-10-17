"""Bounded official BTC/SOL/XRP hourly archive collection. Public GET only; no PnL."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import gzip,hashlib,io,json,os,re,sys,zipfile
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tradingagents import futures_extension_023 as b
KINDS=('klines','markPriceKlines','fundingRate')
BASE='https://data.binance.vision/data/futures/um/'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')


def specs(symbol):
    if symbol not in b.SYMBOLS:raise ValueError('Unauthorized asset')
    for year in (2026,):
        for month in range(1,10):
            period=f'{year}-{month:02d}'
            for kind in KINDS:
                name=f'{symbol}-fundingRate-{period}.zip' if kind=='fundingRate' else f'{symbol}-1h-{period}.zip'
                relative=f'{kind}/{symbol}/'+('' if kind=='fundingRate' else '1h/')+name
                yield {'symbol':symbol,'kind':kind,'period':period,'relative':relative,'url':BASE+'monthly/'+relative}


def fetch(url,limit,root,label):
    status=None;headers={};error=None
    try:
        with build_opener(NoRedirect).open(Request(url,headers={'User-Agent':'TradingAgents-Research/1.0'}),timeout=30) as r:
            status=r.status;headers=dict(r.headers);raw=r.read(limit+1)
    except HTTPError as e:status=e.code;headers=dict(e.headers);raw=e.read(min(limit,1000000));error=str(e)
    except Exception as e:raw=b'';error=type(e).__name__+': '+str(e)
    if error or status!=200 or len(raw)>limit or raw.lstrip().lower().startswith((b'<!doctype html',b'<html')):
        folder=root/'failed-responses';folder.mkdir(exist_ok=True)
        (folder/(label+'.response')).write_bytes(raw)
        write(folder/(label+'.json'),{'url':url,'status':status,'error':error,'headers':headers,'sha256':sha(raw),'bytes':len(raw),'received_utc':datetime.now(timezone.utc).isoformat()})
        raise ValueError('Public request failed; no retry: '+url+' status='+str(status)+' '+str(error))
    return raw


def one(root,item,probes):
    target=root/item['relative'];target.parent.mkdir(parents=True,exist_ok=True)
    receipt=target.with_suffix('.receipt.json');checksum=Path(str(target)+'.CHECKSUM')
    if receipt.exists():
        r=json.loads(receipt.read_bytes())
        if r['url']!=item['url'] or sha(target.read_bytes())!=r['sha256'] or sha(checksum.read_bytes())!=r['checksum_sha256']:raise ValueError('Cache mismatch')
        return r
    if target.exists() or checksum.exists():raise ValueError('Unjournaled partial archive')
    label=item['symbol']+'-'+item['kind']+'-'+item.get('period',item.get('day'))
    if item['url'] in probes:
        p=probes[item['url']];raw=Path(p['path']).read_bytes()
        if sha(raw)!=p['sha256']:raise ValueError('Probe pin mismatch')
    else:raw=fetch(item['url'],5_000_000,root,label)
    try:
        check=fetch(item['url']+'.CHECKSUM',1024,root,label+'-checksum')
        if check.decode().split()!=[sha(raw),target.name]:raise ValueError('Published checksum mismatch')
    except Exception:
        folder=root/'unverified';folder.mkdir(exist_ok=True)
        (folder/(label+'.response')).write_bytes(raw)
        write(folder/(label+'.json'),{'url':item['url'],'sha256':sha(raw),'bytes':len(raw),'not_accepted':True})
        raise
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.infolist())!=1 or z.infolist()[0].filename!=target.name[:-4]+'.csv' or z.infolist()[0].file_size>15_000_000 or z.testzip():raise ValueError('Archive structure/CRC')
    with target.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    with checksum.open('xb') as f:f.write(check);f.flush();os.fsync(f.fileno())
    saved={**item,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'sha256':sha(raw),'checksum_sha256':sha(check),'bytes':len(raw),'published_checksum_verified':True,'probe_reused':item['url'] in probes}
    write(receipt,saved);return saved


def repair_days(rows,start,end):
    parsed=b.parse_bars(rows,kind='klines',start=start,end=end,allow_gaps=True)
    missing=sorted(set(range(start,end,b.HOUR))-{int(r[0]) for r in parsed})
    days=sorted({t//b.DAY*b.DAY for t in missing})
    # For every missing day also inspect one adjacent day in the same month.
    selected=set(days)
    for day in days:selected.add(day-b.DAY if day>start else day+b.DAY)
    return days,sorted(selected)


def collect_symbol(root,symbol,probes):
    if root.exists():raise ValueError('New output directory required; no automatic failed retry')
    root.mkdir(parents=True);files=[];supplements=[]
    write(root/'intent.json',{'symbol':symbol,'start':'2026-01-01','end_exclusive':'2026-10-01','maximum_monthly_archives':27,'maximum_missing_candle_days':10,'strategy_pnl_computed':False})
    try:
        for item in specs(symbol):
            files.append(one(root,item,probes))
            if len(files)%9==0:print(symbol+' verified '+str(len(files))+'/27',flush=True)
        manifest={'schema':'binance023_public_archive_v1','venue':'Binance USD-M perpetual','symbols':[symbol],'files':files,'archives':len(files),'strategy_pnl_computed':False}
        write(root/'monthly-manifest.json',manifest)
        plans=[];missing_count=0
        for item in files:
            if item['kind']=='fundingRate':continue
            a,z=b.month_bounds(item['period']);name=Path(item['relative']).name
            rows=b.csv_rows((root/item['relative']).read_bytes(),name[:-4]+'.csv')
            missing,days=repair_days(rows,a,z);missing_count+=len(missing)
            for day in days:plans.append((item['kind'],day))
        write(root/'daily-recovery-plan.json',{'missing_kind_days':missing_count,'daily_kind_days':plans,'rule':'Missing UTCdays plus previousday inside month, otherwise nextday. Exact overlap required; never replace conflicting observations.'})
        if missing_count>10:raise ValueError('Exceeds frozen10missing candle-kind-days per asset')
        for kind,day in sorted(set(plans)):
            daystr=datetime.fromtimestamp(day/1000,timezone.utc).strftime('%Y-%m-%d');name=f'{symbol}-1h-{daystr}.zip'
            item={'symbol':symbol,'kind':kind,'day':daystr,'relative':f'daily-repairs/{kind}/{name}','url':BASE+f'daily/{kind}/{symbol}/1h/{name}','status':'VERIFIED'}
            supplements.append(one(root,item,probes))
        manifest['supplemental_daily']=supplements;write(root/'manifest.json',manifest)
        digest=b.sha(root/'manifest.json');data,audit=b.audit_raw(root,digest);write(root/'audit.json',audit)
        raw=gzip.compress(json.dumps({'schema':'binance023_extension_v1','audit':audit,'datasets':data},separators=(',',':'),allow_nan=False).encode(),mtime=0)
        path=root/'normalized.json.gz'
        with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        result={'symbol':symbol,'status':'COMPLETE','manifest_sha256':digest,'normalized_sha256':sha(raw),'normalized_bytes':len(raw),'audit':audit,'new_strategy_simulations':0}
        write(root/'complete.json',result);return result
    except Exception as exc:
        r={'symbol':symbol,'status':'BLOCKED_OR_INCOMPLETE','error':type(exc).__name__+': '+str(exc),'verified_monthly_archives':len(files),'verified_daily_archives':len(supplements),'new_strategy_simulations':0}
        write(root/'stopped.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--collection-freeze-sha256',required=True);a=p.parse_args()
    freeze=ROOT/'research/experiments/023/collection-freeze.json'
    if b.sha(freeze)!=a.collection_freeze_sha256:raise ValueError('Collection freeze external hash mismatch')
    pin=json.loads(freeze.read_bytes())
    for path,digest in pin['source_hashes'].items():
        if b.sha(ROOT/path)!=digest:raise ValueError('Frozen source changed')
    if a.output.exists():raise ValueError('New collection root required')
    a.output.mkdir(parents=True);probes={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda s:collect_symbol(a.output/s,s,probes),b.SYMBOLS))
    write(a.output/'collection-summary.json',{'assets':results,'new_strategy_simulations':0,'no_retries':True})
    print(json.dumps(results,indent=2),flush=True)


if __name__=='__main__':main()
