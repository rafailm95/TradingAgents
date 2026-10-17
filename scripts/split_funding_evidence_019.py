"""Partition the verified archive into3independently readable ZIPs after transfer failure."""
from pathlib import Path
import hashlib,json,os,zipfile
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT.parent
SOURCE=WORK/'Futures_019_Funding_Evidence.zip'
EXPECTED='633bd89dad2175d17a288d8dc68a33cd332b8d5b1c1a8af11b94eb6dc8d9cd75'


def main():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('Source archive changed')
    bins=[[],[],[]];sizes=[0,0,0]
    with zipfile.ZipFile(SOURCE) as src:
        for entry in sorted(src.infolist(),key=lambda e:(-e.file_size,e.filename)):
            i=min(range(3),key=lambda i:sizes[i]);bins[i].append(entry);sizes[i]+=entry.file_size
        receipts=[]
        for i,entries in enumerate(bins,1):
            path=WORK/f'Futures_019_Evidence_Part{i}.zip'
            with path.open('xb') as f:
                with zipfile.ZipFile(f,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as out:
                    for entry in entries:out.writestr(entry.filename,src.read(entry.filename))
                    out.writestr(f'README_PART{i}.txt','Part'+str(i)+'of3. Extract all3ZIPs to the same directory. Original member names/bytes are preserved without overlap. Full result paths and hashes are in repository/research/experiments/019/full_result_hashes.json. Original oversized archive transfer failed; no result was dropped.')
                f.flush();os.fsync(f.fileno())
            with zipfile.ZipFile(path) as check:
                if check.testzip():raise ValueError('Partition CRC failed')
                for entry in entries:
                    if check.read(entry.filename)!=src.read(entry.filename):raise ValueError('Partition member changed')
            receipts.append({'file':path.name,'bytes':path.stat().st_size,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'original_members':len(entries)})
    receipt={'status':'PASS','reason':'Whole105.6MBarchive transfer_failed twice; use3smallerstandaloneZIPs, no further whole-file retries.',
             'source_archive_sha256':EXPECTED,'all123originalmembers_preserved':sum(len(b) for b in bins)==123,
             'parts':receipts,'extract_all_three_into_same_directory':True}
    (ROOT/'research/experiments/019/partition-verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()

