"""P3 orchestration, archived native replay, validation and review artifacts."""
from core import *
from collectors import prepare_day, collect_evm, collect_solana, check_pump_idl, write_envelopes
from views import build_registry, build_expectations, legacy_audit, metadata, read_envelopes
from markets import seed_inputs, reviewed_mappings, write_market_tables, applicability, collect as collect_markets
from collections import Counter, defaultdict
import platform, resource, subprocess, sys

def input_hashes():
    d=load(P2/'reports/offline_reproduction.json');paths={Path(p) for p in d['input_hashes']}
    paths.update((P2/'processed').glob('*.csv'));paths.update((P2/'reports').glob('*receipt.json'))
    paths.update([P2/'reports/validation_results.json',P2/'reports/offline_reproduction.json',P2/'reports/stage_status.json',P2/'reports/legacy_day_identity_comparison.csv',P2/'reports/bsc_all_native_QA.csv'])
    paths.update((PARENT/'processed').glob('*.csv'));paths.update(LEGACY.glob('*.csv'));paths.add(PARENT/'reports/unresolved_cases.csv')
    paths.update(p for p in (P2/'vendor').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ['.py','.so'])
    paths.add(P2/'configs/requirements-lock.txt')
    paths.update(p for p in (PARENT/'raw').rglob('*') if p.is_file() and p.suffix in ['.body','.gz','.txt'])
    return {str(p.resolve()):sha(p) for p in sorted(paths)}

def verify_inputs(lock=None):
    lock=lock or load(ROOT/'configs/input_locks.json');missing=[];changed=[]
    for name,expected in lock.items():
        p=Path(name)
        if not p.exists():missing.append(name)
        elif sha(p)!=expected:changed.append(name)
    if missing or changed:raise Halt('Frozen P0-P2 input changed/missing: '+canonical({'missing':missing,'changed':changed}))
    return {'status':'passed','checked':len(lock),'missing':0,'changed':0}

def preflight(cfg,run_root=None):
    check_config(cfg);frozen=verify_inputs();origins=load(ROOT/'configs/reused_sources.json')
    for name,expected in origins.items():
        if sha(PARENT/name)!=expected:raise Halt('Reused P2 source changed')
    for path in (ROOT/'configs').glob('pump_*.json'):check_pump_idl(load(path))
    from native_decode import exact_evm
    import eth_abi
    saved_raw=sum(p.stat().st_size for p in (Path(run_root)/'raw').glob('*.body.gz')) if run_root is not None else 0
    remaining_raw=max(0,cfg['budgets']['max_raw_bytes']-saved_raw)
    free=shutil.disk_usage(ROOT).free;needed=2*remaining_raw+cfg['budgets']['disk_reserve_bytes']
    result={'status':'passed' if free>=needed else 'insufficient_disk_for_formal_budget','input_locks':frozen,'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'eth_abi':eth_abi.__version__,'free_disk_bytes':free,'recommended_free_disk_bytes':needed,'saved_raw_bytes_already_allocated':saved_raw,'remaining_raw_budget_bytes':remaining_raw,'disk_policy':'twofold remaining raw allowance plus unchanged reserve; fresh runs still require 34GB','candidate_days':utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']),'formal_collection_started':False,'network_requests':0,'historical_daily_capability':'must_be_verified_on_formal_start','lifecycle':'awaiting_integration','prepared_at_utc':now()}
    return result

def scope_rows(root,cfg):
    rows=[]
    for day in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']):
        for chain in CHAINS:
            d=load(Path(root)/'days'/day/(chain.replace(':','_')+'_receipt.json'),{})
            rows.append({'day':day,'chain':chain,'platform':PLATFORMS[chain],'status':d.get('status','not_attempted'),'enumeration_unit':d.get('enumeration_unit','not_attempted'),'candidate_count':d.get('candidate_count',''),'resolved_candidates':d.get('resolved_candidates',''),'native_logs_checked':d.get('native_logs_checked',''),'source_receipt':ref(Path(root)/'days'/day/(chain.replace(':','_')+'_receipt.json'),root) if d else ''})
    write_csv(Path(root)/'reports/creation_coverage.csv',rows)
    return rows

def rebase_envelope(b,source,dest):
    if b.get('header_raw_ref'):b['header_raw_ref']=ref(resolve(source,b['header_raw_ref']),dest)
    for t in b.get('transactions',[]):
        if t.get('receipt_raw_ref'):t['receipt_raw_ref']=ref(resolve(source,t['receipt_raw_ref']),dest)
    for i in b.get('instructions',[]):
        if i.get('instruction_commitment_evidence_ref'):i['instruction_commitment_evidence_ref']=ref(resolve(source,i['instruction_commitment_evidence_ref']),dest)
    return b

def import_p2_day(root):
    """Re-decode actual raw/native evidence, never copy the old Registry as output."""
    root=Path(root);day='2026-10-08';out=root/'days'/day;out.mkdir(parents=True,exist_ok=True)
    validate=load(P2/'reports/validation_results.json')
    if validate['status']!='passed_for_declared_platform_version_scope':raise Halt('P2 is not an accepted reusable input')
    def sol():
        for s in read_csv(P2/'reports/vibe_creation_segments.csv'):
            p=resolve(P2,s['raw_ref'])
            if sha(p)!=s['raw_sha256']:raise Halt('P2 normalized native hash mismatch')
            for b in read_envelopes(p):yield rebase_envelope(b,P2,root)
    receipt=load(P2/'reports/base_rpc_receipt.json');path=resolve(P2,receipt['normalized_ref'])
    if sha(path)!=receipt['normalized_sha256']:raise Halt('P2 Base evidence hash mismatch')
    qa=read_csv(P2/'reports/bsc_all_native_QA.csv');by_id={r['creation_event_id']:r for r in qa if r['status']=='passed'}
    def bsc():
        seen=set()
        for s in read_csv(P2/'reports/query_ledger_eip155_56.csv'):
            if s['status']!='complete_segment':continue
            p=resolve(P2,s['raw_ref'])
            if sha(p)!=s['raw_sha256']:raise Halt('P2 BSC raw hash mismatch')
            for b in read_envelopes(p):
                for l in b.get('logs',[]):
                    key=(l['transactionHash'],l['logIndex'])
                    if key in seen:continue
                    seen.add(key);cid='creation:'+sid('eip155:56',l['transactionHash'],str(l['logIndex']));q=by_id.get(cid)
                    if not q:raise Halt('P2 BSC log lacks all-creation native QA')
                    tx=next(t.copy() for t in b['transactions'] if t['hash']==l['transactionHash']);tx['receipt_raw_ref']=q['receipt_raw_ref']
                    envelope={'header':b['header'],'transactions':[tx],'logs':[l],'header_raw_ref':q['header_raw_ref'],'native_source':'P2_SQD+every_native_receipt_header_checked'}
                    yield rebase_envelope(envelope,P2,root)
    for chain,rows in [('solana:mainnet',sol()),('eip155:8453',(rebase_envelope(b,P2,root) for b in read_envelopes(path))),('eip155:56',bsc())]:
        # Stream the existing large envelopes instead of holding native transaction pages in memory.
        p=out/(chain.replace(':','_')+'_normalized.ndjson');tmp=p.with_suffix('.tmp')
        try:
            with tmp.open('w',encoding='utf-8') as f:
                for b in rows:f.write(canonical(b)+'\n')
            os.replace(tmp,p)
        finally:tmp.unlink(missing_ok=True)
        original={'solana:mainnet':'solana_native_creation_receipt.json','eip155:8453':'base_rpc_receipt.json','eip155:56':'bsc_all_native_QA_receipt.json'}[chain]
        save(out/(chain.replace(':','_')+'_receipt.json'),{'status':'complete_for_declared_address_topic_scope','enumeration_unit':'mandatory_PDA_transactions' if chain=='solana:mainnet' else 'block_positions','candidate_count':59404 if chain=='solana:mainnet' else '', 'resolved_candidates':59404 if chain=='solana:mainnet' else '', 'native_logs_checked':197 if chain=='eip155:8453' else (6211 if chain=='eip155:56' else ''),'source_receipt':ref(P2/'reports'/original,root),'import_policy':'replayed_native_envelopes_after_full_input_hash_lock_check','P2_scope_exclusions':['Four.meme V1']})
    save(out/'version_check.json',{'status':'passed_for_P2_declared_layout_scope','evidence_ref':ref(P2/'configs/platform_scope.csv',root),'day':day})

def build_all(root,cfg):
    scope_rows(root,cfg);build_registry(root,cfg);version_coverage(root,cfg);build_expectations(root,cfg);legacy_audit(root,cfg);metadata(root,cfg);applicability(root,cfg)

def version_coverage(root,cfg):
    root=Path(root);counts=Counter()
    for r in iter_csv(root/'processed/registry.csv'):
        version=json.loads(r['initial_attributes_json'])['native_instruction'] if r['chain_key']=='solana:mainnet' else r['platform_version_id']
        counts[(r['chain_key'],r['created_at_utc'][:10],version)]+=1
    scope={(r['chain'],r['day']):r for r in read_csv(root/'reports/creation_coverage.csv')};events=load(ROOT/'configs/platform_events.json');rows=[]
    for day in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']):
        declarations=[{'chain_key':'solana:mainnet','version':v,'address':PROGRAM,'topic0':disc} for v,disc in [('create','181ec828051c0777'),('create_v2','d6904cec5f8b31b4')]]+events
        for d in declarations:
            chain=d['chain_key'];status=scope[(chain,day)]['status'];n=counts[(chain,day,d['version'])]
            rows.append({'chain_key':chain,'platform_id':PLATFORMS[chain],'utc_day':day,'version':d['version'],'program_or_factory':d['address'],'topic_or_discriminator':d['topic0'],'observed_unique_tokens':n,'declared_complete_count':n if status.startswith('complete') else '','coverage_status':status,'version_evidence_ref':ref(root/'days'/day/'version_check.json',root),'ABI_sha256':d.get('abi_sha256','see historical IDL check'),'scope_limit':'named address/topic/layout; no full deployment or proxy-lineage claim'})
    write_csv(root/'reports/version_coverage.csv',rows)

def validate(root,cfg,preparation=False):
    root=Path(root);checks=[]
    def check(name,count,failures,kind='integrity'):
        if isinstance(failures,int):n=failures;refs=[]
        else:refs=list(failures);n=len(refs)
        checks.append({'check_id':name,'tested_count':count,'failure_count':n,'failure_refs':canonical(refs[:20]),'kind':kind,'status':'passed' if n==0 else ('pending' if kind=='coverage' else 'failed')})
    reg=read_csv(root/'processed/registry.csv');events=read_csv(root/'processed/creation_events.csv');ids={r['token_id'] for r in reg};event_ids={r['creation_event_id'] for r in events};start=epoch(cfg['candidate_start_utc']);end=epoch(cfg['candidate_end_utc'])
    check('unique_token_identity',len(reg),len(reg)-len(ids));check('unique_event_identity',len(events),len(events)-len(event_ids))
    check('registry_event_FK',len(reg),[r['token_id'] for r in reg if r['creation_event_id'] not in event_ids]);check('creation_UTC_range',len(reg),[r['token_id'] for r in reg if not start<=epoch(r['created_at_utc'])<end]);check('native_success_only',len(reg),[r['token_id'] for r in reg if r['execution_status']!='success_committed'])
    check('stable_chain_address_identity',len(reg),[r['token_id'] for r in reg if token_id(r['chain_key'],r['token_address_canonical'])!=r['token_id']])
    evidence={};missing=[]
    for r in reg:
        for key in ['native_receipt_raw_ref','native_block_raw_ref']:
            value=r.get(key,'')
            if not value or not resolve(root,value).is_file():missing.append(r['creation_event_id']+':'+key)
            else:evidence[value]=resolve(root,value)
        if r['chain_key']=='solana:mainnet' and (not r.get('instruction_commitment_evidence_ref') or not resolve(root,r['instruction_commitment_evidence_ref']).is_file()):missing.append(r['creation_event_id']+':commitment')
    check('native_transaction_and_block_evidence_present',len(reg),missing)
    prices={p['price_observation_id']:p for p in read_csv(root/'processed/pm_prices.csv')};maps={m['mapping_id']:m for m in read_csv(root/'processed/pm_mapping.csv')};markets={m['market_snapshot_id']:m for m in read_csv(root/'processed/pm_markets.csv')}
    joined=set();seen=set();errors=Counter();count=0;lookup={r['token_id']:r for r in reg};from views import mapping_applies, PriceIndex
    index=PriceIndex(list(prices.values()))
    for row in iter_csv(root/'processed/token_expectations_at_creation.csv'):
        count+=1;joined.add(row['token_id'])
        if row['expectation_link_id'] in seen:errors['duplicate_link']+=1
        seen.add(row['expectation_link_id']);m=maps.get(row['mapping_id']);r=lookup.get(row['token_id'])
        if r is None or row['creation_event_id']!=r['creation_event_id']:errors['registry_link_FK']+=1;continue
        if row['match_status']=='matched_valid':
            p=prices.get(row['price_observation_id'])
            if p is None or m is None:errors['price_mapping_FK']+=1;continue
            age=epoch(row['anchor_time_utc'])-epoch(p['effective_information_time_utc'])
            if not 0<age<=cfg['price']['primary_max_age_hours']*3600:errors['strict_prior_information_and_age']+=1
            if p['pm_outcome_key']!=m['pm_outcome_key'] or p['market_snapshot_id']!=m['market_snapshot_id']:errors['outcome_snapshot_FK']+=1
            expected,status=index.select(m['pm_outcome_key'],row['anchor_time_utc'],cfg['price']['primary_max_age_hours'],markets[m['market_snapshot_id']],m)
            if not mapping_applies(m,r) or expected is None or expected['price_observation_id']!=p['price_observation_id']:errors['mapping_semantics_and_last_valid_price']+=1
        elif row['price'] or row['price_observation_id']:errors['unmatched_has_fake_price']+=1
    check('left_join_exact_token_set',len(ids),list(ids^joined))
    for key in ['duplicate_link','registry_link_FK','price_mapping_FK','strict_prior_information_and_age','outcome_snapshot_FK','mapping_semantics_and_last_valid_price','unmatched_has_fake_price']:check(key,count,errors[key])
    from decimal import Decimal
    check('finite_price_0_to_1',len(prices),[k for k,p in prices.items() if not Decimal(p['price']).is_finite() or not 0<=Decimal(p['price'])<=1])
    cov=read_csv(root/'processed/metadata_coverage.csv');obs=read_csv(root/'processed/metadata_observations.csv')
    check('legacy_checkpoint_count_unchanged',len(cov),int(len(cov)!=18672));check('legacy_field_rows_preserved',len(obs),int(len(obs)!=133888))
    old_coverage=read_csv(PARENT/'processed/metadata_coverage.csv');original={(r['event_key'],r['checkpoint']):r for r in old_coverage};changed=[]
    for r in cov:
        old=original.get((r['event_key'],r['checkpoint']))
        if old is None or any(r.get(k)!=v for k,v in old.items()):changed.append(r['event_key']+':'+r['checkpoint'])
    check('legacy_plans_states_and_original_clocks_preserved',len(cov),changed)
    field_changes=[]
    for actual,old in zip(obs,iter_csv(LEGACY/'field_observations.csv')):
        if any(actual.get(k)!=v for k,v in old.items()):field_changes.append(actual['metadata_observation_id'])
    check('all_original_metadata_field_values_preserved',len(obs),field_changes)
    check('unique_metadata_observation_identity',len(obs),len(obs)-len({r['metadata_observation_id'] for r in obs}))
    statuses=read_csv(root/'processed/token_metadata_status.csv');check('backfills_not_fake_historical_observations',len(statuses),[r['token_id'] for r in statuses if not truth(r['legacy_observed_cohort']) and r['historical_checkpoint_status']!='not_collected_historically'])
    coverage=read_csv(root/'reports/creation_coverage.csv');check('all_declared_chain_days_closed',len(coverage),[r['chain']+':'+r['day'] for r in coverage if not r['status'].startswith('complete')],'coverage')
    week=read_csv(root/'reports/legacy_week_summary.csv');check('whole_legacy_week_audited',7,[r['utc_day'] for r in week if not r['coverage_status'].startswith('complete')],'coverage')
    cat=read_csv(root/'reports/market_category_coverage.csv');check('all_requested_categories_queried',len(cfg['categories']),[r['category'] for r in cat if not truth(r['active_queried']) or not truth(r['closed_queried']) or r['search_status']=='partial_source_failures'],'coverage')
    feasible=read_csv(root/'reports/polymarket_feasibility.csv')
    check('selected_outcome_rules_reviewed',len(feasible),[r['pm_outcome_key'] for r in feasible if not truth(r['rules_checked'])],'coverage')
    history=read_csv(root/'reports/history_requests.csv')
    check('history_pagination_and_request_status',len(history),[r['outcome'] for r in history if r['status'] in ['partial_page_cap','request_failed','not_attempted_outcome_budget']],'coverage')
    check('lifecycle_disabled',1,int(cfg['lifecycle_enabled'] or cfg['common_cutoff_utc'] is not None))
    check('fixture_rows_excluded',len(reg),[r['token_id'] for r in reg if r.get('dataset_kind')=='synthetic_test'])
    check('all_mapping_rule_evidence_present',len(maps),[k for k,m in maps.items() if not resolve(root,m['rule_snapshot_ref']).is_file()])
    meta_paths=list((root/'raw').glob('*.meta.json'));raw_errors=[]
    for path in meta_paths:
        m=load(path);p=resolve(root,m['raw_ref'])
        if not p.is_file() or sha(p)!=m['sha256']:raw_errors.append(str(path))
    check('saved_public_response_hashes',len(meta_paths),raw_errors)
    if not preparation:
        reproduction=load(root/'reports/offline_reproduction.json',{})
        valid_reproduction=reproduction.get('status')=='passed' and reproduction.get('second_output_hashes')==processed_hashes(root)
        check('P3_fixed_input_zero_network_reproduction',1,int(not valid_reproduction))
        qa=load(root/'reports/native_QA_receipt.json',{});check('fixed_seed_independent_native_QA',1,int(qa.get('status')!='passed'))
        versions=[load(root/'days'/d/'version_check.json',{}) for d in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc'])]
        check('historical_daily_version_checks',len(versions),sum(not v.get('status','').startswith('passed') for v in versions),'coverage')
        check('formal_scope_frozen',1,int(not cfg.get('formal_window_frozen')),'coverage')
    result={'status':'failed' if any(r['status']=='failed' for r in checks) else ('passed_integrity_with_pending_P3_coverage' if any(r['status']=='pending' for r in checks) else 'passed_for_declared_P3_scope'),'scope':'preparation_real_P2_replay' if preparation else 'P3_formal','formal_P3_completed':not preparation and all(r['status']=='passed' for r in checks),'checks':checks,'token_count':len(reg),'counts_by_chain':dict(Counter(r['chain_key'] for r in reg)),'expectation_rows':count,'evidence_files':len(evidence),'lifecycle':'awaiting_integration','price_feature_readiness':'retrospective_demonstration_only','checked_at_utc':now()}
    save(root/'reports/validation_results.json',result);write_csv(root/'reports/validation_checks.csv',checks);return result

def processed_hashes(root):return {p.name:sha(p) for p in sorted((Path(root)/'processed').glob('*.csv'))}

def reproduce(root,cfg):
    """Rebuild derived outputs twice while denying network at the transport boundary."""
    from unittest.mock import patch
    root=Path(root)
    sources=list((root/'days').rglob('*.ndjson'))+list((root/'days').rglob('*.json'))
    sources += [root/'processed'/name for name in ['pm_markets.csv','pm_outcomes.csv','pm_prices.csv','pm_mapping.csv']]
    sources += list((ROOT/'code').glob('*.py'))+[ROOT/'configs/input_locks.json']
    sources.append(root/'configs/mapping_reviews.csv' if (root/'configs/mapping_reviews.csv').exists() else ROOT/'configs/mapping_reviews.csv')
    before={str(p.resolve()):sha(p) for p in sorted(sources)};started=time.monotonic()
    with patch('urllib.request.urlopen',side_effect=Halt('Network prohibited in offline reproduction')):
        build_all(root,cfg);first=processed_hashes(root);build_all(root,cfg);second=processed_hashes(root)
    after={str(p.resolve()):sha(p) for p in sorted(sources)}
    result={'status':'passed' if first==second and before==after else 'failed','network_requests':0,'network_denied_during_rebuild':True,'byte_identical_processed_outputs':first==second,'input_snapshot_unchanged':before==after,'input_hashes':before,'first_output_hashes':first,'second_output_hashes':second,'elapsed_seconds':round(time.monotonic()-started,3),'completed_at_utc':now()}
    save(root/'reports/offline_reproduction.json',result)
    if result['status']!='passed':raise Halt('Offline reproduction mismatch')
    return result

def native_qa(client,cfg):
    """Fixed-seed Solana replay plus first/last, nested, versioned and empty URI cases."""
    import random
    from native_call_tree import native_creations
    from native_decode import pump_args
    rows=[r for r in read_csv(client.root/'processed/registry.csv') if r['chain_key']=='solana:mainnet'];groups=defaultdict(list)
    for r in rows:groups[(r['created_at_utc'][:10],json.loads(r['initial_attributes_json'])['native_instruction'])].append(r)
    rng=random.Random(cfg['random_seed']);selected={}
    for key,group in sorted(groups.items()):
        group.sort(key=lambda r:r['creation_event_id'])
        for r in rng.sample(group,min(10,len(group))):selected[r['creation_event_id']]=r
        for r in [min(group,key=lambda r:r['created_at_utc']),max(group,key=lambda r:r['created_at_utc'])]:selected[r['creation_event_id']]=r
        for predicate in [lambda r:len(json.loads(r['native_instruction_path']))>1,lambda r:not r['initial_metadata_uri'],lambda r:r['transaction_format_version']=='1']:
            risk=next((r for r in group if predicate(r)),None)
            if risk:selected[risk['creation_event_id']]=risk
    url=cfg['sources']['solana_rpc'];checks=[]
    for r in sorted(selected.values(),key=lambda r:r['creation_event_id']):
        tx,tm=client.rpc(url,'getTransaction',[r['creation_tx_hash_or_signature'],{'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1}],'P3_fixed_seed_native_QA_transaction')
        h,hm=client.rpc(url,'getBlock',[int(r['block_height_or_slot']),{'commitment':'finalized','transactionDetails':'none','rewards':False,'maxSupportedTransactionVersion':1}],'P3_fixed_seed_native_QA_header')
        if tx['transaction']['signatures'][0]!=r['creation_tx_hash_or_signature'] or tx['slot']!=int(r['block_height_or_slot']) or iso(tx['blockTime'])!=r['created_at_utc'] or h['blockhash']!=r['block_hash'] or h['blockTime']!=tx['blockTime']:raise Halt('Independent Solana QA identity/time/header mismatch')
        tx['transactionIndex']=int(r['transaction_index']);items=[i for i in native_creations(tx) if json.dumps(i['instructionAddress'],separators=(',',':'))==r['native_instruction_path']]
        if len(items)!=1 or items[0]['isCommitted'] is not True:raise Halt('Independent Solana QA commitment unknown/conflicting')
        args=pump_args(items[0]['data']);args['instruction_user_signer_address']=items[0]['accounts'][5 if args['native_instruction']=='create_v2' else 7]
        if args!=json.loads(r['initial_attributes_json']) or items[0]['accounts'][0]!=r['token_address_raw']:raise Halt('Independent Solana QA mint/creator/parameter mismatch')
        checks.append({'creation_event_id':r['creation_event_id'],'token_id':r['token_id'],'day':r['created_at_utc'][:10],'status':'passed','transaction_raw_ref':tm['raw_ref'],'header_raw_ref':hm['raw_ref']})
    write_csv(client.root/'reports/native_QA.csv',checks,['creation_event_id','token_id','day','status','transaction_raw_ref','header_raw_ref'])
    save(client.root/'reports/native_QA_receipt.json',{'status':'passed','seed':cfg['random_seed'],'groups':len(groups),'required_sample_ids':sorted(selected),'checked':len(checks),'claim':'programmatic fixed-seed/risk replay; not manual review of the full cohort'})

def artifacts(root,cfg,result):
    root=Path(root);rows=[]
    for p in sorted((root/'processed').glob('*.csv')):
        with p.open(newline='',encoding='utf-8') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;count=sum(1 for _ in reader)
        rows.append({'path':ref(p,root),'sha256':sha(p),'bytes':p.stat().st_size,'rows':count,'columns':canonical(fields),'cohort_id':cfg['cohort_id']})
    write_csv(root/'provenance/processed_manifest.csv',rows)
    # Dictionary contains actual generated columns, derivations and source domains.
    dictionaries=[]
    descriptions={'token_id':'chain-qualified token identity; EVM lowercase/Solana case-preserving','created_at_utc':'native block timestamp in UTC','legacy_observed_cohort':'membership in original 4668-token observation cohort','historical_checkpoint_status':'backfills never inherit old checkpoint observations','price':'source API scalar; construction unconfirmed','price_age_hours':'anchor minus effective information end in hours','effective_information_time_utc':'bucket start plus returned resolution; strictly before anchor','final_state':'original legacy checkpoint terminal state; parse failure may include missing evidence','reason':'row-level cause; unknown unless supported by old/native evidence','value_hash':'legacy field-value summary; full HTTP body unavailable','allowed_value':'legacy exported value, preserved without reconstruction'}
    for row in rows:
        for column in json.loads(row['columns']):
            dictionaries.append({'table':Path(row['path']).stem,'column':column,'dtype':'string (IDs/integers preserved exactly)','definition':descriptions.get(column,'Preserved named source field or deterministic derivation; see code/'+('markets.py' if Path(row['path']).stem.startswith('pm_') else 'views.py')),'unit':'UTC' if column.endswith('_utc') else ('hours' if 'hours' in column else ''),'null_reason':'not_acquired/not_applicable/unmatched; see status/reason columns','source':'pinned native evidence/P1 market snapshot/legacy six-table archive','version':cfg['protocol_version']})
    write_csv(root/'configs/data_dictionary.csv',dictionaries)
    scope=read_csv(root/'reports/creation_coverage.csv');summary='\n'.join('- '+r['chain']+' '+r['day']+': '+r['status'] for r in scope)
    text=f"# P3 数据与验证记录\n\n状态：{result['status']}。本运行类型：{result['scope']}。正式 P3 完成：{result['formal_P3_completed']}。\n\nRegistry {result['token_count']} 个币；预期长表 {result['expectation_rows']} 行。\n\n{summary}\n\n历史规则与价格构造限制仍保留；真实生命周期 awaiting_integration；共同 cutoff 为空。4 笔缺签名交易及缺正文检查点保留在异常表，不能视为已修复。\n\n## Methods\n逐日、声明地址/事件范围，原生交易/receipt 与区块证据核验；创建资格不使用 URI、交易或迁移结果。预期按 outcome/mapping 连接，桶结束严格早于锚点，24 小时主陈旧度及12/48小时敏感性。\n\n## Data Records\n实际文件、哈希、粒度及列见 provenance/processed_manifest.csv 和 configs/data_dictionary.csv。\n\n## Data Overview\n按链数量：{canonical(result['counts_by_chain'])}。直接身份与背景覆盖分别见 reports/expectation_coverage.csv，日背景见 background_day_coverage.csv。\n\n## Technical Validation\n检查 {len(result['checks'])} 项；失败 {sum(r['status']=='failed' for r in result['checks'])} 项；待完成覆盖 {sum(r['status']=='pending' for r in result['checks'])} 项。完整记录见 validation_checks.csv。\n\n## Usage Notes\n按 token_id 左连接；长表行数不是币数。原始18,672个历史计划不扩写，新增币未历史采集。此稿按当前验证结果生成，不宣称因果或已认证事前特征。\n"
    atomic(root/'reports/P3_run_report.md',text.encode());atomic(root/'manuscript/P3_sections.md',text.encode())
    sources=[]
    for name,url in cfg['sources'].items():sources.append({'source_id':name,'endpoint':url,'access':'public_without_private_credentials','acquisition_status':'see request ledger; prepared endpoint is not an actual access result','raw_redistribution_status':'not_reviewed_local_only','history_limitations':'provider/date-specific; failures and partial coverage retained'})
    write_csv(root/'configs/source_inventory.csv',sources)
    # P3 updates the actual panel inputs; the final five-panel artwork is P4.
    reg=read_csv(root/'processed/registry.csv');counts=Counter((r['chain_key'],r['created_at_utc'][:10]) for r in reg)
    activity=[{**r,'observed_created_tokens':counts[(r['chain'],r['day'])],'count_unit':'distinct token_id/day','cohort_id':cfg['cohort_id']} for r in scope]
    write_csv(root/'figures/data/panel_A_activity.csv',activity)
    write_csv(root/'figures/data/panel_B_coverage.csv',scope)
    write_csv(root/'figures/data/panel_C_links.csv',read_csv(root/'reports/expectation_coverage.csv'))
    metadata_cov=read_csv(root/'processed/metadata_coverage.csv');terminal=Counter((r['checkpoint'],r['final_state']) for r in metadata_cov)
    write_csv(root/'figures/data/panel_D_metadata.csv',[{'legacy_cohort':'legacy_7day_20261008','checkpoint':checkpoint,'final_state':state,'checkpoints':n,'checkpoint_denominator':4668,'note':'parse_failed includes evidence missing; not lifecycle death'} for (checkpoint,state),n in sorted(terminal.items())])
    atomic(root/'figures/data/panel_E_alignment.csv',(root/'processed/context_daily.csv').read_bytes())

def replay(root,cfg):
    root=Path(root)
    if root.exists() and any(root.iterdir()):raise Halt('Replay output must be a new empty directory')
    root.mkdir(parents=True,exist_ok=True);cfg={**cfg,'candidate_start_utc':'2026-10-08T00:00:00Z','candidate_end_utc':'2026-10-09T00:00:00Z','cohort_id':'p3_preparation_real_P2_replay','dataset_kind':'real_archived_replay'};save(root/'configs/protocol.json',cfg);verify_inputs()
    atomic(root/'configs/mapping_reviews.csv',(ROOT/'configs/mapping_reviews.csv').read_bytes())
    import_p2_day(root);seed=seed_inputs(root);seed['pm_mapping']=reviewed_mappings(seed['pm_markets'],seed['pm_outcomes'],root);write_market_tables(root,seed)
    build_all(root,cfg);first=processed_hashes(root);result=validate(root,cfg,True)
    reference={r['token_id']:r for r in read_csv(P2/'processed/registry.csv')};current={r['token_id']:r for r in read_csv(root/'processed/registry.csv')};fields=['creation_event_id','creation_tx_hash_or_signature','created_at_utc','creator_address','initial_attributes_json','block_hash','native_instruction_path','log_index']
    differences=[]
    for tid in sorted(set(reference)|set(current)):
        a,b=reference.get(tid),current.get(tid)
        if a is None or b is None:differences.append({'token_id':tid,'field':'set_membership'});continue
        for field in fields:
            if a.get(field,'')!=b.get(field,''):differences.append({'token_id':tid,'field':field})
    write_csv(root/'reports/P2_native_comparison.csv',differences,['token_id','field'])
    build_all(root,cfg);second=processed_hashes(root)
    replay_result={'status':'passed' if not differences and first==second and result['status']!='failed' else 'failed','real_native_records_compared':len(reference),'comparison_fields':fields,'differences':len(differences),'network_requests':0,'byte_identical_processed_outputs':first==second,'first_output_hashes':first,'second_output_hashes':second,'formal_P3_started':False,'note':'P3 whole-week and category coverage deliberately remain pending; this is a real archived input test, not formal collection','checked_at_utc':now()}
    save(root/'reports/replay_result.json',replay_result);artifacts(root,cfg,result);return replay_result

def run(root,cfg,authorized=False):
    if not authorized:raise Halt('Formal collection is disabled. User must explicitly request start; then pass --authorize-formal-run.')
    root=guard_output(root)
    pf=preflight(cfg,root)
    if pf['status']!='passed':raise Halt(pf['status'])
    root.mkdir(parents=True,exist_ok=True)
    with run_lock(root):
        frozen=load(root/'configs/protocol.json');code={p.name:sha(p) for p in sorted((ROOT/'code').glob('*.py'))};code_lock=load(root/'configs/code_lock.json')
        if code_lock is not None and code_lock!=code:raise Halt('Code changed during a frozen run; use an explicit new run/version')
        save(root/'configs/code_lock.json',code)
        if not (root/'configs/mapping_reviews.csv').exists():atomic(root/'configs/mapping_reviews.csv',(ROOT/'configs/mapping_reviews.csv').read_bytes())
        if frozen:
            if frozen['prepared_protocol_hash']!=digest(cfg):raise Halt('Protocol changed on resume; use new run/version')
            run_cfg=frozen
        else:
            run_cfg={**cfg,'cohort_id':cfg['protocol_version']+'_'+cfg['candidate_start_utc'][:10]+'_'+cfg['candidate_end_utc'][:10],'prepared_protocol_hash':digest(cfg),'formal_window_frozen':False,'run_authorized_at_utc':now(),'dataset_kind':'real_formal'}
        save(root/'configs/protocol.json',run_cfg);client=Client(root,run_cfg,online=True);started=now();clock=time.monotonic();failures=[];run_status='running';stop_reason=''
        try:
            # Verify all dates' source/version capability before freezing promised scope.
            for day in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']):
                if day=='2026-10-08' and cfg['reuse_validated_P2_day']:continue
                prepare_day(client,day)
            run_cfg['formal_window_frozen']=True;save(root/'configs/protocol.json',run_cfg)
            for day in utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']):
                if day=='2026-10-08' and cfg['reuse_validated_P2_day']:
                    if not (root/'days'/day/'solana_mainnet_receipt.json').exists():import_p2_day(root)
                    continue
                bounds=prepare_day(client,day)['bounds']
                for chain in ['eip155:8453','eip155:56','solana:mainnet']:
                    p=root/'days'/day/(chain.replace(':','_')+'_receipt.json')
                    if load(p,{}).get('status','').startswith('complete'):continue
                    try:
                        (collect_solana(client,day,bounds[chain]) if chain=='solana:mainnet' else collect_evm(client,day,chain,bounds[chain]))
                    except Halt as e:
                        failures.append({'day':day,'chain':chain,'error':str(e),'at_utc':now()});save(root/'state/failures.json',failures)
                        if 'budget' in str(e).lower():raise
                scope_rows(root,run_cfg)
            final_coverage=scope_rows(root,run_cfg)
            pending=[r['chain']+':'+r['day'] for r in final_coverage if not r['status'].startswith('complete')]
            if pending:
                result={'status':'collection_pending_coverage','pending_chain_days':pending,'derived_build_deferred':True,
                        'note':'Saved collection checkpoints retained; large derived tables, QA, and offline reproduction are deferred until all declared chain-days close.'}
                run_status=result['status'];return result
            collect_markets(client);build_all(root,run_cfg);native_qa(client,run_cfg);reproduce(root,run_cfg);result=validate(root,run_cfg);artifacts(root,run_cfg,result)
            if result['status']=='failed':raise Halt('P3 data integrity failed; see validation report')
            run_status=result['status']
            return result
        except BaseException as e:
            run_status='stopped_with_saved_checkpoints';stop_reason=type(e).__name__+': '+str(e)
            raise
        finally:
            scope_rows(root,run_cfg)
            run_receipt={'started_at_utc':started,'finished_at_utc':now(),'elapsed_seconds':round(time.monotonic()-clock,3),'network_requests_this_invocation':client.calls,'RPC_elements_this_invocation':client.elements,'stored_raw_bytes':client.stored,'peak_RSS_raw':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'RSS_units':'bytes on macOS; KiB on Linux','failures':failures,'status':run_status,'stop_reason':stop_reason,'lifecycle':'awaiting_integration','formal_window_frozen':run_cfg['formal_window_frozen']}
            save(root/'reports/run_receipt.json',run_receipt);append_json(root/'provenance/run_history.jsonl',run_receipt)

def smoke(root,cfg):
    """Exactly seven tiny public read probes, never a formal range enumeration."""
    c=Client(root,cfg,online=True,request_cap=7);results=[]
    calls=[('solana',lambda:c.rpc(cfg['sources']['solana_rpc'],'getBlockTime',[454377023])),('base',lambda:c.rpc(cfg['sources']['base_rpc'],'eth_getBlockByNumber',['0x'+format(52314127,'x'),False])),('bsc',lambda:c.rpc(cfg['sources']['bsc_rpc'],'eth_getBlockByNumber',['0x'+format(126344214,'x'),False])),('vibe',lambda:c.rpc(cfg['sources']['vibe'],'getTransactionsForAddress',[AUTHORITY,{'transactionDetails':'full','sortOrder':'asc','limit':1,'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1,'filters':{'slot':{'gte':454377023,'lt':454698759}}}])),('polymarket',lambda:c.json(cfg['sources']['gamma']+'/markets/2589811')),('headers_sql',lambda:c.request(cfg['sources']['headers_sql'],raw_sql='SELECT slot,block_hash FROM solana.blocks WHERE slot=454377023 LIMIT 1 FORMAT JSON')),('sqd',lambda:c.request(cfg['sources']['bsc_archive'],{'type':'evm','fromBlock':126344214,'toBlock':126344214,'fields':{'block':{'number':True,'hash':True,'timestamp':True}},'includeAllBlocks':True},'one_block_smoke'))]
    # No retries: the seven-request ceiling includes failures, not seven successes.
    c.cfg={**cfg,'budgets':{**cfg['budgets'],'max_attempts_per_request':1,'timeout_seconds':10}}
    for name,fn in calls:
        try:
            data,m=fn();results.append({'source':name,'status':'passed_public_response','raw_ref':m['raw_ref'],'note':'single probe only; full target-date scope remains unproved'})
        except Exception as e:results.append({'source':name,'status':'unavailable_in_this_test','error':str(e)})
    report={'status':'passed' if all(r['status'].startswith('passed') for r in results) else 'partial_live_capability','requests':c.calls,'formal_collection_started':False,'results':results,'tested_at_utc':now()};save(Path(root)/'reports/online_smoke.json',report);return report

def guard_output(root):
    root=Path(root).resolve()
    if not any(parent in root.parents for parent in [ROOT/'runs',ROOT/'test_outputs']):raise Halt('Output must be a new run directory below p3/runs/ or p3/test_outputs/; P0-P2 are protected')
    return root

def apply_reviews(root,review_file,defer_rebuild=False):
    """Explicit local semantic-review amendment; retains earlier version and inputs."""
    root=guard_output(root);cfg=load(root/'configs/protocol.json')
    if cfg is None:raise Halt('No run protocol to review')
    reviews=read_csv(review_file)
    required=['market_id','outcome_label','rules_sha256','reviewed_by']
    for r in reviews:
        if any(not r.get(k) for k in required):raise Halt('Review row missing evidence/identity/period/reviewer fields')
        if r.get('review_decision')!='catalogue_only':
            if any(not r.get(k) for k in ['link_type','target_type','target_id','applicable_chain_keys','semantic_valid_from_utc','semantic_valid_to_utc']):raise Halt('Mapping review missing typed target and period')
            epoch(r['semantic_valid_from_utc']);epoch(r['semantic_valid_to_utc'])
        elif not r.get('decision_reason'):raise Halt('Catalogue-only review needs an explicit reason')
    markets=read_csv(root/'processed/pm_markets.csv');outcomes=read_csv(root/'processed/pm_outcomes.csv')
    from markets import reviewed_mappings
    new=reviewed_mappings(markets,outcomes,root,reviews=reviews)
    known={(m['market_id'],m['rules_sha256']) for m in markets}
    if any((r['market_id'],r['rules_sha256']) not in known for r in reviews):raise Halt('Review rule hash does not match a saved market snapshot')
    with run_lock(root):
        old=root/'configs/mapping_reviews.csv'
        if old.exists():atomic(root/'configs/review_history'/(sha(old)+'.csv'),old.read_bytes())
        atomic(old,Path(review_file).read_bytes())
        write_csv(root/'processed/pm_mapping.csv',new,['mapping_id','link_type','target_id','applicable_chain_keys','pm_outcome_key','market_snapshot_id','semantic_valid_from_utc','semantic_valid_to_utc'] if not new else None)
        append_json(root/'provenance/review_amendments.jsonl',{'at_utc':now(),'review_sha256':sha(old),'maps':len(new),'prior_reviews_preserved':True})
        if defer_rebuild:
            # A scheduled collection continuation will rebuild once after native
            # acquisition. Never leave old validation looking current meanwhile.
            for name in ['validation_results.json','offline_reproduction.json']:
                report=root/'reports'/name
                if report.exists():atomic(root/'configs/review_history'/(sha(report)+'_'+name),report.read_bytes())
                save(report,{'status':'pending_rebuild_after_review_amendment','formal_P3_completed':False,'review_sha256':sha(old),'invalidated_at_utc':now()})
            result={'status':'reviews_validated_pending_rebuild','review_rows':len(reviews),'maps':len(new),'review_sha256':sha(old),'formal_P3_completed':False}
            save(root/'reports/review_application.json',result);return result
        build_all(root,cfg);reproduce(root,cfg);result=validate(root,cfg,cfg.get('dataset_kind')=='real_archived_replay');artifacts(root,cfg,result);return result
