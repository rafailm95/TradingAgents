"""Offline official daily recovery, complete audit and deterministic input export."""
import argparse,gzip,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tradingagents.binance_archive import audit_raw,sha

def run(raw_root,output_root,normalized):
    if output_root.exists() or normalized.exists():raise ValueError('New outputs required')
    original=json.loads((raw_root/'manifest.json').read_bytes())
    if original['symbols']!=['ETHUSDT']:raise ValueError('This bounded attempt accepts only ETH')
    shutil.copytree(raw_root,output_root)
    shutil.copyfile(raw_root/'manifest.json',output_root/'original-collection-manifest.json')
    original['supplemental_daily']=[json.loads(p.read_bytes()) for p in sorted((raw_root/'daily-repairs').glob('*.receipt.json'))]
    if {r['day'] for r in original['supplemental_daily']}!={'2022-10-01','2022-10-02','2023-02-23','2023-02-24'}:raise ValueError('Exact four official daily source files required')
    original['original_collection_manifest_sha256']=sha(raw_root/'manifest.json')
    original['assembly_utc']=datetime.now(timezone.utc).isoformat()
    original['attribution']='Source: Binance Vision public USD-M archives, CC BY-NC-SA4.0 dataset terms. Personal non-production historical research only; no Binance endorsement. https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md'
    (output_root/'manifest.json').write_text(json.dumps(original,indent=2)+'\n')
    data,audit=audit_raw(output_root,sha(output_root/'manifest.json'))
    if audit['recovered_real_hours']!=48 or audit['matched_overlap_hours']!=48:raise ValueError('Unexpected recovery scope')
    (output_root/'input-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    with normalized.open('xb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as z:
        z.write(json.dumps({'schema':'binance017_normalized_v1','audit':audit,'datasets':data},separators=(',',':'),allow_nan=False).encode())
    print(json.dumps({'audit':audit,'normalized_sha256':sha(normalized),'normalized_bytes':normalized.stat().st_size}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--normalized',type=Path,required=True);a=p.parse_args();run(a.raw_root,a.output_root,a.normalized)
