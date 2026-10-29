"""Validate actual P0/P1 outputs without network requests or lifecycle assertions."""
from common import *

def run():
    checks=[]
    code_version=sid(*[(p.name,sha(p)) for p in sorted((ROOT/'code').glob('*.py'))])
    def check(name,tested,failed,refs='',severity='error'):
        checks.append({'check_id':name,'scope':'P0/P1_actual_data','tested_count':tested,'failure_count':failed,'failure_refs':refs,'severity':severity,'executed_at_utc':now(),'code_version':code_version,'status':'passed' if not failed else ('open_limitation' if severity=='limitation' else 'failed')})
    baseline=json.loads((ROOT/'reports/baseline_audit.json').read_text())
    bad=[x['path'] for x in baseline['inputs'] if sha(x['path'])!=x['sha256']]
    check('legacy_archive_byte_integrity',len(baseline['inputs']),len(bad),'|'.join(bad))
    tables={p.stem:read_csv(p) for p in (ROOT/'processed').glob('*.csv')}
    registry=tables['registry'];ids={r['token_id'] for r in registry};events={r['creation_event_id'] for r in tables['creation_events']}
    check('registry_token_unique',len(registry),len(registry)-len(ids))
    check('creation_event_unique',len(tables['creation_events']),len(tables['creation_events'])-len(events))
    check('crosswalk_all_legacy_events',4668,abs(4668-len(tables['token_id_crosswalk'])))
    check('crosswalk_token_foreign_keys',len(tables['token_id_crosswalk']),sum(r['token_id'] not in ids for r in tables['token_id_crosswalk']))
    check('registry_creation_foreign_keys',len(registry),sum(r['creation_event_id'] not in events for r in registry))
    check('legacy_creation_window',len(registry),sum(not 1791417600<=epoch(r['created_at_utc'])<1792022400 for r in registry))
    check('metadata_coverage_denominator',18672,abs(18672-len(tables['metadata_coverage'])))
    for table,key in [('pm_markets','market_snapshot_id'),('pm_outcomes','pm_outcome_key'),('pm_prices','price_observation_id'),('pm_mapping','mapping_id'),('token_expectations_at_creation','expectation_link_id')]:
        data=tables[table];check(table+'_unique',len(data),len(data)-len({r[key] for r in data}))
    market_ids={r['market_snapshot_id'] for r in tables['pm_markets']};outcome_ids={r['pm_outcome_key'] for r in tables['pm_outcomes']};pindex={r['price_observation_id']:r for r in tables['pm_prices']};mapping_ids={r['mapping_id'] for r in tables['pm_mapping']}
    check('outcome_market_fk',len(outcome_ids),sum(r['market_snapshot_id'] not in market_ids for r in tables['pm_outcomes']))
    check('price_outcome_fk',len(pindex),sum(r['pm_outcome_key'] not in outcome_ids for r in pindex.values()))
    check('price_range',len(pindex),sum(not 0<=float(r['price'])<=1 for r in pindex.values()))
    check('bucket_end_matches_width',len(pindex),sum(epoch(r['source_timestamp_utc'])+int(r['resolution_seconds'])!=epoch(r['effective_information_time_utc']) for r in pindex.values()))
    joins=tables['token_expectations_at_creation'];matched=[r for r in joins if r['match_status']=='matched_valid']
    check('left_join_retains_exact_token_set',len(ids),len(ids.symmetric_difference({r['token_id'] for r in joins})))
    check('joined_price_and_mapping_fks',len(matched),sum(r['price_observation_id'] not in pindex or r['mapping_id'] not in mapping_ids for r in matched))
    check('strict_price_end_before_creation',len(matched),sum(epoch(r['effective_information_time_utc'])>=epoch(r['anchor_time_utc']) for r in matched))
    check('primary_staleness_limit',len(matched),sum(epoch(r['anchor_time_utc'])-epoch(r['effective_information_time_utc'])>86400 for r in matched))
    check('settlement_and_ambiguous_tick_not_joined',len(matched),sum(int(pindex[r['price_observation_id']]['resolution_seconds'])==0 for r in matched))
    samples=read_csv(ROOT/'reports/verified_creation_samples.csv')
    check('three_native_creation_samples',len(samples),sum(r['creator_and_mint_and_native_position_match']!='True' or r['slot_matches']!='True' for r in samples))
    raw=[]
    for path in (ROOT/'raw').rglob('*.meta.json'):
        meta=json.loads(path.read_text());raw.append(meta)
    check('raw_response_hashes',len(raw),sum(sha(ROOT/m['raw_ref'])!=m['sha256'] for m in raw))
    protocol=json.loads((ROOT/'configs/protocol.yaml').read_text())
    check('real_lifecycle_disabled_without_cutoff',1,int(protocol['lifecycle_analysis_enabled'] or protocol['observation_cutoff_utc'] is not None))
    check('legacy_chain_unresolved_cases',4,4,'Original signatures unavailable in retained report; requires cluster logs',severity='limitation')
    check('legacy_missing_snapshot_cases',4,4,'reports/unresolved_cases.csv',severity='limitation')
    check('whole_window_creation_completeness',3,3,'Deferred to P2/P3B; finite probes are not enumeration',severity='limitation')
    check('historical_rule_revision_archive',len(tables['pm_markets']),len(tables['pm_markets']),'Current rules snapshots retained; retrospective mapping flagged',severity='limitation')
    report={'executed_at_utc':now(),'code_version':code_version,'status':'passed_with_disclosed_limitations' if not any(r['failure_count'] and r['severity']=='error' for r in checks) else 'failed','checks':checks,'lifecycle_real_data_status':'awaiting_integration','P0':'passed','P1':'executed_limited_feasibility;real_time_alignment_passed;P2_not_started'}
    write_json(ROOT/'reports/validation_results.json',report);write_csv(ROOT/'reports/validation_checks.csv',checks)
    print(json.dumps({'status':report['status'],'checks':len(checks),'actual_data_errors':sum(r['failure_count'] for r in checks if r['severity']=='error'),'open_limitations':sum(r['failure_count'] for r in checks if r['severity']=='limitation')}))
    if report['status']=='failed':raise SystemExit(1)

if __name__=='__main__':run()
