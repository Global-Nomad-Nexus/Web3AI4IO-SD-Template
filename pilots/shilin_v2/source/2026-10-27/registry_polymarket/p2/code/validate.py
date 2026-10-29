"""P2 gate is fail-closed: partial chain coverage can never count as completion."""
from p2io import *
from collections import Counter

def run():
    tables={p.stem:read_csv(p) for p in (ROOT/'processed').glob('*.csv')};checks=[]
    version=sid(*[(p.name,sha(p)) for p in sorted((ROOT/'code').glob('*.py'))])
    def ck(name,tested,failed,refs='',kind='error'):
        checks.append({'check_id':name,'tested_count':tested,'failure_count':failed,'failure_refs':refs,'severity':kind,'status':'passed' if not failed else ('pending' if kind=='gate' else 'failed'),'executed_at_utc':now(),'code_version':version})
    registry=tables['registry'];events=tables['creation_events'];joins=tables['token_expectations_at_creation'];ids={r['token_id'] for r in registry};eids={r['creation_event_id'] for r in events}
    ck('registry_unique_token_identity',len(registry),len(registry)-len(ids));ck('creation_event_key_unique',len(events),len(events)-len(eids));ck('registry_event_FK',len(registry),sum(r['creation_event_id'] not in eids for r in registry))
    ck('frozen_UTC_window',len(events),sum(not 1791417600<=epoch(r['created_at_utc'])<1791504000 for r in events));ck('successful_committed_creations_only',len(events),sum(r['execution_status']!='success_committed' for r in events))
    cfg=json.loads((ROOT/'configs/pilot_protocol.json').read_text());ck('frozen_native_boundaries',len(events),sum(not cfg['chain_bounds_inclusive_start_exclusive_end'][r['chain_key']][0]<=int(r['block_height_or_slot'])<cfg['chain_bounds_inclusive_start_exclusive_end'][r['chain_key']][1] for r in events))
    ck('decode_errors',len(events),len(read_csv(ROOT/'reports/decode_errors.csv')));ck('conflicting_token_creation_not_dropped',len(events),len(read_csv(ROOT/'reports/creation_conflicts.csv')))
    ck('left_join_exact_token_set',len(ids),len(ids.symmetric_difference({r['token_id'] for r in joins})))
    ck('expectation_link_unique',len(joins),len(joins)-len({r['expectation_link_id'] for r in joins}));ck('unmatched_rows_have_reason',len(joins),sum(not r['match_status'] for r in joins))
    matched=[r for r in joins if r['match_status']=='matched_valid'];prices={r['price_observation_id']:r for r in tables['pm_prices']};maps={r['mapping_id']:r for r in tables['pm_mapping']}
    ck('price_mapping_foreign_keys',len(matched),sum(r['price_observation_id'] not in prices or r['mapping_id'] not in maps for r in matched))
    ck('strict_information_end_before_creation',len(matched),sum(epoch(r['effective_information_time_utc'])>=epoch(r['anchor_time_utc']) for r in matched));ck('maximum_price_age_24h',len(matched),sum(epoch(r['anchor_time_utc'])-epoch(r['effective_information_time_utc'])>86400 for r in matched))
    ck('no_settlement_or_ambiguous_zero_resolution_tick',len(matched),sum(int(prices[r['price_observation_id']]['resolution_seconds'])==0 for r in matched));ck('price_range',len(prices),sum(not 0<=float(r['price'])<=1 for r in prices.values()))
    ck('retrospective_feature_limit_preserved',len(matched),sum(r['feature_readiness']!='retrospective_demonstration_only_rule_revision_unverified' for r in matched))
    rawchecks=[]
    for p in (ROOT/'raw').glob('*.meta.json'):
        m=json.loads(p.read_text());rawchecks.append(sha(ROOT/m['raw_ref'])==m['sha256'])
    ck('saved_public_response_hashes',len(rawchecks),sum(not v for v in rawchecks))
    ck('no_backfilled_legacy_T0_clock',len(events),sum(bool(r['first_decoded_at_utc']) or r['discovery_mode']!='historical_backfill' for r in events))
    coverage=read_csv(ROOT/'reports/coverage.csv');ck('all_three_full_day_creation_enumerations_closed',3,sum(r['creation_scope_complete']!='True' for r in coverage),'reports/remaining_creation_gaps.csv;coverage.csv preserves separate original SQD position gaps','gate')
    sol_path=ROOT/'reports/solana_native_creation_receipt.json';sol=json.loads(sol_path.read_text()) if sol_path.exists() else {}
    vr=json.loads((ROOT/'reports/vibe_history_receipt.json').read_text()) if (ROOT/'reports/vibe_history_receipt.json').exists() else {}
    ck('Solana_complete_native_candidate_resolution',vr.get('full_transactions',0),int(sol.get('status')!='passed_complete_native_creation_resolution' or sol.get('full_native_transactions')!=vr.get('full_transactions') or vr.get('missing_from_Vibe',1) or vr.get('extra_from_Vibe',1)),'reports/solana_native_creation_receipt.json','gate')
    ck('Solana_native_archive_creation_identity_and_commitment',sol.get('archive_native_instruction_comparisons',0),sol.get('conflicts',0)+sol.get('decode_errors',0)+sol.get('unknown_commitment_instructions',0),'reports/solana_native_archive_conflicts.csv')
    ck('all_creation_block_hash_evidence_present',len(events),sum(not r['block_hash'] for r in events))
    ck('all_creation_native_transaction_and_header_refs_present',len(events),sum(not r['native_receipt_raw_ref'] or not r['native_block_raw_ref'] for r in events))
    ck('daily_background_strict_asof',len(tables['context_daily']),sum(bool(r['price_observation_id']) and (epoch(r['effective_information_time_utc'])>=epoch(r['anchor_time_utc']) or epoch(r['anchor_time_utc'])-epoch(r['effective_information_time_utc'])>86400) for r in tables['context_daily']))
    bsc=json.loads((ROOT/'reports/bsc_all_native_QA_receipt.json').read_text()) if (ROOT/'reports/bsc_all_native_QA_receipt.json').exists() else {}
    bsc_events=[r for r in events if r['chain_key']=='eip155:56']
    ck('every_BSC_creation_native_receipt_header_and_fields',len(bsc_events),int(bsc.get('status')!='passed' or bsc.get('cohort_event_ids_hash')!=sid(sorted(r['creation_event_id'] for r in bsc_events))),'reports/bsc_all_native_QA.csv','gate')
    ck('nonempty_real_creation_per_chain',3,3-len({r['chain_key'] for r in registry}),'','gate')
    ck('real_valid_expectation_per_chain',3,3-len({r['chain_key'] for r in matched}),'','gate')
    qa=json.loads((ROOT/'reports/native_QA_receipt.json').read_text()) if (ROOT/'reports/native_QA_receipt.json').exists() else {}
    ck('native_source_QA_failures',qa.get('archive_sample_checks',0),qa.get('archive_sample_failures',0))
    qa_rows=read_csv(ROOT/'reports/native_QA.csv') if (ROOT/'reports/native_QA.csv').exists() else []
    groups=Counter((r['chain_key'],r['platform_version_id']) for r in registry if r['chain_key']!='eip155:8453')
    sampled=Counter((r['chain_key'],r['platform_version_id']) for r in qa_rows if r['status']=='passed')
    ck('fixed_seed_native_QA_target_per_chain_version',sum(min(10,n) for n in groups.values()),sum(max(0,min(10,n)-sampled[g]) for g,n in groups.items()),'reports/native_QA.csv','gate')
    ck('real_lifecycle_disabled',1,int(cfg['lifecycle_enabled'] or cfg['common_cutoff_utc'] is not None))
    reproduction=json.loads((ROOT/'reports/offline_reproduction.json').read_text()) if (ROOT/'reports/offline_reproduction.json').exists() else {}
    from reproduce_offline import inputs,fingerprints
    replay_valid=reproduction.get('status')=='passed_for_fixed_checkpoint' and reproduction.get('input_hashes')==inputs() and reproduction.get('second_output_hashes')==fingerprints()
    ck('fixed_input_zero_network_reproduction',1,int(not replay_valid),'reports/offline_reproduction.json;current input and output hashes must still match','gate')
    test_log=(ROOT/'reports/unit_tests.log').read_text() if (ROOT/'reports/unit_tests.log').exists() else ''
    ck('isolated_decoder_and_commitment_boundary_tests',10,int('Ran 10 tests' not in test_log or not test_log.rstrip().endswith('OK')),'reports/unit_tests.log','gate')
    status='passed_for_declared_platform_version_scope' if all(not r['failure_count'] for r in checks) else ('failed' if any(r['failure_count'] and r['severity']=='error' for r in checks) else 'in_progress_not_P2_complete')
    write_csv(ROOT/'reports/validation_checks.csv',checks);write_json(ROOT/'reports/validation_results.json',{'status':status,'checks':checks,'execution_time_utc':now(),'code_version':version,'scope_exclusions':cfg['known_scope_exclusions'],'price_feature_limit':'retrospective demonstration; historical rule revisions and scalar price construction remain unverified','whole_platform_census_claim':False})
    print(json.dumps({'status':status,'checks':len(checks),'errors':sum(r['failure_count'] for r in checks if r['severity']=='error'),'pending_gate_failures':sum(r['failure_count'] for r in checks if r['severity']=='gate')}),flush=True)
if __name__=='__main__':run()
