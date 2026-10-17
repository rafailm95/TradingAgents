"""Restore exact024 original ZIP archives from verified persisted segment ZIPs."""
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
    p.add_argument('--segments', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    metadata = json.loads((ROOT / 'research/experiments/024/artifact-transfer-recovery.json').read_bytes())
    a.output.mkdir(parents=True, exist_ok=True)
    for record in metadata['records']:
        target = a.output / record['original']
        digest = hashlib.sha256()
        offset = 0
        with target.open('xb') as destination:
            for item in record['segments']:
                wrapper = a.segments / Path(item['path']).name
                raw = wrapper.read_bytes()
                if len(raw) != item['bytes'] or sha(raw) != item['sha256'] or item['offset'] != offset:
                    raise ValueError('Segment wrapper or ordering mismatch: ' + wrapper.name)
                with zipfile.ZipFile(wrapper) as z:
                    chunk = z.read(item['member'])
                if len(chunk) != item['chunk_bytes'] or sha(chunk) != item['chunk_sha256']:
                    raise ValueError('Segment content mismatch: ' + wrapper.name)
                destination.write(chunk)
                digest.update(chunk)
                offset += len(chunk)
        if digest.hexdigest() != record['original_sha256']:
            raise ValueError('Original archive reconstruction mismatch: ' + target.name)
        print('Restored and verified ' + target.name)
    print('Part21 was saved directly; obtain it separately using artifact_receipts.json. Extract all21 original ZIPs into one directory.')


if __name__ == '__main__':
    main()
