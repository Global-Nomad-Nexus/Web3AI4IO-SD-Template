#!/usr/bin/env python3
"""Restore the exact sealed P4 delivery using verified GitHub Release assets."""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            h.update(block)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, required=True, help='Directory downloaded with gh release download')
    p.add_argument('--output', type=Path, required=True, help='New output directory')
    a = p.parse_args()
    output = a.output.resolve()
    if output.exists():
        p.error('Output already exists; choose a new directory')
    assets = json.loads((ROOT / 'metadata/release_assets.json').read_text())['assets']
    for asset in assets:
        path = a.assets / asset['name']
        if path.stat().st_size != asset['bytes'] or sha(path) != asset['sha256']:
            raise ValueError('Release asset failed verification: ' + asset['name'])
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.shilin-p4-', dir=output.parent))
    try:
        shutil.copytree(ROOT / 'reproduction/p4_sealed', stage, dirs_exist_ok=True)
        for asset in assets:
            shutil.copy2(a.assets / asset['name'], stage / asset['name'])
        seal = json.loads((stage / 'file_manifest.json').read_text())
        expected = {r['path']: r for r in seal}
        # Original gzip writer uses level=1, mtime=0 and the target filename header.
        # Reconstruct those exact archived bytes, not just semantically equal CSVs.
        from data import manifest, payload
        for table in manifest()['tables']:
            if not table['id'].startswith('p3_v6/'):
                continue
            name = table['id'].split('/')[1] + '.csv.gz'
            path = stage / 'data' / name
            path.parent.mkdir(exist_ok=True)
            with path.open('wb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', compresslevel=1, mtime=0) as gz:
                for block in payload(table):
                    gz.write(block)
        actual = {str(x.relative_to(stage)) for x in stage.rglob('*') if x.is_file() and x.name != 'file_manifest.json'}
        if actual != set(expected):
            raise ValueError('Sealed file set mismatch: ' + str(sorted(actual ^ set(expected))))
        for rel, row in expected.items():
            path = stage / rel
            if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
                raise ValueError('Sealed file mismatch: ' + rel)
        os.rename(stage, output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print('Exact P4 delivery restored and all sealed file hashes verified:', output)
    print('Next: python3 -B', str(output / 'code/accept_delivery.py'), '--release', str(output), '--output NEW_ACCEPTANCE_DIRECTORY')

if __name__ == '__main__':
    main()
