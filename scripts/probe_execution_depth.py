"""One public snapshot per allowed asset; hypothetical cost diagnostics only."""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import sys
from urllib.request import Request,urlopen
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from tradingagents.execution_depth import analyze

def capture(product,output,opener=urlopen):
    evidence={}
    for kind,suffix in (('product',''),('book','/book?level=2')):
        endpoint='https://api.exchange.coinbase.com/products/'+product+suffix
        started=datetime.now(timezone.utc)
        with opener(Request(endpoint,headers={'User-Agent':'TradingAgents-depth-research/1'}),timeout=15) as response:
            if response.status!=200 or response.geturl()!=endpoint:raise ValueError('Unexpected response or redirect')
            raw=response.read(15_000_001)
        received=datetime.now(timezone.utc)
        if len(raw)>15_000_000:raise ValueError('Oversized response')
        (output/(kind+'.json')).write_bytes(raw)
        evidence[kind]={'url':endpoint,'requested_at_utc':started.isoformat(),'received_at_utc':received.isoformat(),'sha256':hashlib.sha256(raw).hexdigest()}
        (output/'requests.json').write_text(json.dumps(evidence,indent=2))
        if (received-started).total_seconds()>15:raise ValueError('Slow response')
    spec=json.loads((output/'product.json').read_text());book=json.loads((output/'book.json').read_text())
    if spec.get('id')!=product:raise ValueError('Product mismatch')
    stamp=datetime.fromisoformat(book['time'].replace('Z','+00:00'))
    if stamp.tzinfo is None or not -5<=(received-stamp).total_seconds()<=30:raise ValueError('Missing or stale exchange book time')
    return {'product':product,'sequence':book['sequence'],'exchange_time':book['time'],'received_at_utc':received.isoformat(),
        'levels':{k:len(book[k]) for k in ('bids','asks')},
        'scenarios':[analyze(book,spec,budget,fee) for budget in (250,1000,5000) for fee in (60,120)],
        'orders':0,'account_fees_verified':False,'single_snapshot_only':True}

def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);results=[]
    for product in ('BTC-USD','ETH-USD','LTC-USD'):
        dest=output/product;dest.mkdir()
        try:result=capture(product,dest)
        except Exception as exc:result={'product':product,'status':'BLOCKED','error':str(exc),'orders':0}
        (dest/'result.json').write_text(json.dumps(result,indent=2));results.append(result)
    (output/'summary.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);run(p.parse_args().output)
