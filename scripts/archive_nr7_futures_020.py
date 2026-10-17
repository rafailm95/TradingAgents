"""Create <=32MB input groups as independent ZIPs and verify every archived byte."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]


def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();w=a.workspace
    entries=[]
    for stage in ('train1','train2','evaluation'):
        for path in sorted((w/('nr7-020-'+stage)).iterdir()):
            if path.is_file():entries.append((str(path.relative_to(w)),path))
    entries.append(('inputs/binance-017-normalized.json.gz',w/'binance-017-normalized.json.gz'))
    paths=[*sorted((ROOT/'research/experiments/020').glob('*')),
           ROOT/'docs/NR7_FUTURES_020.json',ROOT/'docs/NR7_FUTURES_020_RESULTS.md',ROOT/'research/registry.json',
           ROOT/'tradingagents/nr7_futures_020.py',ROOT/'scripts/run_nr7_futures_020.py',ROOT/'scripts/package_nr7_futures_020.py',
           ROOT/'scripts/archive_nr7_futures_020.py',ROOT/'tests/test_nr7_futures_020.py',ROOT/'requirements-research.txt']
    for path in paths:
        if path.is_file():entries.append(('repository/'+str(path.relative_to(ROOT)),path))
    entries.append(('Futures_020_NR7_EL.html',w/'Futures_020_NR7_EL.html'))
    inventory=[{'path':name,'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size} for name,path in entries]
    groups=[];group=[];size=0
    for name,path in entries:
        n=path.stat().st_size
        if n>32_000_000:raise ValueError('Individual artifact too large for bounded transfer')
        if group and size+n>32_000_000:groups.append(group);group=[];size=0
        group.append((name,path));size+=n
    if group:groups.append(group)
    result=[]
    for i,group in enumerate(groups,1):
        out=w/f'Futures_020_Evidence_Part{i}.zip'
        with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name,path in group:z.write(path,name)
            z.writestr(f'README_PART{i}.txt','Batch020 evidence. Extract allparts to onefolder. Previous017and019reference archives remain separately persisted with exact pins in protocol. No new real orders. Each base64+gzip result envelope decodes to its SHA256-pinned result.\n')
            z.writestr(f'INVENTORY_PART{i}.json',json.dumps(inventory,indent=2)+'\n')
        with zipfile.ZipFile(out) as z:
            if z.testzip() is not None:raise ValueError('ZIP CRC failure')
            for name,path in group:
                if sha(z.read(name))!=sha(path.read_bytes()):raise ValueError('Archived content mismatch')
        result.append({'path':str(out),'sha256':sha(out.read_bytes()),'bytes':out.stat().st_size,'members':len(group)})
    (w/'nr7-020-archive-inventory.json').write_text(json.dumps({'parts':result,'all_members':inventory},indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
