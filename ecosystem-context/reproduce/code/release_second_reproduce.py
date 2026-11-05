#!/usr/bin/env python3
"""Rebuild the three released second-level market tables from frozen archives."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import build_second_market as market


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[1]
    data, output = args.data.resolve(), args.output.resolve()
    if output.exists() or data == output or data in output.parents:
        raise SystemExit('Choose a new output directory outside reference data.')
    checks = json.loads((base / 'second-input-checksums.json').read_text())
    for name, digest in checks.items():
        if sha(base / 'inputs' / name) != digest:
            raise ValueError('Input hash mismatch: ' + name)
    jobs = json.loads((base / 'second-jobs.json').read_text())
    for job in jobs:
        for key in ['output', 'hourly_control']:
            if sha(data / job[key]) != job[key + '_sha256']:
                raise ValueError('Reference hash mismatch: ' + job[key])
    output.mkdir(parents=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='ecosystem-second-') as temporary:
        market.ROOT = Path(temporary)
        for job in jobs:
            layer = market.ROOT / job['chain'] / 'layer2'
            (layer / 'output').mkdir(parents=True)
            raw = layer / 'evidence/binance_vision'
            raw.mkdir(parents=True)
            shutil.copyfile(data / job['hourly_control'], layer / 'output' / Path(job['hourly_control']).name)
            for name in job['archives']:
                shutil.copyfile(base / 'inputs' / name, raw / Path(name).name)
            report = market.build(job['chain'], job['pair'], job['days'], job['stem'], offline=True)
            result = layer / report['output']
            # Pinned dependencies make serialization and numerical comparison exact.
            if sha(result) != job['output_sha256']:
                raise ValueError('Rebuilt output differs: ' + job['output'])
            target = output / job['output']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(result, target)
            results.append(dict(file=job['output'], rows=report['rows'], sha256=sha(target), byte_identical=True))
    report = dict(status='Verified', tables=len(results), inputs_verified=len(checks), results=results)
    (output / 'verification-second.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
