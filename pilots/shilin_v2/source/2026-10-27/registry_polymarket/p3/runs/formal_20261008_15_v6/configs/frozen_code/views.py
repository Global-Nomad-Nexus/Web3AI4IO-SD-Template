"""Native evidence -> stable Registry; multi-market joins; legacy/metadata audits."""
from core import *
from native_decode import pump_args, exact_evm
from markets import market_end
from collections import Counter, defaultdict
import bisect

def decode_envelopes(envelopes,chain,start,end,cohort,legacy_ids,source_root,output_root):
    versions={(v['chain_key'],v['address'],v['topic0']):v for v in load(ROOT/'configs/platform_events.json')}
    seen={}
    for block in envelopes:
        h=block['header'];t=h['timestamp']
        if not start<=t<end:raise Halt('Creation block outside declared UTC day')
        if not h.get('hash'):raise Halt('Creation block hash missing')
        txs=block.get('transactions',[]);by_index={r['transactionIndex']:r for r in txs};by_hash={r['hash']:r for r in txs if 'hash' in r}
        for item in block.get('instructions' if chain=='solana:mainnet' else 'logs',[]):
            if chain=='solana:mainnet':
                tx=by_index[item['transactionIndex']];sig=tx['signatures'][0];position=json.dumps(item['instructionAddress'],separators=(',',':'))
                if item.get('isCommitted') is None:raise Halt('Unknown native commitment')
                if not item['isCommitted'] or item.get('error') is not None or tx.get('err') is not None:continue
                if item['programId']!=PROGRAM:raise Halt('Wrong Solana creation program')
                args=pump_args(item['data']);address=item['accounts'][0];creator=args['creator'];platform='pump.fun';version='pump_create_prefix_accounts_v1';program=PROGRAM
                if item['accounts'][1]!=AUTHORITY:raise Halt('Mandatory PDA account mismatch')
                sender=item['accounts'][5 if args['native_instruction']=='create_v2' else 7];args['instruction_user_signer_address']=sender
                payer=tx.get('feePayer','');role='creator argument;not assumed fee payer or user account';name=args['name'];symbol=args['symbol'];uri=args['uri'];outer=item['instructionAddress'][0];inner=json.dumps(item['instructionAddress'][1:]);log_index=''
            else:
                sig=item['transactionHash'];position=str(item['logIndex']);tx=by_hash[sig]
                if tx['status']!=1:raise Halt('Failed native EVM creation in selected evidence')
                v=versions.get((chain,item['address'].lower(),item['topics'][0].lower()))
                if not v:raise Halt('Unregistered EVM creation emitter/topic')
                args=exact_evm(v['event_abi'],item['topics'],item['data']);address=args.get('tokenAddress',args.get('token'));creator=args.get('creator',args.get('tokenAdmin',args.get('creatorAdmin',args.get('deployer',''))))
                if not creator:raise Halt('Creator field absent from declared event layout')
                platform=v['platform_id'];version=v['version'];program=v['address'];role='TokenCreate.creator' if platform=='four.meme' else ('TokenCreated.tokenAdmin' if version=='v4' else ('TokenCreated.creatorAdmin' if version=='v3.1' else 'TokenCreated.deployer'));sender=tx['from'];payer='';name=args.get('tokenName',args.get('name',''));symbol=args.get('tokenSymbol',args.get('symbol',''));uri='';outer='';inner='';log_index=item['logIndex']
            key=(chain,sig,position);fingerprint=digest(item)
            if key in seen:
                if seen[key]!=fingerprint:raise Halt('Conflicting duplicate native event')
                continue
            seen[key]=fingerprint;tid=token_id(chain,address);cid='creation:'+sid(*key)
            def rr(value):return ref(resolve(source_root,value),output_root) if value else ''
            yield {'creation_event_id':cid,'token_id':tid,'chain_key':chain,'platform_id':platform,'platform_version_id':version,'program_or_factory_address':program,'token_address_raw':address,'token_address_canonical':address if chain=='solana:mainnet' else address.lower(),'creation_tx_hash_or_signature':sig,'block_height_or_slot':h['number'],'block_hash':h['hash'],'created_at_utc':iso(t),'transaction_index':item['transactionIndex'],'transaction_format_version':str(tx.get('version','')) if chain=='solana:mainnet' else '','native_instruction_path':position if chain=='solana:mainnet' else '','outer_instruction_index':outer,'inner_instruction_path':inner,'log_index':log_index,'creator_address':creator,'creator_role_definition':role,'tx_sender_or_signer':sender,'fee_payer':payer,'initial_name':name,'initial_symbol':symbol,'initial_metadata_uri':uri,'initial_metadata_uri_status':'onchain_empty_preserved' if chain=='solana:mainnet' and not uri else ('onchain_declared' if uri else 'not_in_creation_event_schema'),'initial_attributes_json':json.dumps(args,ensure_ascii=False,sort_keys=True),'discovery_mode':'legacy_observed_and_historical_rebuild' if tid in legacy_ids else 'historical_backfill','first_decoded_at_utc':'','historical_metadata_status':'legacy_observation_available_see_coverage' if tid in legacy_ids else 'not_collected_historically','legacy_observed_cohort':tid in legacy_ids,'source_id':block.get('native_source','saved_P2_native_evidence'),'native_receipt_raw_ref':rr(tx.get('receipt_raw_ref','')),'native_block_raw_ref':rr(block.get('header_raw_ref','')),'instruction_commitment_evidence_ref':rr(item.get('instruction_commitment_evidence_ref','')) if chain=='solana:mainnet' else '','execution_status':'success_committed','decoder_version':'p3_pinned_native_prefix_ABI_v1','cohort_id':cohort,'evidence_scope':'declared_address_topic_layout_only'}

def read_envelopes(path):
    with Path(path).open(encoding='utf-8') as f:
        for line in f:
            if line.strip():yield json.loads(line)

def build_registry(root,cfg):
    root=Path(root);legacy={r['token_id'] for r in read_csv(PARENT/'processed/registry.csv')};events=[];conflicts=[];seen_events={};by_token={}
    for day in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']):
        start,end=day_window(day)
        for chain in CHAINS:
            path=root/'days'/day/(chain.replace(':','_')+'_normalized.ndjson')
            if not path.exists():continue
            for row in decode_envelopes(read_envelopes(path),chain,start,end,cfg['cohort_id'],legacy,root,root):
                cid=row['creation_event_id'];tid=row['token_id']
                if cid in seen_events:
                    if seen_events[cid]!=row:raise Halt('Conflicting repeated event')
                    continue
                seen_events[cid]=row;events.append(row)
                if tid in by_token:conflicts.append({'token_id':tid,'first_event':by_token[tid]['creation_event_id'],'second_event':cid,'resolution':'unresolved'})
                else:by_token[tid]=row
    write_csv(root/'reports/creation_conflicts.csv',conflicts,['token_id','first_event','second_event','resolution'])
    if conflicts:raise Halt('Multiple creation identities for a token; review conflicts')
    events.sort(key=lambda r:(r['chain_key'],r['created_at_utc'],r['creation_event_id']))
    fields=['creation_event_id','token_id','chain_key','created_at_utc']
    write_csv(root/'processed/creation_events.csv',events,fields if not events else None)
    # The one-creation-per-token gate above makes these two CSV byte streams
    # identical. Preserve both paths while sharing their immutable storage;
    # subsequent rebuilds replace files atomically rather than editing in place.
    target=root/'processed/registry.csv';tmp=target.with_name(target.name+'.linktmp-'+str(os.getpid()))
    try:
        os.link(root/'processed/creation_events.csv',tmp)
        os.replace(tmp,target)
    finally:tmp.unlink(missing_ok=True)
    return events

class PriceIndex:
    def __init__(self,prices):
        groups=defaultdict(list)
        for p in prices:
            if truth(p.get('eligible_for_asof')) and int(p.get('resolution_seconds',0))>0 and str(p.get('is_settlement_point','False')) in ['False','false','']:
                groups[(p['pm_outcome_key'],int(p['resolution_seconds']))].append(p)
        self.groups={k:sorted(v,key=lambda r:(epoch(r['effective_information_time_utc']),r['price_observation_id'])) for k,v in groups.items()}
        self.times={k:[epoch(r['effective_information_time_utc']) for r in v] for k,v in self.groups.items()}
    def select(self,outcome,anchor,age,market,mapping):
        t=epoch(anchor) if isinstance(anchor,str) else anchor
        if not epoch(mapping['semantic_valid_from_utc'])<=t<epoch(mapping['semantic_valid_to_utc']):return None,'mapping_outside_validity'
        if not market.get('opened_at_utc') or t<epoch(market['opened_at_utc']):return None,'market_not_open'
        if t>=market_end(market):return None,'market_closed_or_resolved'
        resolutions={key[1] for key in self.groups if key[0]==outcome}
        selected=mapping.get('history_resolution_seconds','')
        if selected:
            key=(outcome,int(selected))
        elif len(resolutions)>1:return None,'ambiguous_resolution_series_requires_review'
        else:key=(outcome,next(iter(resolutions),-1))
        times=self.times.get(key,[]);i=bisect.bisect_left(times,t)-1
        if i<0:return None,'history_unavailable'
        if t-times[i]>age*3600:return None,'stale_price'
        return self.groups[key][i],'matched_valid'

def mapping_applies(m,r):
    if r['chain_key'] not in m['applicable_chain_keys'].split('|'):return False
    if m['link_type']=='verified_token_identity':return m['target_id']==r['token_id']
    if m['link_type']=='platform':return m['target_id']==r['platform_id']
    if m['link_type']=='chain':return m['target_id']==r['chain_key']
    return m['link_type']=='shared_economic_event'

LINK_FIELDS=['expectation_link_id','token_id','chain_key','creation_event_id','mapping_id','pm_outcome_key','price_observation_id','anchor_time_utc','effective_information_time_utc','price','price_age_hours','match_status','link_type','feature_readiness']
def build_expectations(root,cfg):
    root=Path(root);registry=read_csv(root/'processed/registry.csv');markets={m['market_snapshot_id']:m for m in read_csv(root/'processed/pm_markets.csv')};maps=read_csv(root/'processed/pm_mapping.csv');index=PriceIndex(read_csv(root/'processed/pm_prices.csv'));age=cfg['price']['primary_max_age_hours']
    numerators=Counter();unique_background=set();unique_direct=set();distinct_by_type=defaultdict(set);denom=Counter(r['chain_key'] for r in registry)
    def links():
        for r in registry:
            applicable=[m for m in maps if mapping_applies(m,r)]
            if not applicable:
                yield dict(zip(LINK_FIELDS,['expectation:'+sid(r['token_id'],'unmatched'),r['token_id'],r['chain_key'],r['creation_event_id'],'','','',r['created_at_utc'],'','','','no_candidate','','retrospective_demonstration_only']))
            for m in applicable:
                p,status=index.select(m['pm_outcome_key'],r['created_at_utc'],age,markets[m['market_snapshot_id']],m)
                if p:
                    numerators[(r['chain_key'],m['link_type'])]+=1;distinct_by_type[(r['chain_key'],m['link_type'])].add(r['token_id'])
                    (unique_direct if m['link_type']=='verified_token_identity' else unique_background).add(r['token_id'])
                yield {'expectation_link_id':'expectation:'+sid(r['token_id'],m['mapping_id']),'token_id':r['token_id'],'chain_key':r['chain_key'],'creation_event_id':r['creation_event_id'],'mapping_id':m['mapping_id'],'pm_outcome_key':m['pm_outcome_key'],'price_observation_id':p['price_observation_id'] if p else '','anchor_time_utc':r['created_at_utc'],'effective_information_time_utc':p['effective_information_time_utc'] if p else '','price':p['price'] if p else '','price_age_hours':format((epoch(r['created_at_utc'])-epoch(p['effective_information_time_utc']))/3600,'.9f') if p else '','match_status':status,'link_type':m['link_type'],'feature_readiness':'retrospective_demonstration_only'}
    stream_csv(root/'processed/token_expectations_at_creation.csv',links(),LINK_FIELDS)
    stream_csv(root/'processed/pm_match_status.csv',({'match_assessment_id':'assessment:'+sid(r['token_id'],r['mapping_id'],r['anchor_time_utc']),'token_id':r['token_id'],'mapping_id':r['mapping_id'],'link_type':r['link_type'],'status':r['match_status'],'primary_reason':r['match_status'],'anchor_time_utc':r['anchor_time_utc']} for r in iter_csv(root/'processed/token_expectations_at_creation.csv')),['match_assessment_id','token_id','mapping_id','link_type','status','primary_reason','anchor_time_utc'])
    counts=Counter((r['chain_key'],r['created_at_utc'][:10]) for r in registry);context=[];coverage=read_csv(root/'reports/creation_coverage.csv');coverage_map={(r['chain'],r['day']):r['status'] for r in coverage}
    for day in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']):
        anchor=day+'T00:00:00Z'
        for chain in CHAINS:
            target={'chain_key':chain,'platform_id':PLATFORMS[chain],'token_id':''}
            for m in maps:
                if m['link_type']=='verified_token_identity' or not mapping_applies(m,target):continue
                p,status=index.select(m['pm_outcome_key'],anchor,age,markets[m['market_snapshot_id']],m)
                context.append({'chain_key':chain,'platform_id':PLATFORMS[chain],'utc_day':day,'mapping_id':m['mapping_id'],'pm_outcome_key':m['pm_outcome_key'],'link_type':m['link_type'],'anchor_time_utc':anchor,'price_observation_id':p['price_observation_id'] if p else '','expectation_at_day_start':p['price'] if p else '','effective_information_time_utc':p['effective_information_time_utc'] if p else '','match_status':status,'observed_created_tokens':counts[(chain,day)],'creation_coverage_status':coverage_map.get((chain,day),'not_attempted')})
    write_csv(root/'processed/context_daily.csv',context,['chain_key','platform_id','utc_day','mapping_id','pm_outcome_key','link_type','anchor_time_utc','price_observation_id','expectation_at_day_start','effective_information_time_utc','match_status','observed_created_tokens','creation_coverage_status'])
    coverage_rows=[]
    for chain in CHAINS:
        for typ in ['verified_token_identity','platform','chain','shared_economic_event']:
            coverage_rows.append({'chain_key':chain,'link_type':typ,'valid_token_numerator':len(distinct_by_type[(chain,typ)]),'token_denominator':denom[chain],'mapping_rows':sum(mapping_applies(m,{'chain_key':chain,'platform_id':PLATFORMS[chain],'token_id':m['target_id']}) for m in maps if m['link_type']==typ)})
    write_csv(root/'reports/expectation_coverage.csv',coverage_rows)
    daily=[]
    for chain in CHAINS:
        grid=[(chain,d) for d in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc'])];good={r['utc_day'] for r in context if r['chain_key']==chain and r['match_status']=='matched_valid'}
        daily.append({'chain_key':chain,'background_days_numerator':len(good),'declared_days_denominator':len(grid),'joint_complete_days_numerator':sum(d in good and coverage_map.get((chain,d),'').startswith('complete') for _,d in grid)})
    write_csv(root/'reports/background_day_coverage.csv',daily)
    anchors=[]
    for m in maps:
        eligible=[d for d in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']) if epoch(m['semantic_valid_from_utc'])<=day_window(d)[0]<epoch(m['semantic_valid_to_utc'])]
        valid=sum(index.select(m['pm_outcome_key'],day_window(d)[0],age,markets[m['market_snapshot_id']],m)[0] is not None for d in eligible)
        anchors.append({'mapping_id':m['mapping_id'],'pm_outcome_key':m['pm_outcome_key'],'valid_daily_anchor_numerator':valid,'eligible_daily_anchor_denominator':len(eligible)})
    write_csv(root/'reports/market_history_anchor_coverage.csv',anchors,['mapping_id','pm_outcome_key','valid_daily_anchor_numerator','eligible_daily_anchor_denominator'])
    sensitivity=[]
    for threshold in cfg['price']['sensitivity_hours'][:1]+[age]+cfg['price']['sensitivity_hours'][1:]:
        valid=defaultdict(set)
        for r in registry:
            for m in maps:
                if mapping_applies(m,r) and index.select(m['pm_outcome_key'],r['created_at_utc'],threshold,markets[m['market_snapshot_id']],m)[0]:valid[(r['chain_key'],m['link_type'])].add(r['token_id'])
        for chain in CHAINS:
            for typ in ['verified_token_identity','platform','chain','shared_economic_event']:sensitivity.append({'chain_key':chain,'link_type':typ,'max_price_age_hours':threshold,'valid_token_numerator':len(valid[(chain,typ)]),'token_denominator':denom[chain]})
    write_csv(root/'reports/price_age_sensitivity.csv',sensitivity)

def legacy_audit(root,cfg):
    root=Path(root);old=read_csv(PARENT/'processed/registry.csv');current=read_csv(root/'processed/registry.csv');old_by={r['token_id']:r for r in old};new_by={r['token_id']:r for r in current if r['chain_key']=='solana:mainnet'};diff=[];crosswalk=[]
    coverage={(r['chain'],r['day']):r['status'] for r in read_csv(root/'reports/creation_coverage.csv')}
    for tid in sorted(set(old_by)|set(new_by)):
        a=old_by.get(tid);b=new_by.get(tid);day=(b or a)['created_at_utc'][:10];complete=coverage.get(('solana:mainnet',day),'').startswith('complete')
        status='intersection' if a and b else ('new_only' if b else ('old_not_found_in_complete_scope' if complete else 'old_not_evaluated_unclosed_scope'))
        conflicts=[]
        if a and b:
            conflicts=[k for k in ['creation_tx_hash_or_signature','created_at_utc','creator_address'] if a[k]!=b[k]]
            crosswalk.append({'token_id':tid,'legacy_creation_event_id':a['creation_event_id'],'P3_creation_event_id':b['creation_event_id'],'legacy_native_path':a.get('native_instruction_path',''),'P3_native_path':b.get('native_instruction_path',''),'signature_same':a['creation_tx_hash_or_signature']==b['creation_tx_hash_or_signature'],'conflicting_fields':'|'.join(conflicts)})
        diff.append({'token_id':tid,'utc_day':day,'platform_version_id':(b or a).get('platform_version_id',''),'set_status':status,'legacy_creation_event_id':a['creation_event_id'] if a else '','P3_creation_event_id':b['creation_event_id'] if b else '','field_conflicts':'|'.join(conflicts),'reason':'identity_fields_agree' if a and b and not conflicts else 'reason_unknown','empty_URI_rule_consistent':bool(b and not a and not b.get('initial_metadata_uri')),'reason_evidence_status':'URI condition is an auditable candidate explanation, not sole proven cause' if b and not a else 'compare native evidence','legacy_evidence_ref':ref(PARENT/'processed/registry.csv',root),'P3_evidence_ref':b.get('native_receipt_raw_ref','') if b else ''})
    write_csv(root/'reports/creation_set_diff.csv',diff)
    write_csv(root/'processed/token_id_crosswalk.csv',crosswalk,['token_id','legacy_creation_event_id','P3_creation_event_id','legacy_native_path','P3_native_path','signature_same','conflicting_fields'])
    summary=[]
    for day in utc_days('2026-10-08T00:00:00Z','2026-10-15T00:00:00Z'):
        rr=[r for r in diff if r['utc_day']==day]
        summary.append({'utc_day':day,'coverage_status':coverage.get(('solana:mainnet',day),'not_attempted'),'legacy_tokens':sum(r['set_status']!='new_only' for r in rr),'reconstructed_tokens':sum(r['set_status'] in ['new_only','intersection'] for r in rr),'intersection':sum(r['set_status']=='intersection' for r in rr),'new_only':sum(r['set_status']=='new_only' for r in rr),'old_not_found':sum(r['set_status']=='old_not_found_in_complete_scope' for r in rr),'not_evaluated':sum(r['set_status']=='old_not_evaluated_unclosed_scope' for r in rr),'field_conflicts':sum(bool(r['field_conflicts']) for r in rr),'reason_unknown':sum(r['reason']=='reason_unknown' for r in rr)})
    write_csv(root/'reports/legacy_week_summary.csv',summary)
    anomalies=read_csv(PARENT/'reports/unresolved_cases.csv')
    for r in anomalies:
        r['P3_disposition']='still_unresolved_without_original_body_or_exact_signature' if r['case_type'] in ['unfetched_chain_transactions','successful_checkpoint_missing_snapshot'] else 'retained_as_original_audit_context'
        r['original_evidence_ref']=ref(PARENT/'reports/unresolved_cases.csv',root)
    write_csv(root/'reports/unresolved_cases.csv',anomalies)
    # Capture possible legacy selection causes and local log availability without guessing signatures.
    candidates=list((PROJECT/'1021/scientific-data-essential').rglob('*.jsonl'))
    save(root/'reports/legacy_reason_audit.json',{'checks':['legacy URI gate','live discovery/page/request budget','unretrieved transaction group','native decode and execution state','IDL versions','UTC boundaries'],'not_proven_causes':'Differences retain reason_unknown until row-level old logs establish cause','local_jsonl_candidates':[str(p) for p in candidates],'unretrieved_transaction_group_count':4,'exact_signatures_recovered':False,'historical_response_bodies_restored':False,'legacy_code_ref':str(PROJECT/'1021/scientific-data-essential/code-7day-72h/mvp/acquire_chain.py')})

def metadata(root,cfg):
    root=Path(root);old=read_csv(PARENT/'processed/registry.csv');cross={r['legacy_event_key']:r for r in read_csv(PARENT/'processed/token_id_crosswalk.csv')};registry=read_csv(root/'processed/registry.csv');formal={r['token_id'] for r in registry};coverage=read_csv(PARENT/'processed/metadata_coverage.csv');snaps={r['request_id']:r for r in read_csv(LEGACY/'response_snapshots.csv')};attempts={r['request_id']:r for r in read_csv(LEGACY/'request_attempts.csv')}
    for r in coverage:r['in_formal_creation_cohort']=r['token_id'] in formal
    write_csv(root/'processed/metadata_coverage.csv',coverage)
    def observations():
        for r in iter_csv(LEGACY/'field_observations.csv'):
            if r['event_key'] not in cross:raise Halt('Legacy metadata key not in crosswalk')
            s=snaps.get(r['request_id'],{});a=attempts.get(r['request_id'],{})
            yield {**r,'metadata_observation_id':'metadata:'+sid('legacy_7day_20261008',r['request_id'],r['field_name']),'token_id':cross[r['event_key']]['token_id'],'actual_request_started_at_utc':a.get('started_at',''),'actual_request_completed_at_utc':a.get('completed_at',''),'source_retrieved_at_utc':s.get('retrieved_at',''),'response_sha256':s.get('response_sha256',''),'source_release':'legacy_7day_20261008','in_formal_creation_cohort':cross[r['event_key']]['token_id'] in formal,'historical_body_status':'not_in_slim_release','source_ref':ref(LEGACY/'field_observations.csv',root)}
    fields=list(next(iter_csv(LEGACY/'field_observations.csv')))+['metadata_observation_id','token_id','actual_request_started_at_utc','actual_request_completed_at_utc','source_retrieved_at_utc','response_sha256','source_release','in_formal_creation_cohort','historical_body_status','source_ref']
    stream_csv(root/'processed/metadata_observations.csv',observations(),fields)
    old_ids={r['token_id'] for r in old};good={r['token_id'] for r in coverage if r['final_state']=='observed'}
    stream_csv(root/'processed/token_metadata_status.csv',({'token_id':r['token_id'],'chain_key':r['chain_key'],'cohort_id':cfg['cohort_id'],'legacy_observed_cohort':r['token_id'] in old_ids,'historical_checkpoint_status':'legacy_see_metadata_coverage' if r['token_id'] in old_ids else 'not_collected_historically','historical_plan_created':False} for r in registry),['token_id','chain_key','cohort_id','legacy_observed_cohort','historical_checkpoint_status','historical_plan_created'])
    summary=[{'scope':'legacy_all','metric':'tokens_with_any_historical_JSON','numerator':len(good),'denominator':len(old_ids)},{'scope':'legacy_all','metric':'planned_checkpoints','numerator':len(coverage),'denominator':18672}]
    for state,count in sorted(Counter(r['final_state'] for r in coverage).items()):summary.append({'scope':'legacy_all','metric':'checkpoint_'+state,'numerator':count,'denominator':18672})
    for chain in CHAINS:
        ids={r['token_id'] for r in registry if r['chain_key']==chain};new=ids-old_ids
        summary.extend([{'scope':chain,'metric':'formal_tokens_with_historical_JSON','numerator':len(ids&good),'denominator':len(ids)},{'scope':chain,'metric':'formal_legacy_member_tokens','numerator':len(ids&old_ids),'denominator':len(ids)},{'scope':chain,'metric':'backfilled_not_collected_historically','numerator':len(new),'denominator':len(new)}])
    write_csv(root/'reports/metadata_cohort_coverage.csv',summary)
