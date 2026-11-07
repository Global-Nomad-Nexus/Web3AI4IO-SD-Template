#!/usr/bin/env python3
"""Rebuild the three released AWS-derived tables from frozen AWS input archives."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

EVIDENCE = {
    'base': ['aws-pool-opening-probe.json'],
    'bsc': [],
}
FOLDER = {'base': 'base', 'bsc': 'BSC'}
TABLES = [
    ('base/layer2/aws_network_second.parquet', 'base/layer2/output/aws_network_second.parquet'),
    ('bsc/layer2/aws_network_second.parquet', 'BSC/layer2/output/aws_network_second.parquet'),
    ('base/layer2/uniswap_v2_weth_usdc_pool_second.parquet',
     'base/layer2/output/uniswap_v2_weth_usdc_pool_second.parquet'),
]
CODE = ['build_aws_network_second.py', 'build_aws_base_pool.py', 'validate_second_pool.py']


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def fetch(spec, base_url, archives):
    target = archives / spec['name']
    if target.exists() and sha(target) == spec['sha256']:
        return target
    url = base_url.rstrip('/') + '/' + spec['name']
    partial = target.with_suffix(target.suffix + '.partial')
    # A failed download is retried from the start; the archive hash decides acceptance.
    with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as out:
        shutil.copyfileobj(response, out, 1024 * 1024)
    partial.replace(target)
    return target


def unpack(archive, destination):
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter='data')


def run(workspace, *command):
    start = time.time()
    subprocess.run([sys.executable, *command], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
    return round(time.time() - start)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--archives', type=Path, required=True,
                        help='Directory holding the input archives; missing ones go here with --download.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download', action='store_true', help='Fetch missing archives, then work offline.')
    parser.add_argument('--base-url', help='Override the published archive location.')
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[1]
    data, output, archives = args.data.resolve(), args.output.resolve(), args.archives.resolve()
    if output.exists() or data == output or data in output.parents:
        raise SystemExit('Choose a new output directory outside reference data.')
    spec = json.loads((base / 'aws-input-checksums.json').read_text())
    manifest = {row['path']: row for row in json.loads((base.parent / 'metadata/manifest.json').read_text())}
    if args.download:
        archives.mkdir(parents=True, exist_ok=True)
    verified = 0
    output.mkdir(parents=True)
    timings = {}
    with tempfile.TemporaryDirectory(prefix='ecosystem-aws-') as temporary:
        workspace = Path(temporary)
        for name in CODE:
            (workspace / 'code').mkdir(exist_ok=True)
            shutil.copyfile(base / 'code' / name, workspace / 'code' / name)
        for chain, folder in FOLDER.items():
            layer = workspace / folder / 'layer2'
            selected = layer / 'evidence/aws-selected'
            selected.mkdir(parents=True)
            (layer / 'output').mkdir()
            for name in EVIDENCE[chain]:
                shutil.copyfile(base / 'aws-evidence' / chain / name, layer / 'evidence' / name)
            for path in sorted((base / 'aws-evidence' / chain / 'daily').iterdir()):
                shutil.copyfile(path, selected / path.name)
        shutil.copyfile(data / 'base/layer2/eth_usdc_market_second.parquet',
                        workspace / 'base/layer2/output/eth_usdc_market_second.parquet')
        for item in spec['archives']:
            archive = fetch(item, args.base_url or spec['base_url'], archives) if args.download else archives / item['name']
            if sha(archive) != item['sha256']:
                raise ValueError('Archive hash mismatch: ' + item['name'])
            selected = workspace / FOLDER[item['chain']] / 'layer2/evidence/aws-selected'
            unpack(archive, selected)
            for name, digest in item['files'].items():
                if sha(selected / name) != digest:
                    raise ValueError('Input hash mismatch: ' + name)
                verified += 1
        timings['network_base_seconds'] = run(workspace, 'code/build_aws_network_second.py', '--chain', 'base', '--offline', '--recompute')
        timings['network_bsc_seconds'] = run(workspace, 'code/build_aws_network_second.py', '--chain', 'BSC', '--offline', '--recompute')
        timings['pool_seconds'] = run(workspace, 'code/build_aws_base_pool.py', '--offline')
        timings['pool_check_seconds'] = run(workspace, 'code/validate_second_pool.py')
        results = []
        for table, built in TABLES:
            result = workspace / built
            if sha(result) != manifest[table]['sha256'] or sha(data / table) != manifest[table]['sha256']:
                raise ValueError('Rebuilt output differs: ' + table)
            target = output / table
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(result, target)
            results.append(dict(file=table, rows=manifest[table]['rows'], sha256=sha(target), byte_identical=True))
    report = dict(status='Verified', tables=len(results), inputs_verified=verified,
                  independent_pool_check=True, timings=timings, results=results)
    (output / 'verification-aws.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
