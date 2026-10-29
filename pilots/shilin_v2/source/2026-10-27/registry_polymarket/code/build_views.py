"""Offline, strict bucket-END-before-creation joins; preserve every registry token."""
import bisect
import collections
import sys
from common import *

def eligible_price(sorted_prices, information_end_times, anchor, max_age_hours=24):
    """Select strictly prior completed information; same-second end is excluded."""
    index=bisect.bisect_left(information_end_times,anchor)-1
    while index>=0:
        p=sorted_prices[index]
        if anchor-information_end_times[index]>max_age_hours*3600:return None
        if str(p['eligible_for_asof']).lower()=='true' and 0<=float(p['price'])<=1:return p
        index-=1
    return None

def run():
    registry=read_csv(ROOT/'processed/registry.csv');markets=read_csv(ROOT/'processed/pm_markets.csv');outcomes=read_csv(ROOT/'processed/pm_outcomes.csv');prices=read_csv(ROOT/'processed/pm_prices.csv')
    # Reuse legacy decoder only on successfully executed, jsonParsed transactions with
    # the exact registered legacy version; do not claim general version compatibility.
    sys.path.insert(0,str(LEGACY/'code-7day-72h'))
    from mvp.acquire_chain import decode_transaction
    samples=[]
    for tag in ['start','mid','end']:
        path=ROOT/f'reports/solana_{tag}_transaction_check.json'
        if not path.exists():continue
        check=json.loads(path.read_text());native=json.loads((ROOT/check['raw_ref']).read_text());tx=native.get('result')
        source=next(r for r in read_csv(RELEASE/'launch_events.csv') if r['event_key']==check['legacy_event_key'])
        if not tx or tx.get('meta',{}).get('err') is not None:continue
        decoded=decode_transaction(native,source['transaction_signature'],tx['blockTime'])
        matches=[d for d in decoded if d['event_key']==source['event_key'] and d['mint']==source['mint'] and d['creator']==source['creator']]
        samples.append({'legacy_event_key':source['event_key'],'token_id':'solana:mainnet:token:'+source['mint'],'created_at_utc':iso(tx['blockTime']),'slot_matches':str(tx.get('slot'))==source['slot'],'creator_and_mint_and_native_position_match':len(matches)==1,'execution_succeeded':True,'transaction_version':tx.get('version'),'raw_ref':check['raw_ref'],'decoder_version':source['decoder_version'],'scope':'three predetermined boundary samples; not full cohort native validation'})
    write_csv(ROOT/'reports/verified_creation_samples.csv',samples)
    market=next((m for m in markets if m['market_id']=='2589811'),None)
    mapping=[];joined=[];daily=[];sensitivity=[]
    if market:
        outcome=next(o for o in outcomes if o['market_snapshot_id']==market['market_snapshot_id'] and o['outcome_index']=='0')
        mapping_id='mapping:'+sid('shared_economic_event','fomc:2026-10-28',outcome['pm_outcome_key'])
        mapping=[{'mapping_id':mapping_id,'link_type':'shared_economic_event','target_type':'economic_event','target_id':'fomc:2026-10-28','applicable_chain_keys':'solana:mainnet|eip155:8453|eip155:56','pm_market_key':market['pm_market_key'],'pm_outcome_key':outcome['pm_outcome_key'],'market_snapshot_id':market['market_snapshot_id'],'rule_snapshot_ref':market['rules_ref'],'evidence_ref':market['raw_ref'],'semantic_valid_from_utc':market['opened_at_utc'],'semantic_valid_to_utc':market['scheduled_close_at_utc'],'rule_known_from_utc':'','mapping_created_at_utc':now(),'reviewed_by':'Codex_local_evidence_review','review_status':'retrospective_mapping','uncertainty':'Historical rule revision archive unavailable. Mapping is common macro background, not individual token forecast; not certified as fully contemporaneously specified prediction feature.'}]
        seq=sorted([p for p in prices if p['pm_outcome_key']==outcome['pm_outcome_key'] and p['eligible_for_asof']=='True'],key=lambda r:epoch(r['effective_information_time_utc']))
        end_times=[epoch(p['effective_information_time_utc']) for p in seq]
        def choose(anchor,age):
            if not epoch(market['opened_at_utc'])<=anchor<epoch(market['scheduled_close_at_utc']):return None
            return eligible_price(seq,end_times,anchor,age)
        for r in registry:
            anchor=epoch(r['created_at_utc']);p=choose(anchor,24)
            joined.append({'expectation_link_id':'expectation:'+sid(r['token_id'],mapping_id),'token_id':r['token_id'],'creation_event_id':r['creation_event_id'],'mapping_id':mapping_id,'price_observation_id':p['price_observation_id'] if p else '', 'anchor_time_utc':r['created_at_utc'],'price':p['price'] if p else '', 'source_timestamp_utc':p['source_timestamp_utc'] if p else '', 'bucket_start_utc':p['bucket_start_utc'] if p else '', 'bucket_end_utc':p['bucket_end_utc'] if p else '', 'effective_information_time_utc':p['effective_information_time_utc'] if p else '', 'price_age_hours':round((anchor-epoch(p['effective_information_time_utc']))/3600,6) if p else '', 'is_stale':False if p else '', 'source_retrieved_at_utc':p['source_retrieved_at_utc'] if p else '', 'time_semantics_status':'strict_bucket_end_before_anchor_official_OpenAPI','match_status':'matched_valid' if p else 'history_unavailable_or_stale','link_type':'shared_economic_event','feature_readiness':'retrospective_demonstration_only_rule_revision_unverified','direct_identity_match':False})
        for age in [12,24,48]:sensitivity.append({'max_price_age_hours':age,'matched_creation_tokens':sum(choose(epoch(r['created_at_utc']),age) is not None for r in registry),'registry_tokens':len(registry),'selection_rule':'strict_information_end_before_creation;settlement/exact0_ticks_excluded'})
        for chain,platform in [('solana:mainnet','pump.fun'),('eip155:8453','clanker'),('eip155:56','four.meme')]:
            for t in range(1791417600,1792022400,86400):
                p=choose(t,24);count=sum(r['chain_key']==chain and t<=epoch(r['created_at_utc'])<t+86400 for r in registry)
                daily.append({'chain_key':chain,'platform_id':platform,'utc_day':iso(t)[:10],'market_key':market['pm_market_key'],'outcome_key':outcome['pm_outcome_key'],'link_type':'shared_economic_event','anchor_time_utc':iso(t),'expectation_available':p is not None,'price':p['price'] if p else '', 'effective_information_time_utc':p['effective_information_time_utc'] if p else '', 'legacy_enrolled_creation_count':count if chain=='solana:mainnet' else '', 'creation_coverage':'legacy_partial' if chain=='solana:mainnet' else 'not_collected_P2','background_scope':'same common macro event;not_three_independent_forecasts'})
    else:
        joined=[{'expectation_link_id':'expectation:'+sid(r['token_id'],'unmatched'),'token_id':r['token_id'],'mapping_id':'','price_observation_id':'','match_status':'no_candidate'} for r in registry]
    write_csv(ROOT/'processed/pm_mapping.csv',mapping)
    write_csv(ROOT/'processed/token_expectations_at_creation.csv',joined)
    write_csv(ROOT/'processed/context_daily.csv',daily)
    write_csv(ROOT/'reports/price_age_sensitivity.csv',sensitivity)
    verified={s['token_id'] for s in samples if s['creator_and_mint_and_native_position_match']}
    valid=[r for r in joined if r['match_status']=='matched_valid']
    example=next((r for r in valid if r['token_id'] in verified),None)
    write_json(ROOT/'reports/real_asof_example.json',{'example':example,'creation_native_evidence':next((s for s in samples if example and s['token_id']==example['token_id']),None),'mapping':mapping[0] if mapping else None,'status':'real_price_time_alignment_demonstrated' if example else 'not_demonstrated','strict_contemporaneous_rule_feature_status':'not_certified_historical_rule_revisions_unavailable','price_definition':'API history scalar, not asserted trade/midpoint; market expectation proxy only'})
    write_csv(ROOT/'reports/coverage_summary.csv',[
      {'metric':'direct_token_identity_match','numerator':0,'denominator':len(registry),'unit':'tokens','scope':'no verified direct token-identity mapping established'},
      {'metric':'creation_anchor_background_coverage','numerator':len(valid),'denominator':len(registry),'unit':'tokens','scope':'legacy Solana; retrospective shared macro demonstration'},
      {'metric':'common_macro_background_day_coverage','numerator':sum(r['expectation_available'] for r in daily),'denominator':len(daily),'unit':'chain_platform_days','scope':'declared 3x7 grid; creation completeness not implied'},
      {'metric':'jointly_complete_creation_and_background_days','numerator':0,'denominator':len(daily),'unit':'chain_platform_days','scope':'no chain has completed whole-window enumeration in P0/P1'}])
    print(json.dumps({'registry_tokens':len(registry),'joined_distinct_tokens':len({r['token_id'] for r in joined}),'valid_background_tokens':len(valid),'native_revalidated_examples':len(verified),'example':bool(example)}))

if __name__=='__main__':run()
