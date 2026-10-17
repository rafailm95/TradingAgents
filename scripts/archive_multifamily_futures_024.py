"""Archive complete024 evidence into bounded ZIP parts; verify every member hash."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();w=a.workspace
    entries=[]
    for folder in ('futures-024-train1','futures-024-train2','futures-024-evaluation'):
        for path in sorted((w/folder).rglob('*')):
            if path.is_file():entries.append((str(path.relative_to(w)),path))
    for name in ('Futures_024_Twenty_Strategies_EL.html','futures-024-train1.log','futures-024-train2.log','futures-024-evaluation.log','futures-024-package.log','futures-024-completion.log'):
        entries.append((name,w/name))
    sources=[*sorted((ROOT/'research/experiments/024').glob('*')),ROOT/'docs/MULTIFAMILY_FUTURES_024.json',ROOT/'docs/MULTIFAMILY_FUTURES_024_RESULTS.md',ROOT/'docs/MULTIFAMILY_FUTURES_024_REPRODUCE.md',ROOT/'tradingagents/multifamily_futures_024.py',ROOT/'scripts/run_multifamily_futures_024.py',ROOT/'scripts/freeze_multifamily_futures_024.py',ROOT/'scripts/package_multifamily_futures_024.py',ROOT/'scripts/archive_multifamily_futures_024.py',ROOT/'tests/test_multifamily_futures_024.py',ROOT/'tests/test_multifamily_runner_024.py',ROOT/'requirements-research.txt',ROOT/'research/registry.json']
    for path in sources:
        if path.is_file():entries.append(('repository/'+str(path.relative_to(ROOT)),path))
    completion=ROOT/'scripts/complete_multifamily_futures_024.py'
    entries.append(('repository/scripts/complete_multifamily_futures_024.py',completion))
    inventory=[{'path':name,'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size} for name,path in entries]
    groups=[];group=[];size=0
    for name,path in entries:
        n=path.stat().st_size
        if n>128_000_000:raise ValueError('Individualfile exceeds partbound')
        if group and size+n>128_000_000:groups.append(group);group=[];size=0
        group.append((name,path));size+=n
    if group:groups.append(group)
    parts=[]
    for i,group in enumerate(groups,1):
        target=w/f'Futures_024_Results_Part{i}.zip'
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name,path in group:z.write(path,name)
            z.writestr(f'024_README_PART{i}.txt','Batch024. Extract every part into onefolder. FullyhistoricalvirtualBinanceUSD-M;noBybit/liveorders. Allpreviousinputs/referencesremain inoriginal021/022archives withhashes/receipts. Sourcefreeze andexact commands inrepository/.\n')
            z.writestr(f'024_INVENTORY_PART{i}.json',json.dumps(inventory,indent=2)+'\n')
        with zipfile.ZipFile(target) as z:
            if z.testzip():raise ValueError('ZIPCRCfailure')
            for name,path in group:
                if sha(z.read(name))!=sha(path.read_bytes()):raise ValueError('Archivebyte mismatch')
        parts.append({'path':str(target),'sha256':sha(target.read_bytes()),'bytes':target.stat().st_size,'members':len(group)})
        print('Verified '+target.name,flush=True)
    (w/'futures-024-archive-inventory.json').write_text(json.dumps({'parts':parts,'all_members':inventory},indent=2)+'\n')
    print(json.dumps({'parts':len(parts),'bytes':sum(p['bytes'] for p in parts),'members':len(entries)}),flush=True)
if __name__=='__main__':main()
