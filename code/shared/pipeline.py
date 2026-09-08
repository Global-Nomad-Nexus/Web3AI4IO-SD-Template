"""Deterministic, offline SYNTHETIC teaching pipelines. No live acquisition."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse, csv, hashlib, json, shutil

ROOT = Path(__file__).resolve().parents[2]
TRACKS = ('on_chain', 'off_chain', 'integration')
REVISION = 'synthetic-v1'
ON = ['event_id','chain_id','contract_id','block_number','block_hash','transaction_id','log_index','event_time','amount_units','canonical']
OFF = ['record_id','source_id','entity_id','reference_start','reference_end','published_at','retrieved_at','measure','unit']
CW = ['crosswalk_id','chain_id','contract_id','entity_id','relationship_type','valid_from','valid_to','review_status','matching_method','evidence_id']
INTEGRATED = ON + ['link_status','crosswalk_id','entity_id','record_id','source_id','reference_start','reference_end','published_at','retrieved_at','measure','unit','relationship_type','evidence_id','on_chain_revision','off_chain_revision']

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write_json(path, obj):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def read_csv(path, fields=None):
    with Path(path).open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if fields is not None:
            require(reader.fieldnames == fields, f'Schema mismatch: {path}')
        rows = list(reader)
    require(all(None not in r and all(v is not None for v in r.values()) for r in rows), 'Malformed CSV row')
    return rows

def write_csv(path, fields, rows):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader(); w.writerows(rows)

def utc(value):
    require(value.endswith('Z'), f'Expected explicit UTC timestamp: {value}')
    return datetime.fromisoformat(value.replace('Z','+00:00'))

def unique(rows, keys):
    values = [tuple(r[k] for k in keys) for r in rows]
    require(len(values) == len(set(values)), f'Duplicate key: {keys}')

def deduplicate(rows, keys):
    seen = {}; count = 0
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key in seen:
            require(row == seen[key], f'Conflicting duplicate: {key}')
            count += 1
        else:
            seen[key] = row
    return list(seen.values()), count

def verify(path, expected):
    require(Path(path).is_file(), f'Missing input: {path}')
    require(sha(path) == expected, f'Checksum mismatch: {path}')

def validate_on(rows):
    unique(rows, ['event_id']); unique(rows, ['chain_id','transaction_id','log_index'])
    blocks = {}
    for r in rows:
        require(all(r[k] for k in ON if k != 'amount_units'), 'Empty on-chain identifier or time')
        require(r['canonical'] == 'true', 'Non-canonical event reached processed data')
        require(int(r['block_number']) >= 0 and int(r['log_index']) >= 0, 'Negative block/log index')
        utc(r['event_time'])
        if r['amount_units'] != '':
            require(int(r['amount_units']) >= 0, 'Negative demo amount')
        key = (r['chain_id'],r['block_number'])
        require(key not in blocks or blocks[key] == r['block_hash'], 'Inconsistent block hash')
        blocks[key] = r['block_hash']

def validate_off(rows):
    unique(rows, ['record_id']); unique(rows, ['source_id','record_id'])
    for r in rows:
        require(all(r[k] for k in OFF if k != 'measure'), 'Empty off-chain identifier or time')
        require(utc(r['reference_start']) <= utc(r['reference_end']), 'Reversed reference period')
        require(utc(r['published_at']) <= utc(r['retrieved_at']), 'Retrieval before publication')
        require(r['unit'] == 'demo-index', 'Unexpected measurement unit')
        if r['measure'] != '':
            int(r['measure'])

def validate_crosswalk(rows):
    unique(rows, ['crosswalk_id'])
    for r in rows:
        require(all(r.values()), 'Missing linkage evidence or metadata')
        require(r['review_status'] in ('approved','candidate','rejected'), 'Unknown review status')
        require(utc(r['valid_from']) < utc(r['valid_to']), 'Invalid linkage validity interval')

def join_records(events, documents, crosswalk, max_age_days=None):
    """One output per event; no record means missing, never a fabricated zero."""
    validate_on(events); validate_off(documents); validate_crosswalk(crosswalk)
    outputs = []
    for e in sorted(events, key=lambda r:r['event_id']):
        t = utc(e['event_time'])
        candidates = [c for c in crosswalk if (c['chain_id'],c['contract_id']) == (e['chain_id'],e['contract_id'])
                      and utc(c['valid_from']) <= t < utc(c['valid_to']) and c['review_status'] != 'rejected']
        approved = [c for c in candidates if c['review_status'] == 'approved']
        require(len(approved) <= 1, f"Ambiguous approved crosswalk for {e['event_id']}")
        out = dict.fromkeys(INTEGRATED, '')
        out.update(e); out.update(on_chain_revision=REVISION, off_chain_revision=REVISION)
        if not approved:
            out['link_status'] = 'unreviewed_link' if candidates else 'no_crosswalk'
        else:
            c = approved[0]
            out.update({k:c[k] for k in ['crosswalk_id','entity_id','relationship_type','evidence_id']})
            docs = [d for d in documents if d['entity_id'] == c['entity_id']
                    and utc(d['published_at']) <= t and utc(d['reference_end']) <= t]
            if max_age_days is not None:
                docs = [d for d in docs if (t-utc(d['published_at'])).total_seconds() <= max_age_days*86400]
            docs.sort(key=lambda d: (utc(d['published_at']), utc(d['reference_end'])), reverse=True)
            if not docs:
                out['link_status'] = 'no_prior_record'
            else:
                if len(docs) > 1:
                    require((utc(docs[0]['published_at']),utc(docs[0]['reference_end'])) != (utc(docs[1]['published_at']),utc(docs[1]['reference_end'])),
                            f"Tied source records require adjudication for {e['event_id']}")
                d = docs[0]; out['link_status'] = 'matched'
                out.update({k:d[k] for k in OFF})
        outputs.append(out)
    require(len(outputs) == len(events), 'Join changed the event denominator')
    unique(outputs, ['event_id'])
    return outputs

def workspace(base, track):
    require(track in TRACKS, 'Unknown track')
    w = Path(base).resolve() / track
    require(w != ROOT and not ROOT.is_relative_to(w), 'Unsafe output location')
    for protected in ('data','code','metadata','tests','notebooks','docs','templates','scripts','paper','assets'):
        require(not w.is_relative_to(ROOT/protected), 'Outputs must not overwrite repository sources')
    for stage in ('queried_data','processed_data','reports'):
        (w / stage).mkdir(parents=True, exist_ok=True)
    return w

def source_spec(track):
    return read_json(ROOT / 'metadata' / f'{track}_source_manifest.json')

def query(track, w):
    spec = source_spec(track)
    for upstream in spec.get('upstream_manifests', []):
        p = ROOT/upstream['path']; verify(p,upstream['sha256'])
        manifest = read_json(p)
        require(manifest['data_revision'] == REVISION, 'Upstream release revision mismatch')
        for item in manifest['files']:
            verify(ROOT/item['path'],item['sha256'])
            require(any(f['path']==item['path'] and f['sha256']==item['sha256'] for f in spec['files']),
                    'Integration source disagrees with upstream manifest')
    inputs = []
    for f in spec['files']:
        p = ROOT / f['path']; verify(p, f['sha256'])
        dest = w / 'queried_data' / f['filename']
        shutil.copyfile(p, dest)
        inputs.append({'path':f['path'],'filename':f['filename'],'sha256':sha(dest)})
    write_json(w/'reports/acquisition.json', {'evidence_status':'SYNTHETIC','mode':'archived_offline',
               'data_revision':REVISION,'inputs':inputs,'live_requests':0})

def checked_inputs(track, w):
    for f in source_spec(track)['files']:
        verify(w/'queried_data'/f['filename'], f['sha256'])

def process(track, w):
    checked_inputs(track,w)
    out = w/'processed_data'
    if track == 'on_chain':
        raw = read_csv(w/'queried_data/events.csv', ON)
        require(all(r['canonical'] in ('true','false') for r in raw), 'Unknown canonical flag')
        rows, dup = deduplicate(raw, ['chain_id','transaction_id','log_index'])
        kept = sorted((r for r in rows if r['canonical']=='true'), key=lambda r:r['event_id'])
        validate_on(kept); write_csv(out/'events.csv', ON, kept)
        report = {'raw_rows':len(raw),'exact_duplicates_removed':dup,'noncanonical_removed':len(rows)-len(kept),'processed_rows':len(kept)}
    elif track == 'off_chain':
        raw = read_csv(w/'queried_data/records.csv', OFF)
        kept, dup = deduplicate(raw, ['source_id','record_id'])
        kept.sort(key=lambda r:r['record_id']); validate_off(kept)
        write_csv(out/'records.csv', OFF, kept)
        report = {'raw_rows':len(raw),'exact_duplicates_removed':dup,'processed_rows':len(kept),'missing_measure':sum(r['measure']=='' for r in kept)}
    else:
        ev = read_csv(w/'queried_data/on_chain.csv', ON)
        docs = read_csv(w/'queried_data/off_chain.csv', OFF)
        cw = read_csv(w/'queried_data/crosswalk.csv', CW)
        kept = join_records(ev,docs,cw)
        write_csv(out/'integrated.csv', INTEGRATED, kept)
        write_csv(out/'unmatched_events.csv', INTEGRATED, [r for r in kept if r['link_status']!='matched'])
        used = {r['record_id'] for r in kept if r['record_id']}
        write_csv(out/'unused_off_chain.csv', OFF, [r for r in docs if r['record_id'] not in used])
        report = {'on_chain_rows':len(ev),'off_chain_rows':len(docs),'output_rows':len(kept),
                  'link_status_counts':dict(sorted(Counter(r['link_status'] for r in kept).items())),
                  'unused_off_chain_rows':len(docs)-len(used), 'join_cardinality':'one output per event'}
    report.update(evidence_status='SYNTHETIC', data_revision=REVISION)
    write_json(w/'reports/processing.json', report)

def analyze(track,w):
    if track == 'on_chain':
        rows = read_csv(w/'processed_data/events.csv', ON)
        validate_on(rows)
        result = {'rows':len(rows),'unique_contracts':len({r['contract_id'] for r in rows}),
                  'missing_amount':sum(r['amount_units']=='' for r in rows)}
    elif track == 'off_chain':
        rows = read_csv(w/'processed_data/records.csv', OFF); validate_off(rows)
        result = {'rows':len(rows),'unique_entities':len({r['entity_id'] for r in rows}),
                  'missing_measure':sum(r['measure']=='' for r in rows)}
    else:
        rows = read_csv(w/'processed_data/integrated.csv', INTEGRATED)
        matched = [r for r in rows if r['link_status']=='matched']
        result = {'event_denominator':len(rows),'matched_events':len(matched),
                  'match_coverage':len(matched)/len(rows) if rows else None,
                  'matched_with_missing_measure':sum(r['measure']=='' for r in matched),
                  'link_accuracy':'NOT_ESTIMATED: synthetic rules do not establish real linkage accuracy'}
    result.update(evidence_status='SYNTHETIC', inference='descriptive_only', data_revision=REVISION)
    write_json(w/'reports/analysis.json', result)

def output_hashes(w):
    paths = sorted((w/'processed_data').glob('*.csv')) + [w/'reports/processing.json',w/'reports/analysis.json']
    return {str(p.relative_to(w)):sha(p) for p in paths}

def validate(track,w):
    checked_inputs(track,w)
    expected = read_json(ROOT/'tests/reference/outputs.json')[track]
    actual = output_hashes(w)
    require(actual == expected, 'Outputs differ from the governed synthetic reference')
    report = {'evidence_status':'SYNTHETIC','data_revision':REVISION,'reference_comparison':'PASS',
              'files_compared':len(actual),'output_sha256':actual,
              'scientific_validation':'NOT_ESTABLISHED: authors must collect and independently review real evidence'}
    if track == 'integration':
        ev = read_csv(w/'queried_data/on_chain.csv', ON); docs = read_csv(w/'queried_data/off_chain.csv', OFF)
        cw = read_csv(w/'queried_data/crosswalk.csv', CW)
        strict = join_records(ev,docs,cw,max_age_days=7)
        report['sensitivity'] = {'max_publication_age_days':7,'matched_events':sum(r['link_status']=='matched' for r in strict),
                                 'note':'Illustration of a policy choice, not an accuracy estimate'}
    write_json(w/'reports/validation.json', report)

def run_stage(track,stage,workdir):
    w=workspace(workdir,track)
    {'query_data':query,'process_data':process,'analyze_data':analyze,'technical_validation':validate}[stage](track,w)
    return w

def cli(track,stage):
    p=argparse.ArgumentParser(description='Offline synthetic tutorial stage')
    p.add_argument('--workdir', type=Path, default=ROOT/'outputs/demo')
    a=p.parse_args(); w=run_stage(track,stage,a.workdir)
    print(f'{track}/{stage}: complete; SYNTHETIC outputs in {w}')
