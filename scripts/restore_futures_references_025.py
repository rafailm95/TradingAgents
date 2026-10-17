"""Restore exact saved025 inputs and72 old WFA references; no market requests/replays.

Obtain021InputsPart1,024Parts10/16 segment wrappers and024Part21 using receipts.
Existing files are accepted only if byte-identical; never overwrite other bytes.
"""
import argparse,base64,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='d1004b32dce61b57dce36eae32901e843146e632813bd90db4ff7b199173eae9'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def install(p,raw,digest):
    if sha(raw)!=digest:raise ValueError('Digest mismatch: '+str(p))
    if p.exists():
        if p.read_bytes()!=raw:raise ValueError('Existing bytes differ: '+str(p))
        return
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(raw)
def main():
    p=argparse.ArgumentParser();p.add_argument('--archives',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);a=p.parse_args()
    raw=(ROOT/'research/experiments/025/freeze.json').read_bytes()
    if sha(raw)!=PIN:raise ValueError('Freeze mismatch')
    freeze=json.loads(raw)
    for name,digest in freeze['preserved_files'].items():
        if sha((ROOT/name).read_bytes())!=digest:raise ValueError('Preserved source mismatch: '+name)
    receipt=json.loads((ROOT/'research/experiments/022/input-receipt.json').read_bytes())
    source=a.archives/receipt['name']
    if sha(source.read_bytes())!=receipt['sha256']:raise ValueError('021 input archive mismatch')
    with zipfile.ZipFile(source) as z:
        for symbol in ('BTCUSDT','XRPUSDT'):
            for name,key in [('normalized.json.gz','normalized_sha256'),('manifest.json','manifest_sha256')]:
                matches=[n for n in z.namelist() if n.endswith('/'+symbol+'/'+name)]
                if len(matches)!=1:raise ValueError('Ambiguous archive member')
                install(a.workspace/'futures-023-base'/symbol/name,z.read(matches[0]),freeze['inputs'][symbol][key])
    for name,key in [('normalized.json.gz','normalized_sha256'),('manifest.json','manifest_sha256')]:
        source=ROOT/'research/experiments/022'/('SOLUSDT-'+name+('.b64' if name.endswith('.gz') else ''))
        raw=source.read_bytes();raw=base64.b64decode(raw) if name.endswith('.gz') else raw
        install(a.workspace/'futures-023-base/SOLUSDT'/name,raw,freeze['inputs']['SOLUSDT'][key])
    meta=json.loads((ROOT/'research/experiments/024/artifact-transfer-recovery.json').read_bytes())
    for record in meta['records']:
        if record['original'] not in ('Futures_024_Results_Part10.zip','Futures_024_Results_Part16.zip'):continue
        chunks=[];offset=0
        for item in record['segments']:
            wrapper=a.archives/Path(item['path']).name;raw=wrapper.read_bytes()
            if len(raw)!=item['bytes'] or sha(raw)!=item['sha256'] or offset!=item['offset']:raise ValueError('Wrapper/order mismatch')
            with zipfile.ZipFile(wrapper) as z:chunk=z.read(item['member'])
            if len(chunk)!=item['chunk_bytes'] or sha(chunk)!=item['chunk_sha256']:raise ValueError('Chunk mismatch')
            chunks.append(chunk);offset+=len(chunk)
        install(a.archives/record['original'],b''.join(chunks),record['original_sha256'])
    part21=next(x for x in json.loads((ROOT/'research/experiments/024/artifact_receipts.json').read_bytes())['saved_files'] if x['filename']=='Futures_024_Results_Part21.zip')
    if sha((a.archives/part21['filename']).read_bytes())!=part21['sha256']:raise ValueError('Part21 mismatch')
    found=set()
    for i in (10,16,21):
        with zipfile.ZipFile(a.archives/f'Futures_024_Results_Part{i}.zip') as z:
            for name in z.namelist():
                if name in freeze['reference_files']:
                    install(a.workspace/name,z.read(name),freeze['reference_files'][name]['container_sha256']);found.add(name)
    if found!=set(freeze['reference_files']):raise ValueError('Incomplete reference restoration')
    print(json.dumps({'status':'VERIFIED','assets':3,'reference_files':len(found),'financial_replays':0,'market_requests':0}))
if __name__=='__main__':main()
