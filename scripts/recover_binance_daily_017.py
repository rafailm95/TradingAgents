from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import sys,json,hashlib,zipfile,io
sys.path.insert(0,'scripts')
from collect_binance_archive_017 import fetch
import argparse
parser=argparse.ArgumentParser(description='Exact official daily recovery for017;no synthetic filling')
parser.add_argument('--raw-root',type=Path,required=True);args=parser.parse_args()
root=args.raw_root/'daily-repairs';root.mkdir(exist_ok=True)
days=['2022-10-01','2022-10-02','2023-02-23','2023-02-24']
def one(day):
 name=f'ETHUSDT-1h-{day}.zip'
 receipt=root/(name+'.receipt.json')
 if receipt.exists():
  old=json.loads(receipt.read_bytes())
  if old['status']!='VERIFIED' or hashlib.sha256((root/name).read_bytes()).hexdigest()!=old['sha256'] or hashlib.sha256((root/(name+'.CHECKSUM')).read_bytes()).hexdigest()!=old['checksum_sha256']:raise ValueError('Retained recoveryfailedorchanged;noautomaticretry')
  return old
 url='https://data.binance.vision/data/futures/um/daily/markPriceKlines/ETHUSDT/1h/'+name
 r={'day':day,'symbol':'ETHUSDT','kind':'markPriceKlines','url':url,'requested_utc':datetime.now(timezone.utc).isoformat()}
 try:
  raw=fetch(url,5_000_000);check=fetch(url+'.CHECKSUM',1024);digest=hashlib.sha256(raw).hexdigest()
  if check.decode().split()!=[digest,name]:raise ValueError('Published checksum mismatch')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.namelist()!=[name[:-4]+'.csv'] or z.testzip():raise ValueError('Bad ZIP')
  (root/name).write_bytes(raw);(root/(name+'.CHECKSUM')).write_bytes(check)
  r.update(status='VERIFIED',sha256=digest,checksum_sha256=hashlib.sha256(check).hexdigest(),bytes=len(raw),relative='daily-repairs/'+name)
 except Exception as e:r.update(status='FAILED',error=str(e))
 (root/(name+'.receipt.json')).write_text(json.dumps(r,indent=2)+'\n');return r
with ThreadPoolExecutor(max_workers=3) as pool:
 for r in pool.map(one,days):print(json.dumps(r),flush=True)
