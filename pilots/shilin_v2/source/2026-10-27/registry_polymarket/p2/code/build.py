"""Build P2 Registry-to-expectation views and honest full-window coverage."""
from p2io import *
from collections import Counter
import bisect

def run():
    cfg=json.loads((ROOT/'configs/pilot_protocol.json').read_text());registry=read_csv(ROOT/'processed/registry.csv')
    market=next(r for r in read_csv(PARENT/'processed/pm_markets.csv') if r['market_id']=='2589811')
    outs=[r for r in read_csv(PARENT/'processed/pm_outcomes.csv') if r['market_snapshot_id']==market['market_snapshot_id']]
    yes=next(r for r in outs if r['outcome_label']=='Yes')
    prices=[r for r in read_csv(PARENT/'processed/pm_prices.csv') if r['pm_outcome_key']==yes['pm_outcome_key']]
    for r in [market]+outs+prices:
        for key in ['raw_ref','rules_ref']:
            if r.get(key):r[key]='../'+r[key]
    write_csv(ROOT/'processed/pm_markets.csv',[market]);write_csv(ROOT/'processed/pm_outcomes.csv',outs);write_csv(ROOT/'processed/pm_prices.csv',prices)
    mapping=read_csv(PARENT/'processed/pm_mapping.csv')[0].copy()
    for key in ['evidence_ref','rule_snapshot_ref']:mapping[key]='../'+mapping[key]
    write_csv(ROOT/'processed/pm_mapping.csv',[mapping])
    seq=sorted([r for r in prices if r['eligible_for_asof']=='True'],key=lambda r:epoch(r['effective_information_time_utc']));times=[epoch(r['effective_information_time_utc']) for r in seq]
    joined=[]
    for r in registry:
        t=epoch(r['created_at_utc']);index=bisect.bisect_left(times,t)-1;p=seq[index] if index>=0 else None
        valid=p is not None and 0<t-epoch(p['effective_information_time_utc'])<=86400 and epoch(market['opened_at_utc'])<=t<epoch(market['scheduled_close_at_utc'])
        joined.append({'expectation_link_id':'expectation:'+sid(r['token_id'],mapping['mapping_id']),'token_id':r['token_id'],'chain_key':r['chain_key'],'creation_event_id':r['creation_event_id'],'mapping_id':mapping['mapping_id'],'pm_outcome_key':yes['pm_outcome_key'],'price_observation_id':p['price_observation_id'] if valid else '', 'anchor_time_utc':r['created_at_utc'],'source_timestamp_utc':p['source_timestamp_utc'] if valid else '', 'bucket_start_utc':p['bucket_start_utc'] if valid else '', 'bucket_end_utc':p['bucket_end_utc'] if valid else '', 'effective_information_time_utc':p['effective_information_time_utc'] if valid else '', 'price':p['price'] if valid else '', 'price_age_hours':round((t-epoch(p['effective_information_time_utc']))/3600,6) if valid else '', 'match_status':'matched_valid' if valid else 'history_unavailable_or_stale','link_type':'shared_economic_event','feature_readiness':'retrospective_demonstration_only_rule_revision_unverified','is_direct_token_identity_match':False})
    write_csv(ROOT/'processed/token_expectations_at_creation.csv',joined)
    write_csv(ROOT/'processed/pm_match_status.csv',[{'match_assessment_id':'assessment:'+sid(r['token_id'],'shared_economic_event',r['anchor_time_utc']),'token_id':r['token_id'],'anchor_time_utc':r['anchor_time_utc'],'link_type':r['link_type'],'status':r['match_status'],'primary_reason':'valid_historical_bucket_time_for_retrospective_demo' if r['match_status']=='matched_valid' else r['match_status']} for r in joined])
    # Closed union of successful segments only; failed attempts remain visible separately.
    coverage=[];gaps=[]
    for chain,(start,end) in cfg['chain_bounds_inclusive_start_exclusive_end'].items():
        if chain=='eip155:8453' and (ROOT/'reports/base_rpc_query_ledger.csv').exists():files=[ROOT/'reports/base_rpc_query_ledger.csv']
        else:files=[ROOT/'reports'/('query_ledger_'+chain.replace(':','_')+'.csv')]
        segments=[];failures=0
        for file in files:
            for s in read_csv(file) if file.exists() else []:
                if s['chain_key']!=chain:continue
                if s['status']=='complete_segment':segments.append((int(s['from_block']),int(s['scanned_through'])))
                else:failures+=1
        cursor=start
        for a,b in sorted(set(segments)):
            if a>cursor:gaps.append({'chain_key':chain,'from_block_inclusive':cursor,'to_block_exclusive':a,'reason':'not_successfully_enumerated'})
            cursor=max(cursor,b+1)
        if cursor<end:gaps.append({'chain_key':chain,'from_block_inclusive':cursor,'to_block_exclusive':end,'reason':'not_successfully_enumerated'})
        missing=sum(g['to_block_exclusive']-g['from_block_inclusive'] for g in gaps if g['chain_key']==chain)
        complete=not missing;method='full_native_position_interval_filtered_query_union';candidate_denominator='';resolved_candidates=''
        solpath=ROOT/'reports/solana_native_creation_receipt.json'
        if chain=='solana:mainnet' and solpath.exists():
            sol=json.loads(solpath.read_text());vr=json.loads((ROOT/'reports/vibe_history_receipt.json').read_text())
            complete=sol['status']=='passed_complete_native_creation_resolution' and vr['status']=='passed_complete_cross_source_candidate_set' and sol['full_native_transactions']==vr['full_transactions']
            method='complete_mandatory_creation_PDA_transaction_index_and_full_native_transaction_resolution';candidate_denominator=vr['full_transactions'];resolved_candidates=sol['full_native_transactions'] if complete else ''
        coverage.append({'chain_key':chain,'window_start_utc':cfg['creation_start_utc'],'window_end_utc':cfg['creation_end_utc'],'from_block_or_slot_inclusive':start,'to_block_or_slot_exclusive':end,'declared_positions':end-start,'positions_covered_by_successful_query_union':end-start-missing,'positions_not_yet_enumerated':missing,'coverage_status':'complete_for_declared_address_topic_scope' if complete else 'partial','creation_scope_complete':complete,'enumeration_method':method,'native_index_candidate_denominator':candidate_denominator,'native_candidates_resolved':resolved_candidates,'admitted_unique_tokens':sum(r['chain_key']==chain for r in registry),'source_query_failed_attempts':failures,'creation_scope':'frozen named factories/discriminators; not all token launches on the chain','position_scan_note':'SQD slot scan remains partial and is not the final completeness unit' if chain=='solana:mainnet' and complete and missing else 'Native position scan is the enumeration unit'})
    write_csv(ROOT/'reports/coverage.csv',coverage);write_csv(ROOT/'reports/remaining_ranges.csv',gaps,['chain_key','from_block_inclusive','to_block_exclusive','reason'])
    daily=[]
    platform_by_chain={'solana:mainnet':'pump.fun','eip155:8453':'clanker','eip155:56':'four.meme'}
    for c in coverage:
        subset=[r for r in registry if r['chain_key']==c['chain_key']];matches=[r for r in joined if r['chain_key']==c['chain_key'] and r['match_status']=='matched_valid']
        daily.append({'chain_key':c['chain_key'],'platform_id':platform_by_chain[c['chain_key']],'utc_day':'2026-10-08','admitted_unique_tokens':len(subset),'creation_coverage_status':c['coverage_status'],'valid_background_token_anchors':len(matches),'anchor_denominator':len(subset),'direct_identity_token_matches':0,'direct_identity_denominator':len(subset),'direct_identity_anchor_valid_count':0,'whole_day_complete':c['creation_scope_complete']})
    write_csv(ROOT/'reports/integration_coverage.csv',daily)
    anchor=1791417600;index=bisect.bisect_left(times,anchor)-1;day_price=seq[index] if index>=0 else None
    day_valid=day_price is not None and 0<anchor-epoch(day_price['effective_information_time_utc'])<=86400 and epoch(market['opened_at_utc'])<=anchor<epoch(market['scheduled_close_at_utc'])
    context=[]
    for c in coverage:
        complete=c['creation_scope_complete']
        context.append({'chain_key':c['chain_key'],'platform_id':platform_by_chain[c['chain_key']],'utc_day':'2026-10-08','anchor_time_utc':iso(anchor),'pm_outcome_key':yes['pm_outcome_key'],'mapping_id':mapping['mapping_id'],'price_observation_id':day_price['price_observation_id'] if day_valid else '', 'expectation_at_day_start':day_price['price'] if day_valid else '', 'effective_information_time_utc':day_price['effective_information_time_utc'] if day_valid else '', 'match_status':'matched_valid' if day_valid else 'history_unavailable_or_stale_or_market_inactive','observed_created_tokens':c['admitted_unique_tokens'],'full_day_declared_scope_creation_count':c['admitted_unique_tokens'] if complete else '', 'creation_coverage_status':c['coverage_status'],'link_type':'shared_economic_event','feature_readiness':'retrospective_demonstration_only'})
    write_csv(ROOT/'processed/context_daily.csv',context)
    write_csv(ROOT/'reports/background_day_coverage.csv',[{'chain_key':r['chain_key'],'platform_id':r['platform_id'],'utc_day':r['utc_day'],'background_available_numerator':int(day_valid),'declared_day_grid_denominator':1,'creation_window_complete':r['full_day_declared_scope_creation_count']!='','jointly_analyzable_numerator':int(day_valid and r['full_day_declared_scope_creation_count']!=''),'semantic_limit':'retrospective shared macro context'} for r in context])
    write_csv(ROOT/'reports/market_history_anchor_coverage.csv',[{'market_id':market['market_id'],'pm_outcome_key':yes['pm_outcome_key'],'eligible_interval_start_utc':cfg['creation_start_utc'],'eligible_interval_end_exclusive_utc':cfg['creation_end_utc'],'valid_daily_anchors_numerator':int(day_valid),'expected_daily_anchors_denominator':1,'before_open_count':int(anchor<epoch(market['opened_at_utc'])),'after_validity_count':int(anchor>=epoch(market['scheduled_close_at_utc'])),'history_missing_or_stale_count':int(not day_valid and epoch(market['opened_at_utc'])<=anchor<epoch(market['scheduled_close_at_utc']))}])
    sensitivity=[]
    for age in [12,24,48]:
        for c in coverage:
            cohort=[r for r in registry if r['chain_key']==c['chain_key']];available=0
            for r in cohort:
                t=epoch(r['created_at_utc']);i=bisect.bisect_left(times,t)-1
                available+=int(i>=0 and 0<t-times[i]<=age*3600 and epoch(market['opened_at_utc'])<=t<epoch(market['scheduled_close_at_utc']))
            sensitivity.append({'chain_key':c['chain_key'],'link_type':'shared_economic_event','max_price_age_hours':age,'valid_numerator':available,'token_denominator':len(cohort),'time_rule':'information_end_strictly_before_creation','scope_note':'Each age threshold independently evaluated against all fixed historical price observations.'})
    write_csv(ROOT/'reports/price_age_sensitivity.csv',sensitivity)
    samples=[]
    for chain in cfg['chain_bounds_inclusive_start_exclusive_end']:
        by_id={r['token_id']:r for r in joined}
        for r in sorted([x for x in registry if x['chain_key']==chain],key=lambda x:(x['created_at_utc'],x['token_id']))[:10]:samples.append({**r,**by_id[r['token_id']]})
    write_csv(ROOT/'reports/three_chain_display_samples.csv',samples)
    # Only the frozen pilot day is compared; this is not the deferred whole-week P3B audit.
    legacy=read_csv(PARENT/'processed/registry.csv');current={r['token_id']:r for r in registry};overlap=[]
    sol_complete=next(c for c in coverage if c['chain_key']=='solana:mainnet')['creation_scope_complete']
    for old in legacy:
        if not 1791417600<=epoch(old['created_at_utc'])<1791504000:continue
        new=current.get(old['token_id'])
        overlap.append({'token_id':old['token_id'],'legacy_creation_event_id':old['creation_event_id'],'P2_creation_event_id':new['creation_event_id'] if new else '', 'native_transaction_same':old['creation_tx_hash_or_signature']==new['creation_tx_hash_or_signature'] if new else '', 'created_at_same':old['created_at_utc']==new['created_at_utc'] if new else '', 'creator_same':old['creator_address']==new['creator_address'] if new else '', 'status':'same_token_native_event_linked' if new else ('not_found_in_completed_declared_P2_scope' if sol_complete else 'not_yet_observed_in_partial_P2'),'event_ID_note':'P0 flattened legacy position hash and P2 native call-tree hash are different versioned derivations; token_id is stable.','metadata_observation_policy':'No legacy checkpoint completion copied onto newly backfilled tokens.'})
    write_csv(ROOT/'reports/legacy_day_identity_comparison.csv',overlap)
    # Preview source tables (partial coverage stays explicit).
    write_csv(ROOT/'figures/data/panel_A_activity.csv',daily)
    write_csv(ROOT/'figures/data/panel_B_coverage.csv',coverage)
    write_csv(ROOT/'figures/data/panel_C_links.csv',[{'link_type':'shared_economic_event','market_count':1,'mapping_count':1,'token_anchor_count':sum(r['match_status']=='matched_valid' for r in joined),'direct_token_identity_count':0}])
    unresolved_creation_scopes=[{'chain_key':c['chain_key'],'reason':'declared creation enumeration incomplete','enumeration_method':c['enumeration_method']} for c in coverage if not c['creation_scope_complete']]
    write_csv(ROOT/'reports/remaining_creation_gaps.csv',unresolved_creation_scopes,['chain_key','reason','enumeration_method'])
    write_json(ROOT/'reports/build_receipt.json',{'created_at_utc':now(),'registry_tokens':len(registry),'expectation_rows':len(joined),'joined_distinct_tokens':len({r['token_id'] for r in joined}),'coverage_complete_chains':sum(c['creation_scope_complete'] for c in coverage),'status':'complete' if all(c['creation_scope_complete'] for c in coverage) else 'partial_data_do_not_claim_P2_complete','slot_scan_vs_candidate_resolution':'reports/remaining_ranges.csv retains old SQD slot scan gaps; reports/remaining_creation_gaps.csv is final declared creation enumeration gap list'})
    print(json.dumps({'tokens':len(registry),'coverage':[(c['chain_key'],c['coverage_status'],c['positions_not_yet_enumerated']) for c in coverage]}),flush=True)
if __name__=='__main__':run()
