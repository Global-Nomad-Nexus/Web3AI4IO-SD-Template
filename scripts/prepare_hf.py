"""Create an explicit SYNTHETIC package locally. This script never uploads."""
from pathlib import Path
import argparse, hashlib, json, shutil, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'code/shared'))
from pipeline import read_json, verify

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo', action='store_true', required=True)
    p.add_argument('--output', type=Path, default=ROOT/'dist/hugging_face_demo')
    a = p.parse_args()
    dest = a.output.resolve()
    if dest.exists():
        raise SystemExit('Destination exists. Inspect it and choose a fresh output directory.')
    files = {
        'on_chain.csv':'data/on_chain/processed_data/demo/events.csv',
        'off_chain.csv':'data/off_chain/processed_data/demo/records.csv',
        'integration.csv':'data/integration/processed_data/demo/integrated.csv',
        'crosswalk.csv':'data/integration/linkage/demo/crosswalk.csv',
        'unmatched_events.csv':'data/integration/processed_data/demo/unmatched_events.csv',
        'unused_off_chain.csv':'data/integration/processed_data/demo/unused_off_chain.csv',
        'data_dictionary.csv':'metadata/data_dictionary.csv',
        'field_provenance.csv':'metadata/field_provenance.csv',
        'LICENSE':'LICENSE',
    }
    for rel in files.values():
        if not (ROOT/rel).is_file():
            raise SystemExit(f'Missing approved package input: {rel}')
    # Verify archived data against the frozen release before generating new hashes.
    references = read_json(ROOT/'tests/reference/outputs.json')
    for track, track_references in references.items():
        for name, expected in track_references.items():
            if name.startswith('processed_data/'):
                verify(ROOT/'data'/track/'processed_data/demo'/Path(name).name, expected)
    integration_inputs = read_json(ROOT/'metadata/integration_source_manifest.json')
    crosswalk = next(f for f in integration_inputs['files'] if f['filename']=='crosswalk.csv')
    verify(ROOT/crosswalk['path'], crosswalk['sha256'])
    dest.mkdir(parents=True)
    for name, rel in files.items():
        shutil.copyfile(ROOT/rel,dest/name)
    card = (ROOT/'templates/DATASET_CARD.md').read_text()
    card = card[:card.index('# AUTHOR INPUT: dataset title')]
    card = card.replace('pretty_name: AUTHOR INPUT - dataset title', 'pretty_name: Web3AI4IO synthetic teaching example\nlicense: mit')
    card += '''# Synthetic teaching example

Every record and relationship in this package is invented. No empirical Web3,
AI, organization, or individual data are included. The three configurations
demonstrate reproducible source pipelines and explicit integration. The loader
split named train is not a scientific train/test design.

See data_dictionary.csv, field_provenance.csv and the unmatched/unused tables.
The integration has one row per fictional event, permits only a single approved
active link, and selects a record published with a reference period ending no
later than the event. Missing values remain missing. Match coverage is not
linkage accuracy. These fixtures establish no real-world measurement validity,
model performance, causal effect, social impact or identity relationship.

Code and tutorials: https://github.com/sunshineluyao/Web3AI4IO-SD-Template
Data revision: synthetic-v1. This local package has not been uploaded or
validated by a hosting platform or Croissant validator. Source records can be
traced to the repository's data_source fixtures and manifest files. Use only for
learning and software tests; replace with reviewed research evidence for a
scientific release. License and original copyright notice are in LICENSE.
'''
    (dest/'README.md').write_text(card)
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dest.iterdir()) if p.is_file()}
    (dest/'package_manifest.json').write_text(json.dumps({'evidence_status':'SYNTHETIC','data_revision':'synthetic-v1','files':hashes},indent=2,sort_keys=True)+'\n')
    print(f'Created {dest}; {len(hashes)} approved files plus manifest; no upload performed.')

if __name__ == '__main__':
    main()
