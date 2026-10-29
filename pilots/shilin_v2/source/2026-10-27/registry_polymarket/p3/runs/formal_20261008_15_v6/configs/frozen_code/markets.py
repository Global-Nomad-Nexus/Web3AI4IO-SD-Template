"""Bounded seven-category discovery, exact outcome history and reviewed mappings."""
from core import *
from urllib.parse import urlencode
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation

def array(value):
    if isinstance(value,list):return value
    return json.loads(value) if isinstance(value,str) and value else []
def overlap(m,start,end):
    try:return epoch(m['opened_at_utc'])<end and epoch(m['scheduled_close_at_utc'])>start
    except (KeyError,ValueError,TypeError):return False
def market_end(m):
    # Gamma also returns an explicit UTC offset as '+00' with a space before
    # the clock. Parse that representation without changing the saved source.
    values=[m[k] for k in ['scheduled_close_at_utc','actual_close_at_utc','resolved_at_utc'] if m.get(k)]
    return min([epoch(v+':00' if v.endswith('+00') else v) for v in values],default=float('-inf'))

def seed_inputs(root):
    """Read-only reuse of P1 observations; references point back to original bytes."""
    out={}
    for name in ['pm_markets','pm_outcomes','pm_prices','pm_mapping']:
        rows=read_csv(PARENT/'processed'/(name+'.csv'))
        for row in rows:
            for k in ['raw_ref','rules_ref','rule_snapshot_ref','evidence_ref']:
                if row.get(k):row[k]=ref(resolve(PARENT,row[k]),root)
        out[name]=rows
    return out

def reviewed_mappings(markets,outcomes,root,reviews=None):
    review_path=Path(root)/'configs/mapping_reviews.csv'
    reviews=reviews if reviews is not None else read_csv(review_path if review_path.exists() else ROOT/'configs/mapping_reviews.csv');out=[]
    for review in reviews:
        if review.get('review_decision')=='catalogue_only':continue
        matching=[m for m in markets if m['market_id']==review['market_id'] and m.get('rules_sha256')==review['rules_sha256']]
        if not matching:continue # Never carry a review to a changed rule snapshot.
        market=sorted(matching,key=lambda r:r['snapshot_at_utc'])[0]
        if review['link_type'] not in ['verified_token_identity','platform','chain','shared_economic_event']:raise Halt('Invalid mapping link type')
        if review['link_type']=='verified_token_identity' and not review.get('verified_address_evidence_ref'):raise Halt('Direct identity requires address evidence')
        selected=[o for o in outcomes if o['market_snapshot_id']==market['market_snapshot_id'] and o['outcome_label']==review['outcome_label']]
        if len(selected)!=1:raise Halt('Reviewed outcome label does not identify one native asset')
        o=selected[0];a=max(epoch(market['opened_at_utc']),epoch(review['semantic_valid_from_utc']));b=min(market_end(market),epoch(review['semantic_valid_to_utc']))
        if b<=a:continue
        row={'mapping_id':'mapping:'+sid(review['link_type'],review['target_id'],o['pm_outcome_key'],market['market_snapshot_id']),'link_type':review['link_type'],'target_type':review['target_type'],'target_id':review['target_id'],'applicable_chain_keys':review['applicable_chain_keys'],'pm_market_key':market['pm_market_key'],'pm_outcome_key':o['pm_outcome_key'],'market_snapshot_id':market['market_snapshot_id'],'rule_snapshot_ref':market['rules_ref'],'evidence_ref':market['raw_ref'],'semantic_valid_from_utc':iso(a),'semantic_valid_to_utc':iso(b),'rule_known_from_utc':'','reviewed_by':review['reviewed_by'],'review_status':'retrospective_mapping','uncertainty':'API scalar construction and historical rule revisions unverified; background is not individual-token probability'}
        row['history_resolution_seconds']=review.get('history_resolution_seconds','')
        out.append(row)
    return sorted(out,key=lambda r:r['mapping_id'])

def normalize_price(point,outcome,snapshot,meta,start,end):
    ts=int(point['timestamp']);width=int(point['resolution_seconds']);value=Decimal(str(point['price']))
    if not value.is_finite() or not Decimal(0)<=value<=Decimal(1) or width<0:raise Halt('Invalid price or resolution')
    # The API documents a zero-resolution settlement clamped to explicit end.
    # Retain that terminal evidence while excluding every zero-resolution point
    # from as-of features; positive-width points still require the half-open range.
    if not (start<=ts<end or (width==0 and ts==end)):raise Halt('History response outside explicit requested interval')
    return {'price_observation_id':'price:'+sid(outcome,ts,width,str(value)),'pm_outcome_key':outcome,'market_snapshot_id':snapshot,'price':str(value),'source_timestamp_utc':iso(ts),'bucket_start_utc':iso(ts) if width else '','bucket_end_utc':iso(ts+width) if width else '','effective_information_time_utc':iso(ts+width),'resolution_seconds':width,'is_settlement_point':'unknown_tick_excluded' if not width else False,'eligible_for_asof':width>0,'time_semantics_status':'official_OpenAPI_bucket_start_plus_width' if width else 'zero_resolution_excluded','price_definition_status':'api_history_price_definition_unconfirmed','source_retrieved_at_utc':meta['retrieved_at_utc'],'request_id':meta['request_id'],'raw_ref':meta['raw_ref']}

def fetch_history(client,outcome,market,start,end):
    rows=[];audit=[];size=int(client.cfg['budgets']['history_chunk_days'])*86400
    for a in range(start,end,size):
        b=min(end,a+size);cursor=None;seen=set();complete=False
        for page in range(int(client.cfg['budgets']['max_history_pages_per_outcome'])):
            params={'token_id':outcome['asset_id_raw'],'start':a,'end':b,'limit':1000}
            if cursor:params['cursor']=cursor
            try:
                data,m=client.json(client.cfg['sources']['history']+'?'+urlencode(params),label='outcome_historical_prices')
            except Halt as e:
                if 'budget' in str(e).lower():raise
                audit.append({'outcome':outcome['pm_outcome_key'],'start':iso(a),'end':iso(b),'status':'request_failed','reason':str(e)});break
            if not isinstance(data,dict) or not isinstance(data.get('data'),list):raise Halt('Invalid outcome history schema')
            rows.extend(normalize_price(p,outcome['pm_outcome_key'],market['market_snapshot_id'],m,a,b) for p in data['data'])
            cursor=data.get('pagination',{}).get('next_cursor')
            audit.append({'outcome':outcome['pm_outcome_key'],'start':iso(a),'end':iso(b),'page':page+1,'status':'more_pages' if cursor else 'complete','rows':len(data['data']),'raw_ref':m['raw_ref']})
            if not cursor:complete=True;break
            if cursor in seen:raise Halt('Repeated history cursor')
            seen.add(cursor)
        if cursor and not complete:audit.append({'outcome':outcome['pm_outcome_key'],'start':iso(a),'end':iso(b),'status':'partial_page_cap','reason':'not_exhausted'})
    return rows,audit

def collect(client):
    root=client.root;cfg=client.cfg;start=int(epoch(cfg['candidate_start_utc']));end=int(epoch(cfg['candidate_end_utc']))
    seeded=seed_inputs(root);markets={m['market_id']:m for m in seeded['pm_markets']};outcomes=list(seeded['pm_outcomes']);prices=list(seeded['pm_prices']);catalogue={};searches=[];selected=set(markets)
    for category,terms in cfg['categories'].items():
        category_markets={}
        for term in terms:
            for state in ['active','closed']:
                for page in range(1,int(cfg['budgets']['max_search_pages_per_term_state'])+1):
                    params={'q':term,'events_status':state,'limit_per_type':10,'page':page};url=cfg['sources']['gamma']+'/public-search?'+urlencode(params)
                    try:
                        data,m=client.json(url,label=category+'_'+state+'_search');events=data.get('events',[]);more=bool(data.get('pagination',{}).get('hasMore'))
                        status='page_cap_not_exhausted' if more and page==cfg['budgets']['max_search_pages_per_term_state'] else ('more_pages' if more else 'server_end')
                        searches.append({'category':category,'term':term,'state':state,'page':page,'status':status,'event_ids':'|'.join(str(e['id']) for e in events),'raw_ref':m['raw_ref'],'parameters':canonical(params),'retrieved_at_utc':m['retrieved_at_utc']})
                        for event in events:
                            # Fetch event details: search submarket arrays may be abbreviated.
                            full,em=client.json(cfg['sources']['gamma']+'/events/'+str(event['id']),label='expand_event_submarkets')
                            for mk in full.get('markets',[]):
                                key=str(mk['id']);category_markets[key]=mk
                                catalogue[(category,key)]={'candidate_id':'candidate:'+sid(category,key),'category':category,'market_id':key,'event_id':str(event['id']),'question':mk.get('question',''),'opened_at_utc':mk.get('startDate',''),'scheduled_close_at_utc':mk.get('endDate',''),'outcomes_json':canonical(array(mk.get('outcomes'))),'raw_ref':em['raw_ref'],'review_status':'pending_rule_review','history_selection':'not_selected_budget_or_temporal_scope'}
                    except Halt as e:
                        if 'budget' in str(e).lower():raise
                        searches.append({'category':category,'term':term,'state':state,'page':page,'status':'request_failed','error':str(e)});more=False
                    write_csv(root/'reports/market_search_log.csv',searches)
                    if not more:break
        eligible=[key for key,mk in category_markets.items() if overlap({'opened_at_utc':mk.get('startDate',''),'scheduled_close_at_utc':mk.get('endDate','')},start,end)]
        selected.update(sorted(eligible,key=lambda x:int(x))[:int(cfg['budgets']['max_markets_per_category'])])
    # Stable, price-blind selection; rules for every other candidate remain in catalogue.
    history_audit=[];history_outcomes=0
    for key in sorted(selected,key=int):
        if key in markets:
            # Keep P1 rule snapshots; still assess/fetch previously unrequested No outcomes.
            for o in [o for o in outcomes if o['market_snapshot_id']==markets[key]['market_snapshot_id']]:
                if any(p['pm_outcome_key']==o['pm_outcome_key'] for p in prices):
                    history_audit.append({'outcome':o['pm_outcome_key'],'start':iso(start),'end':iso(end),'status':'reused_fixed_P1_history','reason':'source bytes and limits retained'});continue
                if history_outcomes>=cfg['budgets']['max_history_outcomes']:
                    history_audit.append({'outcome':o['pm_outcome_key'],'status':'not_attempted_outcome_budget'});continue
                history_outcomes+=1;new,audit=fetch_history(client,o,markets[key],start-49*3600,end);prices.extend(new);history_audit.extend(audit)
            continue
        mk,m=client.json(cfg['sources']['gamma']+'/markets/'+key,label='full_market_rule_snapshot')
        labels=array(mk.get('outcomes'));assets=array(mk.get('clobTokenIds'))
        if len(labels)!=len(assets) or len(assets)!=len(set(assets)) or not assets:raise Halt('Outcome/native identifier array mismatch')
        rule=mk.get('description','');rule_path=root/'rules'/('market_'+key+'_'+m['request_id']+'.txt');atomic(rule_path,rule.encode())
        snapshot='market_snapshot:'+sid(key,m['sha256']);market={'market_snapshot_id':snapshot,'pm_market_key':'polymarket:gamma:market:'+key,'market_id':key,'event_id':next((r['event_id'] for r in catalogue.values() if r['market_id']==key),''),'condition_id':mk.get('conditionId',''),'question':mk.get('question',''),'slug':mk.get('slug',''),'rules_ref':ref(rule_path,root),'rules_sha256':sha(rule_path),'opened_at_utc':mk.get('startDate',''),'scheduled_close_at_utc':mk.get('endDate',''),'actual_close_at_utc':mk.get('closedTime',''),'resolved_at_utc':mk.get('resolvedTime',''),'closed_snapshot':mk.get('closed'),'active_snapshot':mk.get('active'),'resolution_state_snapshot':canonical(mk.get('umaResolutionStatus','')),'resolution_result':'not_inferred_from_current_price','protocol_version_native':mk.get('version','not_returned'),'raw_ref':m['raw_ref'],'snapshot_at_utc':m['retrieved_at_utc'],'rules_historical_revision_status':'not_obtained','activity_scope':'current_snapshot_only_not_historical_activity'}
        markets[key]=market
        for label,asset in zip(labels,assets):
            o={'pm_outcome_key':'polymarket:gamma_asset:'+str(asset),'pm_market_key':market['pm_market_key'],'market_snapshot_id':snapshot,'outcome_label':label,'asset_id_raw':str(asset),'asset_id_type':'gamma_clobTokenIds_asset_identifier','protocol_version_native':market['protocol_version_native'],'raw_ref':m['raw_ref']};outcomes.append(o)
            if history_outcomes>=cfg['budgets']['max_history_outcomes']:
                history_audit.append({'outcome':o['pm_outcome_key'],'status':'not_attempted_outcome_budget'});continue
            history_outcomes+=1;new,audit=fetch_history(client,o,market,start-49*3600,end);prices.extend(new);history_audit.extend(audit)
        write_csv(root/'reports/history_requests.csv',history_audit,['outcome','start','end','page','status','rows','raw_ref','reason'])
        save(root/'state/market_progress.json',{'completed_market_ids':sorted(markets),'history_outcomes_requested':history_outcomes,'status':'in_progress'})
    mapping=reviewed_mappings(list(markets.values()),outcomes,root)
    queue=[]
    for o in outcomes:
        if any(m['pm_outcome_key']==o['pm_outcome_key'] for m in mapping):continue
        m=next(m for m in markets.values() if m['market_snapshot_id']==o['market_snapshot_id'])
        queue.append({'market_id':m['market_id'],'market_snapshot_id':m['market_snapshot_id'],'question':m['question'],'outcome_label':o['outcome_label'],'pm_outcome_key':o['pm_outcome_key'],'rules_ref':m['rules_ref'],'rules_sha256':m['rules_sha256'],'opened_at_utc':m['opened_at_utc'],'scheduled_close_at_utc':m['scheduled_close_at_utc'],'review_status':'pending_explicit_rule_and_period_review','history_points':sum(p['pm_outcome_key']==o['pm_outcome_key'] for p in prices)})
    write_csv(root/'reports/mapping_review_queue.csv',queue,['market_id','market_snapshot_id','question','outcome_label','pm_outcome_key','rules_ref','rules_sha256','opened_at_utc','scheduled_close_at_utc','review_status','history_points'])
    write_csv(root/'reports/history_requests.csv',history_audit,['outcome','start','end','page','status','rows','raw_ref','reason'])
    for r in catalogue.values():
        if r['market_id'] in markets:r['history_selection']='selected_before_price_response'
    write_csv(root/'processed/pm_candidate_catalogue.csv',sorted(catalogue.values(),key=lambda r:(r['category'],int(r['market_id']))),['candidate_id','category','market_id','event_id','question','opened_at_utc','scheduled_close_at_utc','outcomes_json','raw_ref','review_status','history_selection'])
    write_market_tables(root,{'pm_markets':list(markets.values()),'pm_outcomes':outcomes,'pm_prices':prices,'pm_mapping':mapping})
    activities=[]
    for m in markets.values():
        activities.append({'market_id':m['market_id'],'snapshot_at_utc':m['snapshot_at_utc'],'historical_activity_status':'not_acquired','current_activity_not_used_as_historical':True,'raw_ref':m['raw_ref']})
    write_csv(root/'processed/pm_activity.csv',activities)
    applicability(root,cfg)

def write_market_tables(root,tables):
    for name,rows in tables.items():
        if name=='pm_prices':
            by_key={};unique={}
            for r in rows:
                key=(r['pm_outcome_key'],r['source_timestamp_utc'],str(r['resolution_seconds']))
                if key in by_key and Decimal(by_key[key]['price'])!=Decimal(r['price']):raise Halt('Conflicting historical scalar at same outcome/time/resolution')
                by_key[key]=r;unique[r['price_observation_id']]=r
            rows=sorted(unique.values(),key=lambda r:(r['pm_outcome_key'],r['source_timestamp_utc'],r['price_observation_id']))
        fields={'pm_mapping':['mapping_id','link_type','target_id','pm_outcome_key','market_snapshot_id','semantic_valid_from_utc','semantic_valid_to_utc'],'pm_prices':['price_observation_id','pm_outcome_key','price','effective_information_time_utc']}.get(name)
        write_csv(Path(root)/'processed'/(name+'.csv'),rows,fields if not rows else None)

def applicability(root,cfg):
    markets=read_csv(Path(root)/'processed/pm_markets.csv');outs=read_csv(Path(root)/'processed/pm_outcomes.csv');prices=read_csv(Path(root)/'processed/pm_prices.csv');maps=read_csv(Path(root)/'processed/pm_mapping.csv');catalogue=read_csv(Path(root)/'processed/pm_candidate_catalogue.csv');history=read_csv(Path(root)/'reports/history_requests.csv')
    rp=Path(root)/'configs/mapping_reviews.csv';reviews=read_csv(rp if rp.exists() else ROOT/'configs/mapping_reviews.csv')
    by_market={m['market_id']:m for m in markets};by_prices=defaultdict(list)
    for p in prices:by_prices[p['pm_outcome_key']].append(p)
    rows=[];start=epoch(cfg['candidate_start_utc']);end=epoch(cfg['candidate_end_utc'])
    for o in outs:
        m=next(m for m in markets if m['market_snapshot_id']==o['market_snapshot_id']);pp=by_prices[o['pm_outcome_key']];reviewed=any(x['pm_outcome_key']==o['pm_outcome_key'] for x in maps)
        # A rule review of the question also covers its complementary label, without
        # inventing a mapping or requesting it for the token-level product.
        rule_reviewed=any(x['market_snapshot_id']==m['market_snapshot_id'] for x in maps) or any(r['market_id']==m['market_id'] and r['rules_sha256']==m['rules_sha256'] for r in reviews)
        temporal=epoch(m['opened_at_utc'])<end and market_end(m)>start;valid=[p for p in pp if truth(p.get('eligible_for_asof'))]
        semantic_reviews=[r for r in reviews if r['market_id']==m['market_id'] and r['rules_sha256']==m['rules_sha256'] and r.get('semantic_categories')]
        semantic_categories={c for r in semantic_reviews for c in r['semantic_categories'].split('|')}
        cats=sorted({c['category'] for c in catalogue if c['market_id']==m['market_id']}) or [dict(macro='macro',solana='solana',bnb='bnb',base='base_token').get(m.get('topic'),m.get('topic','seed'))]
        for category in cats:
            semantic_match=not semantic_reviews or category in semantic_categories
            decision='limited_for_demonstration' if semantic_match and temporal and valid and reviewed else 'catalogue_only'
            reason='query_false_positive_wrong_semantic_category' if not semantic_match else ('reviewed_retrospective_only' if decision=='limited_for_demonstration' else ('no_temporal_overlap' if not temporal else ('history_unavailable_or_unrequested' if not pp else ('reviewed_catalogue_or_complement_not_selected_for_mapping' if rule_reviewed else 'semantic_mapping_pending_review'))))
            rows.append({'category':category,'market_id':m['market_id'],'pm_outcome_key':o['pm_outcome_key'],'rules_checked':rule_reviewed,'semantic_category_match':semantic_match,'time_overlap':temporal,'history_obtained':bool(pp),'returned_points':len(pp),'valid_points':len(valid),'resolutions_seconds':'|'.join(sorted({str(p['resolution_seconds']) for p in pp})),'distinct_values':len({p['price'] for p in pp}),'decision':decision,'reason':reason,'price_definition_status':'unconfirmed_scalar','historical_rule_version':'not_obtained'})
    write_csv(Path(root)/'reports/polymarket_feasibility.csv',rows,['category','market_id','pm_outcome_key','rules_checked','semantic_category_match','time_overlap','history_obtained','returned_points','valid_points','resolutions_seconds','distinct_values','decision','reason','price_definition_status','historical_rule_version'])
    search=read_csv(Path(root)/'reports/market_search_log.csv');summary=[]
    for cat in cfg['categories']:
        rr=[r for r in rows if r['category']==cat];ss=[r for r in search if r['category']==cat]
        summary.append({'category':cat,'candidate_markets':len({r['market_id'] for r in catalogue if r['category']==cat}),'detailed_markets':len({r['market_id'] for r in rr}),'outcomes':len(rr),'rules_reviewed_outcomes':sum(truth(r['rules_checked']) for r in rr),'history_obtained_outcomes':sum(truth(r['history_obtained']) for r in rr),'connectable_outcomes':sum(r['decision']=='limited_for_demonstration' for r in rr),'active_queried':any(r.get('state')=='active' for r in ss),'closed_queried':any(r.get('state')=='closed' for r in ss),'search_status':'not_run' if not ss else ('partial_source_failures' if any(r['status']=='request_failed' for r in ss) else ('bounded_not_exhaustive' if any(r['status']=='page_cap_not_exhausted' for r in ss) else 'bounded_queries_completed'))})
    write_csv(Path(root)/'reports/market_category_coverage.csv',summary)
