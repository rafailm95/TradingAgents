"""Preserve exact failed-upload ZIP bytes in smaller independently hashed ZIPs."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 48_000_000


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--workspace', type=Path, required=True)
    a = p.parse_args()
    w = a.workspace
    initial = json.loads((w / 'research024-upload-response.json').read_bytes())
    originals = json.loads((w / 'futures-024-archive-inventory.json').read_bytes())
    expected = {Path(x['path']).name: x for x in originals['parts']}
    failed = [r for r in initial['results'] if r['status'] == 'failed']
    if len(failed) != 20 or any(r.get('error_code') != 'transfer_failed' for r in failed):
        raise ValueError('Unexpected failure state; do not retry unknown finalization')
    records = []
    for r in failed:
        source = Path(r['local_path'])
        if source.name not in expected:
            raise ValueError('Unexpected failed file')
        raw = source.read_bytes()
        if sha(raw) != expected[source.name]['sha256']:
            raise ValueError('Original archive changed')
        pieces = []
        reconstructed = hashlib.sha256()
        for number, offset in enumerate(range(0, len(raw), LIMIT), 1):
            chunk = raw[offset:offset + LIMIT]
            member = source.name + f'.part{number:03d}'
            target = w / (source.stem + f'_Segment{number:03d}.zip')
            meta = {'original_file': source.name, 'original_sha256': sha(raw),
                    'original_bytes': len(raw), 'offset': offset, 'chunk_bytes': len(chunk),
                    'chunk_sha256': sha(chunk), 'member': member}
            with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as z:
                z.writestr(member, chunk)
                z.writestr('REASSEMBLY.json', json.dumps(meta, indent=2) + '\n')
            with zipfile.ZipFile(target) as z:
                restored = z.read(member)
                if z.testzip() or sha(restored) != sha(chunk):
                    raise ValueError('Chunk verification failure')
                reconstructed.update(restored)
            pieces.append({**meta, 'path': str(target), 'sha256': sha(target.read_bytes()),
                           'bytes': target.stat().st_size})
        if reconstructed.hexdigest() != expected[source.name]['sha256']:
            raise ValueError('Exact reconstruction failure')
        records.append({'original': source.name, 'original_sha256': sha(raw), 'segments': pieces})
    evidence = {'cause': 'Original20large ZIPuploads returned explicit transfer_failed; cause unspecified. Report andPart21 succeeded. No unknown finalizations were retried.',
                'recovery': 'Only failed originals split into <=48000000byte chunks wrapped in ZIPs. Concatenate extracted .partNNN members in ascending numeric order to recover exact originalZIP. Allbyte hashes and reconstructed originalSHAs verified. No strategy replay.',
                'original_upload_response': initial, 'records': records}
    out = ROOT / 'research/experiments/024/artifact-transfer-recovery.json'
    out.write_text(json.dumps(evidence, indent=2) + '\n')
    uploads = [{'local_path': c['path'], 'purpose': 'create_library_file', 'library_artifact_type': 'other'}
               for r in records for c in r['segments']]
    (w / 'research024-recovery-upload-request.json').write_text(json.dumps({'uploads': uploads}))
    print(json.dumps({'originals_preserved': len(records), 'smaller_ZIPs': len(uploads), 'reassembly_verified': True}))


if __name__ == '__main__':
    main()
