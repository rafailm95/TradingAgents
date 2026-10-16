"""Download public Binance USD-M archives+published checksums, no account/API.
Fixed2022..2025coverage. Verified cache resumable, no retries on blocked data.
"""
import argparse,hashlib,json,zipfile,io,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
SYMBOLS=('BTCUSDT','ETHUSDT','LTCUSDT')
KINDS=('klines','markPriceKlines','fundingRate')
BASE='https://data.binance.vision/data/futures/um/monthly/'
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def digest(data):return hashlib.sha256(data).hexdigest()
def specs():
    for symbol in SYMBOLS:
        for year in range(2022,2026):
            for month in range(1,13):
                period=f'{year}-{month:02d}'
                for kind in KINDS:
                    name=f'{symbol}-fundingRate-{period}.zip' if kind=='fundingRate' else f'{symbol}-1h-{period}.zip'
                    relative=f'{kind}/{symbol}/'+('' if kind=='fundingRate' else '1h/')+name
                    yield {'symbol':symbol,'kind':kind,'period':period,'relative':relative,'url':BASE+relative}

def fetch(url,limit):
    try:
        with build_opener(NoRedirect).open(Request(url,headers={'User-Agent':'TradingAgents-Research/1.0'}),timeout=30) as response:
            if response.status != 200:raise ValueError('Non200response')
            raw=response.read(limit+1)
            if len(raw)>limit:raise ValueError('Oversized archive response')
            return raw
    except Exception as error:raise RuntimeError(url+' :: '+str(error)) from error

def one(root,item):
    folder=root/item['relative'];folder.parent.mkdir(parents=True,exist_ok=True)
    receipt=folder.with_suffix('.receipt.json');check=Path(str(folder)+'.CHECKSUM')
    if receipt.exists():
        saved=json.loads(receipt.read_bytes())
        if saved['url']!=item['url'] or digest(folder.read_bytes())!=saved['sha256'] or digest(check.read_bytes())!=saved['checksum_sha256']:raise ValueError('Existing cache mismatch')
        return saved
    if folder.exists() or check.exists():raise ValueError('Unjournaled partial download; preserve and review')
    raw=fetch(item['url'],5_000_000);checksum=fetch(item['url']+'.CHECKSUM',1024)
    match=re.fullmatch(rb'([0-9a-f]{64})\s+([^\r\n]+)\r?\n?',checksum)
    if not match or match[1].decode()!=digest(raw) or match[2].decode()!=folder.name:raise ValueError('Published checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.infolist())!=1 or z.infolist()[0].filename!=folder.name[:-4]+'.csv' or z.infolist()[0].file_size>15_000_000 or z.testzip():raise ValueError('Invalid archive entries or CRC')
    folder.write_bytes(raw);check.write_bytes(checksum)
    saved={**item,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'sha256':digest(raw),'checksum_sha256':digest(checksum),'bytes':len(raw),'published_checksum_verified':True}
    receipt.write_text(json.dumps(saved,indent=2)+'\n');return saved

def run(root,symbols=SYMBOLS):
    root.mkdir(parents=True,exist_ok=True)
    if (root/'stopped.json').exists() or (root/'coverage-stop.json').exists():raise ValueError('Stopped attempt is retained; no automatic retry')
    items=[item for item in specs() if item['symbol'] in symbols];out=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending={pool.submit(one,root,item):item for item in items}
        try:
            for future in as_completed(pending):
                out.append(future.result())
                if len(out)%30==0:print(f'CHECKSUM_VERIFIED {len(out)}/{len(items)}',flush=True)
        except Exception as e:
            failed_item=pending[future]
            for pending_future in pending:pending_future.cancel()
            (root/'stopped.json').write_text(json.dumps({'error':str(e),'time_utc':datetime.now(timezone.utc).isoformat(),'completed_before_error':len(out),'failed_item':failed_item}))
            raise
    manifest={'schema':'binance017_public_archive_v1','venue':'Binance USD-M perpetual','start_utc':'2022-01-01T00:00:00Z','end_exclusive_utc':'2026-01-01T00:00:00Z','downloaded_utc':datetime.now(timezone.utc).isoformat(),'files':sorted(out,key=lambda r:r['relative']),'archives':len(out),'symbols':list(symbols),'raw_bytes':sum(r['bytes'] for r in out),'real_orders':0}
    target=root/'manifest.json'
    if target.exists():raise ValueError('Completed manifest exists; no overwrite')
    target.write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'status':'COMPLETE','archives':len(out),'manifest_sha256':digest(target.read_bytes())}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--symbols',nargs='+',choices=SYMBOLS,default=SYMBOLS);a=p.parse_args();run(a.output,tuple(a.symbols))
