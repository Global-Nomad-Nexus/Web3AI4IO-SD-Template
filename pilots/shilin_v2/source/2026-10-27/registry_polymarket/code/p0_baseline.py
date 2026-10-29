"""Read-only import of legacy six tables, identity crosswalk and anomaly audit."""
import collections
import importlib.util
import json
import sys
from common import *

TABLES=['launch_events','observation_plan','request_attempts','response_snapshots','field_observations','coverage_ledger']
SOURCE_RELEASE='legacy_7day_20261008'

def run():
    started=now();inputs=list(RELEASE.iterdir())+list((LEGACY/'data/7day-72h-20261008-protocol').iterdir())
    inputs=[p for p in inputs if p.is_file()]
    before={str(p):sha(p) for p in inputs}
    audit_path=LEGACY/'analysis/rq_feasibility_audit.py'
    spec=importlib.util.spec_from_file_location('legacy_audit',audit_path)
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    old=audit.audit(RELEASE,LEGACY);audit.check_reference(old)
    write_json(ROOT/'reports/legacy_rq_audit.json',old)
    tables={name:read_csv(RELEASE/(name+'.csv')) for name in TABLES}
    ev=tables['launch_events']; plans={(r['event_key'],r['checkpoint']):r for r in tables['observation_plan']}
    attempts=collections.defaultdict(list)
    for r in tables['request_attempts']:attempts[r['request_id']].append(r)
    snaps={r['request_id']:r for r in tables['response_snapshots']}
    xwalk=[];registry=[];creation=[];anomalies=[]
    t0={r['event_key']:r['scheduled_at'] for r in tables['observation_plan'] if r['checkpoint']=='T0'}
    protocol=json.loads((LEGACY/'data/7day-72h-20261008-protocol/mvp_protocol.json').read_text())
    program=protocol['pumpfun_program_id']
    for i,r in enumerate(ev,2):
        token=token_id('solana:mainnet',r['mint']);cid='creation:'+sid('solana:mainnet',r['transaction_signature'],r['outer_instruction_index'],r['inner_instruction_index'])
        ref=f'legacy:launch_events.csv#row={i}'
        xwalk.append({'source_release':SOURCE_RELEASE,'legacy_event_key':r['event_key'],'network_raw':r['network'],'mint_raw':r['mint'],'token_id':token,'creation_event_id':cid,'conversion_rule':'case_preserving_solana_v1','verification_status':'legacy_identity_import_not_independent_chain_validation'})
        base={'token_id':token,'chain_key':'solana:mainnet','platform_id':'pump.fun','platform_version_id':'pumpfun_legacy_decoder_v2_historical_bounds_unknown','program_or_factory_address':program,'token_address_raw':r['mint'],'token_address_canonical':r['mint'],'creation_event_id':cid,'creation_tx_hash_or_signature':r['transaction_signature'],'block_height_or_slot':r['slot'],'block_hash':'','created_at_utc':iso(r['block_time']),'block_time_status':'legacy_chain_epoch_seconds','outer_instruction_index':r['outer_instruction_index'],'inner_instruction_index':r['inner_instruction_index'],'creator_address':r['creator'],'creator_role_definition':'legacy_create_argument_creator_not_tx_sender','tx_sender_or_signer':'','fee_payer':'','initial_name':'','initial_symbol':'','initial_metadata_uri':r['metadata_uri'],'initial_attributes_status':'name_symbol_not_exported_in_legacy','discovery_mode':'legacy_import','first_decoded_at_utc':t0[r['event_key']],'first_decoded_time_basis':'legacy_T0_scheduled_at_collector_clock','retrieved_at_utc':'','imported_at_utc':started,'decoder_version':r['decoder_version'],'raw_ref':'','source_row_ref':ref,'source_id':SOURCE_RELEASE,'validation_status':'legacy_import_chain_revalidation_pending','cohort_id':SOURCE_RELEASE,'execution_status_legacy':r['event_status']}
        creation.append(base.copy()); registry.append(base)
    write_csv(ROOT/'processed/token_id_crosswalk.csv',xwalk)
    write_csv(ROOT/'processed/registry.csv',registry)
    write_csv(ROOT/'processed/creation_events.csv',creation)
    coverage=[]
    for r in tables['coverage_ledger']:
        p=plans[(r['event_key'],r['checkpoint'])];a=attempts.get(r['request_id'],[]);snap=snaps.get(r['request_id'])
        times=[x['completed_at'] for x in a if x['completed_at']]
        missing=r['request_state']=='success' and not snap
        if missing:anomalies.append({'case_id':'missing_snapshot:'+sid(r['event_key'],r['checkpoint']),'case_type':'successful_checkpoint_missing_snapshot','legacy_event_key':r['event_key'],'request_id':r['request_id'],'transaction_signature':'','checkpoint':r['checkpoint'],'known_count':1,'status':'evidence_missing','evidence_ref':'legacy:coverage_ledger.csv;request_attempts.csv;response_snapshots.csv','detail':'Legacy request_state success; no selected response snapshot. Original terminal state retained; historical body/cluster logs needed.'})
        coverage.append({**r,'source_release':SOURCE_RELEASE,'token_id':'', 'scheduled_at_utc':p['scheduled_at'],'earliest_allowed_at_utc':p['earliest_allowed_at'],'actual_completed_at_utc':snap['retrieved_at'] if snap else (max(times) if times else ''),'time_basis':'T0_first_decoded;T24_T48_T72_block_time_offset','evidence_status':'evidence_missing' if missing else 'legacy_tables_only_raw_body_unavailable'})
    token_lookup={r['legacy_event_key']:r['token_id'] for r in xwalk}
    created={r['token_id']:epoch(r['created_at_utc']) for r in registry}
    for r in coverage:
        r['token_id']=token_lookup[r['event_key']]
        r['delay_from_creation_seconds']='' if not r['actual_completed_at_utc'] else round(epoch(r['actual_completed_at_utc'])-created[r['token_id']],3)
    write_csv(ROOT/'processed/metadata_coverage.csv',coverage)
    anomalies.append({'case_id':'unfetched_chain_transactions_4','case_type':'unfetched_chain_transactions','legacy_event_key':'','request_id':'','transaction_signature':'','checkpoint':'','known_count':4,'status':'identifiers_missing_requires_original_cluster_logs','evidence_ref':'legacy:validation_results.json;protocol:progress.json','detail':'Four transactions reported; two error sentences describe the same four. No exact signatures available in retained exception report; do not fabricate IDs.'})
    for code,detail in [('unknown_full_window_coverage','No independent whole-window enumeration performed; 4668 is enrolled cohort, not platform total.'),('raw_response_bodies_absent','No historical response_bodies.jsonl in legacy seven-day package; hashes cannot be recomputed from bodies.'),('legacy_request_jsonl_omitted','Original manifest lists request_attempts.jsonl; CSV retained, JSONL intentionally omitted.'),('uri_selection_bias_risk','Legacy decoder skipped empty URI; omitted qualified creation count is unknown.'),('platform_historical_bounds_unknown','ABI/IDL historical applicability is not established by source revision alone.')]:
        anomalies.append({'case_id':code,'case_type':code,'legacy_event_key':'','request_id':'','transaction_signature':'','checkpoint':'','known_count':'','status':'open','evidence_ref':'legacy:README.txt;code-7day-72h/mvp/acquire_chain.py','detail':detail})
    write_csv(ROOT/'reports/unresolved_cases.csv',anomalies)
    manifest=json.loads((RELEASE/'release_manifest.json').read_text())
    declared={r['path']:r for r in manifest['files']}
    inventory=[]
    for p in inputs:
        item={'path':str(p),'relative_to_legacy':str(p.relative_to(LEGACY)),'bytes':p.stat().st_size,'sha256':before[str(p)],'rows':len(tables[p.stem]) if p.stem in tables else '', 'manifest_hash_matches':sha(p)==declared[p.name]['sha256'] if p.name in declared else 'not_declared'}
        inventory.append(item)
    checks={'six_table_reference_counts':{k:len(tables[k]) for k in TABLES},'event_keys_unique':len({r['event_key'] for r in ev})==len(ev),'registry_unique':len({r['token_id'] for r in registry})==4668,'crosswalk_total':len(xwalk),'distinct_creators':len({r['creator'] for r in ev}),'window_violations':sum(not 1791417600<=int(r['block_time'])<1792022400 for r in ev),'missing_selected_snapshots':sum(r['case_type']=='successful_checkpoint_missing_snapshot' for r in anomalies),'all_legacy_files_unchanged':all(sha(p)==before[str(p)] for p in inputs),'reference_aggregate_check':'passed','raw_body_replay':'unavailable','independent_window_enumeration':'not_run_P3B'}
    write_json(ROOT/'reports/baseline_audit.json',{'started_at_utc':started,'finished_at_utc':now(),'inputs':inventory,'checks':checks,'legacy_validation':json.loads((RELEASE/'validation_results.json').read_text()),'status':'P0_A_passed' if checks['registry_unique'] and checks['event_keys_unique'] and checks['all_legacy_files_unchanged'] and checks['window_violations']==0 else 'failed'})
    # Column dictionary covers every legacy field; retain literal raw types for precision.
    grains={'launch_events':'one enrolled creation','observation_plan':'event x checkpoint','request_attempts':'request x route/attempt (policy refusals included)','response_snapshots':'one stored response snapshot','field_observations':'request x extracted field','coverage_ledger':'event x checkpoint terminal state'}
    descriptions={'event_key':'Original chain/signature/instruction key; retain for lineage','block_time':'Chain block timestamp, Unix seconds','mint':'Solana token mint, base58 case preserved','creator':'Creator decoded by legacy implementation, not assumed transaction sender','scheduled_at':'T0 collector first-decoded clock; other checkpoints block timestamp plus offset','started_at':'Actual request start; blank for policy refusal','completed_at':'Actual request completion; blank when no network request','retrieved_at':'Historical response retrieval time','available_at':'Legacy availability timestamp; not a newly observed creation time','presence':'Key presence; present may have JSON null','allowed_value':'Publication-safe extracted value; may be intentionally blank','value_hash':'Legacy digest of extracted value','request_id':'Legacy request key linking attempts/snapshot/fields; route retries may share it','response_sha256':'Digest recorded by legacy collector; historical body absent','final_state':'Legacy terminal state; not reinterpreted as token lifecycle','status':'Legacy request outcome; route refusal can precede network call','inner_instruction_index':'Legacy convention: 0 outer, inner index+1 nested','outer_instruction_index':'Zero-based outer instruction index'}
    dictionary=[]
    for table,rows in tables.items():
        for col in rows[0]:
            vals=sorted({r[col] for r in rows})
            dictionary.append({'table':table,'column':col,'dtype':'string_raw','row_grain':grains[table],'definition':descriptions.get(col,'Retained legacy '+col.replace('_',' ')+'; no inferred replacement'),'unit':'seconds_since_epoch' if col=='block_time' else ('bytes' if col=='response_bytes' else ''),'timezone':'UTC' if col.endswith('_at') or col=='block_time' else '', 'allowed_values':' | '.join(vals) if len(vals)<18 and max(map(len,vals),default=0)<100 else 'source_literal','null_reason':'blank preserved; not zero; may mean not exported, no request or not applicable (consult row status)','derivation':'identity read from original CSV','source':str(RELEASE/(table+'.csv')),'primary_or_foreign_key':('PK/FK legacy' if col in ['event_key','request_id','checkpoint','field_name'] else ''),'version':'legacy_import_v1'})
    write_csv(ROOT/'configs/legacy_six_table_dictionary.csv',dictionary)
    # Deterministic address-level creator concentration preview data and SVG.
    counts=sorted(collections.Counter(r['creator'] for r in ev).values(),reverse=True);total=sum(counts);cumulative=0;curve=[]
    for rank,n in enumerate(counts,1):
        cumulative+=n;curve.append({'creator_rank':rank,'creator_fraction':rank/len(counts),'enrolled_creation_count':n,'cumulative_creation_fraction':cumulative/total})
    write_csv(ROOT/'figures/data/panel_D_creator_concentration.csv',curve)
    points=' '.join(f'{70+640*r["creator_fraction"]:.2f},{420-340*r["cumulative_creation_fraction"]:.2f}' for r in curve)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="510" viewBox="0 0 800 510"><rect width="800" height="510" fill="white"/><text x="65" y="32" font-family="sans-serif" font-size="20">Legacy cohort: creator-address concentration</text><path d="M70 80 V420 H710" fill="none" stroke="#222"/><path d="M70 420 L710 80" stroke="#aaa" stroke-dasharray="6 4"/><polyline points="70,420 {points}" fill="none" stroke="#216f99" stroke-width="3"/><text x="260" y="460" font-family="sans-serif">Creators ranked by enrolled creations (0–100%)</text><text x="65" y="490" font-family="sans-serif" font-size="13">4,668 enrolled events · 2,993 addresses · coverage partial · addresses are not people</text><text x="12" y="70" font-family="sans-serif">100%</text><text x="35" y="425" font-family="sans-serif">0</text></svg>'
    (ROOT/'figures/panel_D_preview.svg').write_text(svg)
    print(json.dumps(checks,ensure_ascii=False))

if __name__=='__main__':run()
