"""Resume an interrupted archive from its original manifest, never rerun PnL."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--workspace', required=True, type=Path)
    w = p.parse_args().workspace
    with zipfile.ZipFile(w / 'Futures_025_Results_Part1.zip') as z:
        inventory = json.loads(z.read('025_INVENTORY_PART1.json'))
    groups, group, size = [], [], 0
    for item in inventory:
        name = item['path']
        path = ROOT / name.removeprefix('repository/') if name.startswith('repository/') else w / name
        if path.stat().st_size != item['bytes'] or sha(path.read_bytes()) != item['sha256']:
            raise ValueError('Original archive input changed: ' + name)
        if group and size + item['bytes'] > 60_000_000:
            groups.append(group)
            group, size = [], 0
        group.append((item, path))
        size += item['bytes']
    if group:
        groups.append(group)
    parts, interrupted = [], []
    for i, group in enumerate(groups, 1):
        target = w / f'Futures_025_Results_Part{i}.zip'
        def verify():
            with zipfile.ZipFile(target) as z:
                if z.testzip():
                    raise ValueError('CRC failure')
                expected = {x['path'] for x, _ in group} | {f'025_README_PART{i}.txt', f'025_INVENTORY_PART{i}.json'}
                if set(z.namelist()) != expected or len(z.namelist()) != len(expected):
                    raise ValueError('Members mismatch')
                if json.loads(z.read(f'025_INVENTORY_PART{i}.json')) != inventory:
                    raise ValueError('Manifest mismatch')
                for item, _ in group:
                    if sha(z.read(item['path'])) != item['sha256']:
                        raise ValueError('Member hash mismatch')
        reused = False
        if target.exists():
            try:
                verify()
                reused = True
            except (zipfile.BadZipFile, EOFError, ValueError) as error:
                old = w / f'Futures_025_Archive_Interrupted_Part{i}.zip.partial'
                if old.exists():
                    raise ValueError('Previous interrupted evidence already exists')
                receipt = {'original': target.name, 'retained_path': str(old), 'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size, 'error': str(error)}
                target.rename(old)
                interrupted.append(receipt)
                print('Preserved incomplete archive ' + old.name, flush=True)
        if not reused:
            with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                for item, path in group:
                    z.write(path, item['path'])
                z.writestr(f'025_README_PART{i}.txt', 'Batch025. Extract every part into onefolder. FullyhistoricalvirtualBinanceUSD-M;noBybit/liveorders. Allpreviousinputs/referencesremain inoriginal021/022/024archives withhashes/receipts. Sourcefreeze andexact commands inrepository/.\n')
                z.writestr(f'025_INVENTORY_PART{i}.json', json.dumps(inventory, indent=2) + '\n')
            verify()
        parts.append({'path': str(target), 'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size, 'members': len(group), 'reused_original_part': reused})
        print(('Reused ' if reused else 'Verified ') + target.name, flush=True)
    (w / 'futures-025-archive-inventory.json').write_text(json.dumps({'parts': parts, 'all_members': inventory}, indent=2) + '\n')
    recovery = {'status': 'ALL_PARTS_VERIFIED', 'cause': 'Archive process unavailable after runtime/tool-context refresh; no financial execution affected.', 'parts': len(parts), 'reused_complete_parts': sum(p['reused_original_part'] for p in parts), 'interrupted': interrupted, 'financial_replays': 0, 'original_member_hashes_preserved': len(inventory)}
    (ROOT / 'research/experiments/025/archive-recovery.json').write_text(json.dumps(recovery, indent=2) + '\n')
    print(json.dumps(recovery), flush=True)


if __name__ == '__main__':
    main()
