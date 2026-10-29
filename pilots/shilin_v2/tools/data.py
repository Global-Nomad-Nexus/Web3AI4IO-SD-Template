#!/usr/bin/env python3
"""Verify and restore the lossless shilin_v2 CSV shards. Python standard library only."""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            h.update(block)
    return h.hexdigest()

def manifest():
    return json.loads((ROOT / 'metadata/tables.json').read_text())

def selected(dataset, tables):
    result = [t for t in manifest()['tables'] if dataset == 'all' or t['id'].split('/')[0] == dataset]
    if tables:
        unknown = set(tables) - {t['id'].split('/')[1] for t in result}
        if unknown:
            raise ValueError('Unknown tables: ' + ', '.join(sorted(unknown)))
        result = [t for t in result if t['id'].split('/')[1] in tables]
    return result

def canonical(table):
    if 'alias_of' not in table:
        return table
    return next(t for t in manifest()['tables'] if t['id'] == table['alias_of'])

def payload(table):
    """Yield the exact original CSV bytes, removing repeated shard headers."""
    table = canonical(table)
    header = None
    for part in table['parts']:
        with gzip.open(ROOT / part['path'], 'rb') as stream:
            current = stream.read(table['header_bytes'])
            if header is None:
                header = current
                yield header
            elif current != header:
                raise ValueError('Shard header mismatch: ' + part['path'])
            for block in iter(lambda: stream.read(2**20), b''):
                yield block

def verify(tables, deep=False):
    seen = set()
    for table in tables:
        original = canonical(table)
        if original['id'] not in seen:
            for part in original['parts']:
                path = ROOT / part['path']
                if path.stat().st_size != part['bytes'] or digest(path) != part['sha256']:
                    raise ValueError('Shard integrity failure: ' + part['path'])
            if deep:
                h = hashlib.sha256()
                size = 0
                for block in payload(original):
                    h.update(block)
                    size += len(block)
                if h.hexdigest() != original['sha256'] or size != original['bytes']:
                    raise ValueError('Original CSV integrity failure: ' + original['id'])
                count = 0
                for part in original['parts']:
                    with gzip.open(ROOT / part['path'], 'rt', encoding='utf-8', newline='') as stream:
                        reader = csv.reader(stream)
                        if next(reader) != original['columns']:
                            raise ValueError('Column mismatch: ' + part['path'])
                        rows = sum(1 for _ in reader)
                    if rows != part['rows']:
                        raise ValueError('Shard row count mismatch: ' + part['path'])
                    count += rows
                if count != original['rows']:
                    raise ValueError('Table row count mismatch: ' + original['id'])
            seen.add(original['id'])
        if table['sha256'] != original['sha256'] or table['bytes'] != original['bytes']:
            raise ValueError('Alias identity mismatch: ' + table['id'])
        print('OK', table['id'], f"{table['rows']:,} rows")

def restore(tables, output):
    """Restore into a new directory only; never overwrite an existing workspace."""
    output = output.resolve()
    if output.exists():
        raise ValueError('Output already exists; choose a NEW directory: ' + str(output))
    verify(tables)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.shilin-restore-', dir=output.parent))
    try:
        shutil.copytree(ROOT / 'source', stage, dirs_exist_ok=True)
        for table in tables:
            target = stage / table['restore_path']
            target.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            with target.open('wb') as stream:
                for block in payload(table):
                    stream.write(block)
                    h.update(block)
            if h.hexdigest() != table['sha256'] or target.stat().st_size != table['bytes']:
                raise ValueError('Restored CSV mismatch: ' + table['id'])
        os.rename(stage, output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print('Restored:', output)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['list', 'verify', 'restore'])
    p.add_argument('--dataset', choices=['all', 'p3_v6', 'legacy_7day_72h'], default='all')
    p.add_argument('--table', action='append', help='Table name; may be repeated')
    p.add_argument('--deep', action='store_true', help='Verify CSV hashes, columns and logical row counts')
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    tables = selected(a.dataset, a.table)
    if a.command == 'list':
        for t in tables:
            print(f"{t['id']:48s} {t['rows']:>12,} rows  {t['bytes']:>14,} bytes" + (f"  alias: {t['alias_of']}" if 'alias_of' in t else ''))
    elif a.command == 'verify':
        verify(tables, a.deep)
    else:
        if a.output is None:
            p.error('restore requires --output pointing to a new directory')
        restore(tables, a.output)

if __name__ == '__main__':
    main()
