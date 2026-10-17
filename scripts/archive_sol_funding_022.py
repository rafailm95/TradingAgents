"""Persist bounded independent ZIP parts, verifying every archived byte. No PnL."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--stage',choices=['inputs','results'],required=True);a=p.parse_args();w=a.workspace
    entries=[]
    if a.stage=='inputs':
        for folder in ('futures-022-data',):
            for path in sorted((w/folder).rglob('*')):
                if path.is_file():entries.append((str(path.relative_to(w)),path))
        prefix='Futures_022_Inputs'
    else:
        for folder in ('futures-022-train1','futures-022-train2','futures-022-evaluation'):
            for path in sorted((w/folder).rglob('*')):
                if path.is_file():entries.append((str(path.relative_to(w)),path))
        entries.append(('Futures_022_SOL_BTC_XRP_EL.html',w/'Futures_022_SOL_BTC_XRP_EL.html'))
        for name in ('futures-022-train1.log','futures-022-train2.log','futures-022-evaluation.log'):
            entries.append((name,w/name))
        prefix='Futures_022_Results'
    sources=[*sorted((ROOT/'research/experiments/022').glob('*')),ROOT/'docs/SOL_FUNDING_022.json',
             ROOT/'scripts/audit_sol_funding_022.py',ROOT/'tradingagents/sol_funding_022.py',ROOT/'scripts/run_sol_funding_022.py',
             ROOT/'tests/test_sol_funding_022.py',ROOT/'tests/test_sol_replay_022.py',ROOT/'scripts/package_sol_funding_022.py',
             ROOT/'scripts/archive_sol_funding_022.py',ROOT/'scripts/report_cross_asset_022.py',ROOT/'docs/NEXT_FUTURES_023_PLAN.md',ROOT/'requirements-research.txt']
    if a.stage=='results':sources.extend([ROOT/'docs/SOL_FUNDING_022_RESULTS.md',ROOT/'docs/SOL_FUNDING_022_REPRODUCE.md',ROOT/'research/registry.json'])
    for path in sources:
        if path.is_file():entries.append(('repository/'+str(path.relative_to(ROOT)),path))
    inventory=[{'path':name,'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size} for name,path in entries]
    groups=[];group=[];size=0
    for name,path in entries:
        n=path.stat().st_size
        if n>32_000_000:raise ValueError('Individualfile exceeds transfer part bound')
        if group and size+n>32_000_000:groups.append(group);group=[];size=0
        group.append((name,path));size+=n
    if group:groups.append(group)
    parts=[]
    for i,group in enumerate(groups,1):
        target=w/f'{prefix}_Part{i}.zip'
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name,path in group:z.write(path,name)
            z.writestr(f'{prefix}_README_PART{i}.txt','Batch022. Extract allinput and resultparts into onefolder. NativeBinance publicdata; historicalvirtualaccounting, noorders. Sources and freezepins in repository/. Preserveallfailures.\n')
            z.writestr(f'{prefix}_INVENTORY_PART{i}.json',json.dumps(inventory,indent=2)+'\n')
        with zipfile.ZipFile(target) as z:
            if z.testzip() is not None:raise ValueError('ZIP CRC mismatch')
            for name,path in group:
                if sha(z.read(name))!=sha(path.read_bytes()):raise ValueError('Archived bytes mismatch')
        parts.append({'path':str(target),'sha256':sha(target.read_bytes()),'bytes':target.stat().st_size,'members':len(group)})
        print('Verified '+target.name,flush=True)
    (w/f'futures-022-{a.stage}-archive-inventory.json').write_text(json.dumps({'parts':parts,'all_members':inventory},indent=2)+'\n')
    print(json.dumps(parts,indent=2),flush=True)


if __name__=='__main__':main()
