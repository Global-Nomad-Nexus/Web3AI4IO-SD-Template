"""Small real-history feasibility layer, with raw API evidence and bounded search."""
import argparse
import collections
from urllib.parse import urlencode
from common import *

def array(v): return json.loads(v) if isinstance(v,str) else (v or [])

def run(refresh=False):
    c=EvidenceClient(refresh=refresh,budget=80)
    searches=[];candidates={};selected=[];markets=[];outcomes=[];prices=[];feasibility=[]
    terms=[('macro','Fed'),('solana','Solana October 2026'),('bnb','BNB October'),('pumpfun','Pump.fun'),('base','Base token')]
    write_csv(ROOT/'configs/market_search_terms.csv',[{'topic':topic,'term':term,'scope':'active_and_closed_separately','max_pages_per_status':2,'limit_per_type':3,'stop_rule':'hasMore false or page cap; capped search is not exhaustive'} for topic,term in terms])
    for topic,term in terms:
        for state in ['active','closed']:
            for page in [1,2]:
                params={'q':term,'events_status':state,'limit_per_type':3,'keep_closed_markets':1,'page':page}
                url='https://gamma-api.polymarket.com/public-search?'+urlencode(params)
                data,m=c.request(url,label=f'{topic}_{state}_page{page}')
                events=data.get('events',[]) if isinstance(data,dict) else []
                more=bool(data.get('pagination',{}).get('hasMore')) if isinstance(data,dict) else False
                searches.append({'query_id':m['request_id'],'term':term,'topic':topic,'source_url':url,'filters':json.dumps(params),'open_or_closed_scope':state,'protocol_version_filter':'none;native version retained','page':page,'retrieved_at_utc':m['retrieved_at_utc'],'returned_event_ids':'|'.join(str(e['id']) for e in events),'http_status':m['http_status'],'error':m['error'],'raw_ref':m['raw_ref'],'has_more':more,'stop_reason':'request_failed' if not m['ok'] else ('page_cap_reached_not_exhaustive' if more and page==2 else ('more_pages' if more else 'server_has_more_false'))})
                for e in events:
                    for mk in e.get('markets',[]):
                        candidates[str(mk['id'])]=(topic,e,mk,m)
                write_csv(ROOT/'reports/market_search_log.csv',searches)
                if not more or not m['ok']:break
    # Preselected economic contract, discovered from real Fed search. No selection on price behavior.
    e,em=c.request('https://gamma-api.polymarket.com/events/606422',label='Fed_October_2026_event_details')
    if isinstance(e,dict):
        for mk in e.get('markets',[]):candidates[str(mk['id'])]=('macro',e,mk,em)
    # One interpretable outcome first. Other topics remain in the bounded catalogue.
    chosen=['2589811']
    for topic in ['bnb','base','solana']:
        eligible=[]
        for key,(tp,ev,mk,meta) in candidates.items():
            try:overlap=epoch(mk['startDate'])<1792022400 and epoch(mk['endDate'])>1791417600
            except (KeyError,ValueError,TypeError):overlap=False
            text=(ev.get('title','')+' '+mk.get('question','')).lower()
            sem=(topic=='bnb' and 'bnb' in text) or (topic=='solana' and 'solana' in text) or (topic=='base' and 'base launch a token' in text)
            if tp==topic and overlap and sem:eligible.append(key)
        if eligible:chosen.append(sorted(eligible,key=int)[0])
    catalogue=[]
    for key,(topic,event,mk,meta) in candidates.items():
        try:overlap=epoch(mk['startDate'])<1792022400 and epoch(mk['endDate'])>1791417600
        except (KeyError,ValueError,TypeError):overlap=False
        catalogue.append({'event_id':str(event['id']),'market_id':key,'condition_id':mk.get('conditionId',''),'question':mk.get('question',''),'topic':topic,'start_at_utc':mk.get('startDate',''),'scheduled_end_at_utc':mk.get('endDate',''),'closed_snapshot':mk.get('closed'),'native_version':mk.get('version','not_returned'),'outcome_labels_json':json.dumps(array(mk.get('outcomes'))),'outcome_asset_ids_json':json.dumps(array(mk.get('clobTokenIds'))),'time_overlap_legacy':overlap,'decision':'selected_for_P1_history_probe' if key in chosen else 'catalogue_only_P1_cap','decision_reason':'fixed economic contract / earliest numerical ID eligible topic candidate, not selected on price variation' if key in chosen else ('not_temporally_applicable' if not overlap else 'bounded_P1_round;no_full_category_completeness_claim'),'evidence_ref':meta['raw_ref'],'market_url':'https://polymarket.com/event/'+event.get('slug','')})
    write_csv(ROOT/'processed/pm_candidate_catalogue.csv',catalogue)
    for key in chosen:
        topic,event,mk,discovery=candidates[key]
        full,m=c.request('https://gamma-api.polymarket.com/markets/'+key,label='market_rule_snapshot_'+key)
        if not isinstance(full,dict) or not m['ok']:continue
        mk=full;labels=array(mk.get('outcomes'));assets=array(mk.get('clobTokenIds'))
        if len(labels)!=len(assets) or not assets:raise ValueError('Outcome/asset array mismatch; no inferred positional repair')
        market_key='polymarket:gamma:market:'+key;snapshot='market_snapshot:'+sid(market_key,m['sha256'])
        rule=ROOT/'raw/rules'/('market_'+key+'_'+m['request_id']+'.txt');rule.write_text(mk.get('description',''),encoding='utf-8')
        market={'market_snapshot_id':snapshot,'pm_market_key':market_key,'event_id':str(event['id']),'market_id':key,'condition_id':mk.get('conditionId',''),'question':mk.get('question',''),'slug':mk.get('slug',''),'rules_ref':str(rule.relative_to(ROOT)),'rules_sha256':sha(rule),'rules_snapshot_at_utc':m['retrieved_at_utc'],'opened_at_utc':mk.get('startDate',''),'created_at_api_utc':mk.get('createdAt',''),'scheduled_close_at_utc':mk.get('endDate',''),'actual_close_at_utc':mk.get('closedTime',''),'resolved_at_utc':mk.get('resolvedTime',''),'active_snapshot':mk.get('active'),'closed_snapshot':mk.get('closed'),'resolution_state_snapshot':mk.get('umaResolutionStatus',mk.get('umaResolutionStatuses','')),'resolution_result':'not_inferred_from_current_outcome_prices','protocol_version_native':str(mk.get('version','not_returned')),'settlement_network':'not_inferred_from_asset_id','snapshot_at_utc':m['retrieved_at_utc'],'raw_ref':m['raw_ref'],'rules_historical_revision_status':'current_definition_snapshot;historical_rule_revision_archive_not_obtained','topic':topic}
        markets.append(market)
        for index,(label,asset) in enumerate(zip(labels,assets)):
            outcomes.append({'pm_outcome_key':'polymarket:gamma_asset:'+str(asset),'pm_market_key':market_key,'market_snapshot_id':snapshot,'outcome_index':index,'outcome_label':label,'asset_id_raw':str(asset),'asset_id_type':'gamma_clobTokenIds_asset_identifier','protocol_version_native':market['protocol_version_native'],'native_id_type_verification':'field_source_verified;not_assumed_CTF_or_position_without_contract_evidence','raw_ref':m['raw_ref']})
        asset=str(assets[0]);okey='polymarket:gamma_asset:'+asset
        base={'token_id':asset,'start':1791244800,'end':1792022400,'limit':250 if key=='2589811' else 1000}
        all_points=[];cursor=None;seen=set();requests=[]
        while True:
            params=base if cursor is None else {**base,'cursor':cursor}
            data,hm=c.request('https://data-api.polymarket.com/v2/prices-history?'+urlencode(params),label='legacy_week_history_'+key)
            requests.append(hm)
            if not isinstance(data,dict) or not hm['ok']:break
            pts=data.get('data',[]);all_points.extend(pts)
            for point in pts:
                ts=int(point['timestamp']);resolution=int(point['resolution_seconds']);price=point['price']
                # Official OpenAPI: aggregate timestamp is bucket START; width is explicit.
                # Exclude all resolution=0 ticks in this P1 adapter (could include settlement).
                prices.append({'price_observation_id':'price:'+sid(okey,ts,resolution,price),'pm_outcome_key':okey,'market_snapshot_id':snapshot,'price':str(price),'price_unit':'0_to_1_API_history_market_expectation_proxy','price_definition_status':'api_history_price_definition_unconfirmed_not_claimed_midpoint_or_trade','source_timestamp_utc':iso(ts),'bucket_start_utc':iso(ts) if resolution else '', 'bucket_end_utc':iso(ts+resolution) if resolution else '', 'effective_information_time_utc':iso(ts+resolution),'resolution_seconds':resolution,'time_semantics_status':'official_OpenAPI_bucket_start_plus_width' if resolution else 'exact_tick_excluded_pending_settlement_classification','is_settlement_point':'unknown_tick_excluded' if resolution==0 else False,'eligible_for_asof':resolution>0,'source_retrieved_at_utc':hm['retrieved_at_utc'],'request_id':hm['request_id'],'raw_ref':hm['raw_ref']})
            cursor=data.get('pagination',{}).get('next_cursor')
            if not cursor:break
            if cursor in seen:raise ValueError('Repeated historical cursor')
            seen.add(cursor)
            if len(requests)>=8:raise RuntimeError('P1 history page cap reached; incomplete pagination')
        unique={ (p['timestamp'],p['resolution_seconds'],p['price']) for p in all_points }
        vals=[float(p['price']) for p in all_points]
        times=sorted({int(p['timestamp']) for p in all_points})
        feasibility.append({'market_key':market_key,'outcome_key':okey,'topic':topic,'target_window':'legacy_week_20261008_20261015','rules_checked':'question/full_description/outcome_array_reviewed','time_overlap':True,'history_requested':True,'history_obtained':bool(all_points),'history_pages':len(requests),'pagination_complete':bool(all_points) and not cursor,'actual_resolution_seconds':'|'.join(map(str,sorted({int(p['resolution_seconds']) for p in all_points}))), 'valid_points':sum(p['resolution_seconds']>0 for p in all_points),'returned_points':len(all_points),'duplicate_points':len(all_points)-len(unique),'first_source_timestamp_utc':iso(times[0]) if times else '', 'last_source_timestamp_utc':iso(times[-1]) if times else '', 'observed_gap_seconds_min':min([b-a for a,b in zip(times,times[1:])],default=0),'observed_gap_seconds_max':max([b-a for a,b in zip(times,times[1:])],default=0),'price_definition_status':'api_history_price_definition_unconfirmed','variation_summary':json.dumps({'min':min(vals) if vals else None,'max':max(vals) if vals else None,'distinct_values':len(set(vals))}), 'public_access_status':'public_no_auth_actual_HTTP200' if all_points else 'history_unavailable','intended_use':'limited_for_demonstration' if all_points else 'catalogue_only','decision_reason':'Official bucket time semantics confirmed; scalar construction not specified as midpoint/trade; retrospective semantic mapping; no causal or individual-token forecast claim.'})
    # Deduplicate exact observations; conflicts are separately caught by validation.
    prices=list({r['price_observation_id']:r for r in prices}.values())
    for name,data in [('pm_markets',markets),('pm_outcomes',outcomes),('pm_prices',prices)]:write_csv(ROOT/'processed'/(name+'.csv'),data)
    write_csv(ROOT/'reports/polymarket_feasibility.csv',feasibility)
    write_json(ROOT/'reports/polymarket_probe_receipt.json',{'completed_at_utc':now(),'network_calls_this_invocation':c.calls,'search_request_count':len(searches),'catalogue_markets':len(catalogue),'history_markets':len(markets),'history_points':len(prices),'chosen_market_ids':chosen,'selection_rule':'fixed Fed 25bps contract then minimum numerical market id in each temporally overlapping semantic topic, before history responses','search_exhaustive':False,'scalar_price_semantics':'not_assumed_trade_midpoint_or_probability_calibration','raw_is_local_only':True})
    print(json.dumps({'searches':len(searches),'catalogue':len(catalogue),'markets':len(markets),'prices':len(prices)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');run(p.parse_args().refresh)
