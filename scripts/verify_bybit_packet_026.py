"""Verify the portable source package before any public request."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT=Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    manifest=json.loads((root/'PACKAGE_FILES.json').read_bytes())
    for name,digest in manifest.items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ValueError('Unsafe package manifest')
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Package file changed or missing: '+name)
    source=json.loads((root/'SOURCE.json').read_bytes())
    freeze=root/'research/collection-026/freeze.json'
    if hashlib.sha256(freeze.read_bytes()).hexdigest()!=source['freeze_sha256']:
        raise ValueError('Collection freeze mismatch')
    print('PACKAGE VERIFIED. Public GET only; no account login or orders.')
    return len(manifest)


if __name__=='__main__':
    try: verify()
    except Exception as error:
        print(str(error));sys.exit(2)
