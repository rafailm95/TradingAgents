"""Offline audit/normalization of the unchanged persisted021 SOL archives."""
import argparse,gzip,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tradingagents import sol_funding_022 as a

def main():
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--output',type=Path,required=True);x=p.parse_args()
    if x.output.exists():raise ValueError('New output directory required')
    data,audit=a.audit_raw(x.raw_root,x.manifest_sha256)
    if set(data)!={'SOLUSDT'}:raise ValueError('SOL-only contract')
    a.prepare(data['SOLUSDT'],'SOLUSDT')
    payload={'schema':'binance022_normalized_v1','datasets':data,'audit':audit}
    folder=x.output/'SOLUSDT';folder.mkdir(parents=True)
    (folder/'normalized.json.gz').write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode(),mtime=0))
    shutil.copyfile(x.raw_root/'manifest.json',folder/'manifest.json')
    result={'normalized_sha256':a.sha(folder/'normalized.json.gz'),'manifest_sha256':x.manifest_sha256,'audit':audit}
    (folder/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
