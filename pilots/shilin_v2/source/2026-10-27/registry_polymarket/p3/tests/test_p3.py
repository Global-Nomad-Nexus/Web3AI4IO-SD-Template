"""Meaningful safety, time, source and restart tests; fixtures stay in tempdirs."""
import sys,unittest,tempfile,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from core import *
from views import PriceIndex,mapping_applies,decode_envelopes
from markets import normalize_price,write_market_tables,reviewed_mappings
from collectors import validate_stream,rpc_batch,solana_history,evm_logs,check_pump_idl,collect_evm
from pipeline import run,guard_output

class PriceBoundaries(unittest.TestCase):
    def setUp(self):
        self.market={'opened_at_utc':'2026-10-01T00:00:00Z','scheduled_close_at_utc':'2026-11-01T00:00:00Z','actual_close_at_utc':'','resolved_at_utc':''}
        self.mapping={'semantic_valid_from_utc':'2026-10-01T00:00:00Z','semantic_valid_to_utc':'2026-11-01T00:00:00Z'}
    def price(self,t='2026-10-08T00:00:00Z',width=1800):
        return {'price_observation_id':'p1','pm_outcome_key':'o','effective_information_time_utc':t,'resolution_seconds':width,'eligible_for_asof':True,'is_settlement_point':False}
    def choose(self,anchor,prices=None,age=24):return PriceIndex(prices or [self.price()]).select('o',anchor,age,self.market,self.mapping)
    def test_same_second_excluded(self):self.assertIsNone(self.choose('2026-10-08T00:00:00Z')[0])
    def test_after_bucket_end_allowed(self):self.assertEqual(self.choose('2026-10-08T00:00:01Z')[1],'matched_valid')
    def test_unfinished_bucket_excluded(self):self.assertIsNone(self.choose('2026-10-07T23:45:00Z')[0])
    def test_exact_age_allowed(self):self.assertEqual(self.choose('2026-10-09T00:00:00Z')[1],'matched_valid')
    def test_stale_not_filled(self):self.assertEqual(self.choose('2026-10-09T00:00:01Z')[1],'stale_price')
    def test_resolution_zero_excluded(self):self.assertIsNone(self.choose('2026-10-08T00:00:01Z',[self.price(width=0)])[0])
    def test_closed_boundary_excluded(self):
        self.market['actual_close_at_utc']='2026-10-08T00:00:01Z';self.assertEqual(self.choose('2026-10-08T00:00:01Z')[1],'market_closed_or_resolved')
    def test_Gamma_short_UTC_offset_closes_at_same_instant(self):
        self.market['actual_close_at_utc']='2026-10-08 00:00:01+00';self.assertEqual(self.choose('2026-10-08T00:00:01Z')[1],'market_closed_or_resolved')
    def test_mapping_expiry(self):
        self.mapping['semantic_valid_to_utc']='2026-10-08T00:00:01Z';self.assertEqual(self.choose('2026-10-08T00:00:01Z')[1],'mapping_outside_validity')
    def test_settlement_flag_excluded(self):
        p=self.price();p['is_settlement_point']=True;self.assertIsNone(self.choose('2026-10-08T00:00:01Z',[p])[0])
    def test_mixed_resolution_series_not_silently_stitched(self):
        prices=[self.price(),{**self.price(width=300),'price_observation_id':'p2'}]
        self.assertEqual(self.choose('2026-10-08T00:00:01Z',prices)[1],'ambiguous_resolution_series_requires_review')
        self.mapping['history_resolution_seconds']='1800'
        self.assertEqual(self.choose('2026-10-08T00:00:01Z',prices)[0]['price_observation_id'],'p1')
    def test_price_nan_rejected(self):
        with self.assertRaises(Halt):normalize_price({'timestamp':1,'resolution_seconds':1,'price':'NaN'},'o','s',{'retrieved_at_utc':'x','request_id':'q','raw_ref':'r'},0,10)
    def test_price_timestamp_outside_range_rejected(self):
        with self.assertRaises(Halt):normalize_price({'timestamp':10,'resolution_seconds':1,'price':'.5'},'o','s',{'retrieved_at_utc':'x','request_id':'q','raw_ref':'r'},0,10)
    def test_documented_settlement_at_end_is_retained_but_ineligible(self):
        p=normalize_price({'timestamp':10,'resolution_seconds':0,'price':'1'},'o','s',{'retrieved_at_utc':'x','request_id':'q','raw_ref':'r'},0,10)
        self.assertFalse(p['eligible_for_asof']);self.assertEqual(p['resolution_seconds'],0)
        with self.assertRaises(Halt):normalize_price({'timestamp':11,'resolution_seconds':0,'price':'1'},'o','s',{'retrieved_at_utc':'x','request_id':'q','raw_ref':'r'},0,10)
    def test_mixed_price_sources_conflict_not_silently_deduped(self):
        with tempfile.TemporaryDirectory() as d:
            p={'price_observation_id':'a','pm_outcome_key':'o','source_timestamp_utc':'t','resolution_seconds':1,'price':'.1'}
            with self.assertRaises(Halt):write_market_tables(d,{'pm_prices':[p,{**p,'price_observation_id':'b','price':'.2'}]})

class SemanticCategoryRegression(unittest.TestCase):
    def test_listing_search_hit_is_not_automatically_revenue_evidence(self):
        from markets import applicability
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)
            write_csv(r/'processed/pm_markets.csv',[{'market_id':'1','market_snapshot_id':'s','rules_sha256':'h','opened_at_utc':'2026-01-01T00:00:00Z','scheduled_close_at_utc':'2027-01-01T00:00:00Z'}])
            write_csv(r/'processed/pm_outcomes.csv',[{'market_snapshot_id':'s','pm_outcome_key':'o'}])
            write_csv(r/'processed/pm_mapping.csv',[{'market_snapshot_id':'s','pm_outcome_key':'o'}])
            write_csv(r/'processed/pm_prices.csv',[{'pm_outcome_key':'o','eligible_for_asof':True,'resolution_seconds':300,'price':'.5'}])
            write_csv(r/'processed/pm_candidate_catalogue.csv',[{'market_id':'1','category':c} for c in ['pump_listing','pump_revenue']])
            write_csv(r/'configs/mapping_reviews.csv',[{'market_id':'1','rules_sha256':'h','semantic_categories':'pump_listing'}])
            applicability(r,default_config());rows={x['category']:x for x in read_csv(r/'reports/polymarket_feasibility.csv')}
            self.assertEqual(rows['pump_listing']['decision'],'limited_for_demonstration');self.assertEqual(rows['pump_revenue']['decision'],'catalogue_only');self.assertEqual(rows['pump_revenue']['reason'],'query_false_positive_wrong_semantic_category')

class IdentityAndRunGates(unittest.TestCase):
    def test_cross_chain_same_address_separate(self):
        a='0x'+'AB'*20;self.assertNotEqual(token_id('eip155:56',a),token_id('eip155:8453',a));self.assertTrue(token_id('eip155:56',a).endswith(a.lower()))
    def test_solana_case_preserved(self):
        self.assertNotEqual(token_id('solana:mainnet','Abc'+'1'*29),token_id('solana:mainnet','abc'+'1'*29))
    def test_explicit_formal_start_required_before_any_write(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'never'
            with self.assertRaises(Halt):run(path,default_config())
            self.assertFalse(path.exists())
    def test_one_writer_per_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            with run_lock(d):
                with self.assertRaises(Halt):
                    with run_lock(d):pass
            self.assertFalse((Path(d)/'.run.lock').exists())
    def test_window_requires_UTC_midnight(self):
        with self.assertRaises(ValueError):utc_days('2026-10-08T00:00:01Z','2026-10-09T00:00:00Z')
    def test_no_lifecycle_auto_enable(self):
        c=default_config();c['lifecycle_enabled']=True
        with self.assertRaises(ValueError):check_config(c)
    def test_mapping_target_chain_restricted(self):
        m={'link_type':'chain','target_id':'eip155:56','applicable_chain_keys':'eip155:56'}
        self.assertFalse(mapping_applies(m,{'chain_key':'eip155:8453','token_id':'x','platform_id':'clanker'}))
    def test_historical_IDL_mandatory_PDA_checked(self):
        p=next((ROOT/'configs').glob('pump_*.json'));d=load(p);self.assertTrue(check_pump_idl(d));d['instructions'][next(i for i,x in enumerate(d['instructions']) if x['name']=='create')]['accounts'][1]['name']='wrong'
        with self.assertRaises(Halt):check_pump_idl(d)

class PublicClient(unittest.TestCase):
    def cfg(self):
        c=default_config();c['rates']={'min_seconds_between_requests':0,'min_seconds_per_rpc_element':0};return c
    def test_cache_replay_offline_hash_verified(self):
        with tempfile.TemporaryDirectory() as d:
            fn=lambda *a:(200,{},b'{"result":[]}');c=Client(d,self.cfg(),True,transport=fn,sleeper=lambda _:None)
            c.rpc('https://api.mainnet.solana.com','getBlocks',[1,2]);self.assertEqual(c.calls,1)
            off=Client(d,self.cfg(),False);value,m=off.rpc('https://api.mainnet.solana.com','getBlocks',[1,2]);self.assertEqual(value,[]);self.assertEqual(off.calls,0)
            resolve(d,m['raw_ref']).write_bytes(b'corrupt')
            with self.assertRaises(Halt):off.rpc('https://api.mainnet.solana.com','getBlocks',[1,2])
    def test_readonly_method_allowlist(self):
        with tempfile.TemporaryDirectory() as d:
            c=Client(d,self.cfg(),True)
            with self.assertRaises(Halt):c.rpc('https://api.mainnet.solana.com','sendTransaction',['x'])
            self.assertEqual(c.calls,0)
    def test_http200_rpc_error_is_failure(self):
        with tempfile.TemporaryDirectory() as d:
            c=Client(d,self.cfg(),True,transport=lambda *a:(200,{},b'{"error":{"code":-1,"message":"not found"}}'),sleeper=lambda _:None)
            with self.assertRaises(Halt):c.rpc('https://api.mainnet.solana.com','getBlock',[1])
            rows=[json.loads(x) for x in (Path(d)/'provenance/requests.jsonl').read_text().splitlines()];self.assertFalse(rows[0]['ok'])
    def test_long_retry_after_stops_not_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            c=Client(d,self.cfg(),True,transport=lambda *a:(429,{'Retry-After':'120'},b'busy'),sleeper=lambda _:None)
            with self.assertRaises(Halt):c.rpc('https://api.mainnet.solana.com','getBlock',[1])
            self.assertEqual(c.calls,1)
    def test_rpc_elements_budget_counts_batch_members(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=self.cfg();cfg['budgets']['rpc_elements_per_invocation']=1;c=Client(d,cfg,True,transport=lambda *a:(200,{},b'[]'))
            with self.assertRaises(Halt):c.json('https://api.mainnet.solana.com',[{'method':'getBlock'},{'method':'getBlock'}])
            self.assertEqual(c.calls,0)
    def test_batch_missing_identity_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c=Client(d,self.cfg(),True,transport=lambda *a:(200,{},b'[{"id":0,"result":1},{"id":0,"result":2}]'),sleeper=lambda _:None)
            with self.assertRaises(Halt):rpc_batch(c,'https://api.mainnet.solana.com',[('a','getBlock',[1]),('b','getBlock',[2])])
    def test_nonpublic_host_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(Halt):Client(d,self.cfg(),True).json('http://example.com')

class PaginationAndCoverage(unittest.TestCase):
    def test_empty_stream_is_unknown_not_zero(self):
        with self.assertRaises(Halt):validate_stream([],10,20)
    def test_partial_stream_only_advances_to_last_returned(self):
        self.assertEqual(validate_stream([{'header':{'number':10}},{'header':{'number':12}}],10,20),13)
    def test_out_of_range_stream_rejected(self):
        with self.assertRaises(Halt):validate_stream([{'header':{'number':21}}],10,20)
    def test_native_log_completed_segments_resume_without_new_network(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=default_config();cfg['rates']={'min_seconds_between_requests':0,'min_seconds_per_rpc_element':0};c=Client(d,cfg,True,transport=lambda *a:(200,{},b'{"result":[]}'),sleeper=lambda _:None)
            rows,state=evm_logs(c,'2026-10-08','eip155:8453',[1,20001]);self.assertEqual(c.calls,2);self.assertEqual(state['next'],20001)
            again=Client(d,cfg,False);rows,state=evm_logs(again,'2026-10-08','eip155:8453',[1,20001]);self.assertEqual(again.calls,0)
    def test_history_official_index_set_disagreement_stops(self):
        with tempfile.TemporaryDirectory() as d:
            class Fake:
                root=Path(d);cfg=default_config()
                def rpc(self,url,method,*a):return ({'data':[]} if method=='getTransactionsForAddress' else None), {'raw_ref':'r','sha256':'x','request_id':'q','retrieved_at_utc':'t'}
            with self.assertRaises(Halt):solana_history(Fake(),'2026-10-08',[1,2],{'candidates':[{'signature':'missing','slot':1,'blockTime':1791417601,'err':None}]})

class NativeSupplementRegression(unittest.TestCase):
    def history(self,d,wrong_order=False):
        cfg=default_config();cfg['rates']={'min_seconds_between_requests':0,'min_seconds_per_rpc_element':0}
        candidate={'signature':'missing','slot':1,'blockTime':1791417601,'err':None}
        tx={'slot':1,'blockTime':1791417601,'meta':{'err':None},'transaction':{'signatures':['missing'],'message':{'accountKeys':[AUTHORITY]}},'version':1}
        if wrong_order:tx['transactionIndex']=0
        def transport(url,payload,sql):
            method=payload['method']
            result={'data':[]} if method=='getTransactionsForAddress' else (tx if method=='getTransaction' else {'blockTime':1791417601,'blockhash':'native_hash','signatures':['prior','missing']})
            return 200,{},canonical({'jsonrpc':'2.0','id':1,'result':result}).encode()
        c=Client(d,cfg,True,transport=transport,sleeper=lambda _:None)
        return solana_history(c,'2026-10-08',[1,2],{'candidates':[candidate]}),c
    def test_missing_versioned_transaction_recovered_with_native_order_proof(self):
        from collectors import history_transactions
        with tempfile.TemporaryDirectory() as d:
            history,c=self.history(d);self.assertTrue(history['cross_source_set_verified']);self.assertEqual(len(history['native_supplements']),1)
            transactions=list(history_transactions(d,history));self.assertEqual(len(transactions),1);self.assertEqual(transactions[0][0]['transactionIndex'],1)
            self.assertIn('getBlock_signature_order',transactions[0][1]['native_source'])
    def test_native_order_disagreement_stops_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(Halt,'transaction index conflict'):self.history(d,True)
    def test_supplement_source_tampering_is_rejected(self):
        from collectors import history_transactions
        with tempfile.TemporaryDirectory() as d:
            history,c=self.history(d);p=resolve(d,history['native_supplements'][0]['block_raw_ref']);p.write_bytes(b'changed')
            with self.assertRaisesRegex(Halt,'hash changed'):list(history_transactions(d,history))
    def test_BSC_empty_logs_still_have_contiguous_bounded_block_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            queries=[];cfg=default_config();cfg['rates']={'min_seconds_between_requests':0,'min_seconds_per_rpc_element':0}
            def transport(url,q,sql):
                queries.append(q);return 200,{},('\n'.join(canonical({'header':{'number':n},'logs':[]}) for n in range(q['fromBlock'],q['toBlock']+1))+'\n').encode()
            c=Client(d,cfg,True,transport=transport,sleeper=lambda _:None);rows,state=evm_logs(c,'2026-10-08','eip155:56',[100,2101])
            self.assertEqual(rows,[]);self.assertEqual(state['next'],2101);self.assertEqual(len(queries),3);self.assertTrue(all(q['includeAllBlocks'] and q['toBlock']-q['fromBlock']<1000 for q in queries))
    def test_BSC_all_block_stream_gap_cannot_close_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=default_config();cfg['rates']={'min_seconds_between_requests':0,'min_seconds_per_rpc_element':0}
            body='\n'.join(canonical({'header':{'number':n}}) for n in [100,102]).encode()
            c=Client(d,cfg,True,transport=lambda *a:(200,{},body),sleeper=lambda _:None)
            with self.assertRaisesRegex(Halt,'position gaps'):evm_logs(c,'2026-10-08','eip155:56',[100,103])
    def test_BSC_archive_log_inherits_parent_block_identity(self):
        from collectors import bsc_stream_logs
        h='0x'+'12'*32
        rows=bsc_stream_logs([{'header':{'number':101,'hash':h},'logs':[{'logIndex':3,'transactionHash':'0xabc'}]}])
        self.assertEqual(rows,[{'logIndex':3,'transactionHash':'0xabc','blockNumber':101,'blockHash':h}])
    def test_BSC_archive_log_parent_identity_conflicts_stop(self):
        from collectors import bsc_stream_logs
        with self.assertRaisesRegex(Halt,'number conflict'):
            bsc_stream_logs([{'header':{'number':101,'hash':'0x'+'12'*32},'logs':[{'blockNumber':102}]}])
        with self.assertRaisesRegex(Halt,'hash conflict'):
            bsc_stream_logs([{'header':{'number':101,'hash':'0x'+'12'*32},'logs':[{'blockHash':'0x'+'34'*32}]}])

class EVMCollectorIntegration(unittest.TestCase):
    def setup_transport(self,corrupt=False):
        from native_decode import abi_encode
        v=next(v for v in load(ROOT/'configs/platform_events.json') if v['chain_key']=='eip155:56');ev=v['event_abi']
        values=['0x'+'ab'*20,'0x'+'cd'*20,1,'Synthetic test','TEST',1000,1791417601,10]
        block_hash='0x'+'22'*32
        log={'address':v['address'],'topics':[v['topic0']],'data':'0x'+abi_encode([x['type'] for x in ev['inputs']],values).hex(),'logIndex':0,'transactionIndex':1,'transactionHash':'0x'+'11'*32}
        native={**log,'logIndex':'0x0','transactionIndex':'0x1','blockNumber':'0x64','blockHash':block_hash,'removed':False}
        receipt={'transactionHash':log['transactionHash'],'blockNumber':'0x64','blockHash':('0x'+'33'*32) if corrupt else block_hash,'transactionIndex':'0x1','status':'0x1','from':'0x'+'ab'*20,'to':v['address'],'logs':[native]}
        header={'number':'0x64','hash':block_hash,'timestamp':hex(1791417601)}
        def transport(url,payload,sql):
            if 'portal.sqd.dev' in url:return 200,{},(canonical({'header':{'number':100,'hash':block_hash,'timestamp':1791417601},'logs':[log]})+'\n').encode()
            response=[{'id':q['id'],'result':receipt if q['method']=='eth_getTransactionReceipt' else header} for q in payload]
            return 200,{},canonical(response).encode()
        return transport
    def test_real_ABI_shape_full_receipt_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=default_config();cfg['rates']={'min_seconds_between_requests':0,'min_seconds_per_rpc_element':0};c=Client(d,cfg,True,transport=self.setup_transport(),sleeper=lambda _:None)
            result=collect_evm(c,'2026-10-08','eip155:56',[100,101]);self.assertEqual(result['native_logs_checked'],1)
            p=Path(d)/'days/2026-10-08/eip155_56_normalized.ndjson'
            events=list(decode_envelopes((json.loads(x) for x in p.read_text().splitlines()),'eip155:56',1791417600,1791504000,'synthetic_test',set(),d,d))
            self.assertEqual(events[0]['initial_name'],'Synthetic test');self.assertEqual(events[0]['creator_address'],'0x'+'ab'*20)
    def test_receipt_header_mismatch_stops(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=default_config();cfg['rates']={'min_seconds_between_requests':0,'min_seconds_per_rpc_element':0};c=Client(d,cfg,True,transport=self.setup_transport(True),sleeper=lambda _:None)
            with self.assertRaises(Halt):collect_evm(c,'2026-10-08','eip155:56',[100,101])
    def test_old_output_paths_protected(self):
        for path in [PARENT,P2,ROOT/'code',ROOT/'reports',ROOT/'test_outputs']:
            with self.assertRaises(Halt):guard_output(path)
    def test_valid_test_and_formal_roots(self):
        for path in [ROOT/'test_outputs/example',ROOT/'runs/formal_example']:self.assertEqual(guard_output(path),path.resolve())

class Orchestration(unittest.TestCase):
    def test_deferred_review_saves_amendment_but_invalidates_old_validation(self):
        from unittest.mock import patch
        from pipeline import apply_reviews
        with tempfile.TemporaryDirectory(dir=ROOT/'test_outputs') as d:
            r=Path(d);save(r/'configs/protocol.json',default_config());write_csv(r/'processed/pm_markets.csv',[{'market_id':'1','rules_sha256':'h'}]);write_csv(r/'processed/pm_outcomes.csv',[],['outcome_label'])
            write_csv(r/'configs/mapping_reviews.csv',[{'market_id':'old'}]);save(r/'reports/validation_results.json',{'status':'passed','formal_P3_completed':True})
            p=r/'new_reviews.csv';write_csv(p,[{'market_id':'1','outcome_label':'Yes','rules_sha256':'h','reviewed_by':'isolated_test','review_decision':'catalogue_only','decision_reason':'out_of_scope'}])
            with patch('pipeline.build_all',side_effect=AssertionError('unexpected rebuild')):
                result=apply_reviews(r,p,defer_rebuild=True)
            self.assertEqual(result['status'],'reviews_validated_pending_rebuild');self.assertFalse(load(r/'reports/validation_results.json')['formal_P3_completed']);self.assertEqual(load(r/'reports/offline_reproduction.json')['status'],'pending_rebuild_after_review_amendment');self.assertTrue(list((r/'configs/review_history').glob('*')))
    def test_resume_disk_gate_counts_saved_raw_without_increasing_cap(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from pipeline import preflight
        cfg=default_config()
        with tempfile.TemporaryDirectory() as d:
            raw=Path(d)/'raw';raw.mkdir()
            with (raw/'saved.body.gz').open('wb') as f:f.truncate(1_000_000_000)
            with patch('pipeline.verify_inputs',return_value={'status':'passed'}),patch('pipeline.shutil.disk_usage',return_value=SimpleNamespace(free=32_500_000_000)):
                resumed=preflight(cfg,d);fresh=preflight(cfg)
            self.assertEqual(resumed['status'],'passed');self.assertEqual(resumed['recommended_free_disk_bytes'],32_000_000_000)
            self.assertEqual(fresh['status'],'insufficient_disk_for_formal_budget');self.assertEqual(fresh['recommended_free_disk_bytes'],34_000_000_000)
            self.assertEqual(cfg['budgets']['max_raw_bytes'],16_000_000_000)
    def test_registry_tables_share_identical_storage_across_atomic_rebuilds(self):
        from unittest.mock import patch
        from views import build_registry
        with tempfile.TemporaryDirectory() as d:
            cfg=default_config();cfg['cohort_id']='isolated_test';cfg['rates']={'min_seconds_between_requests':0,'min_seconds_per_rpc_element':0}
            c=Client(d,cfg,True,transport=EVMCollectorIntegration().setup_transport(),sleeper=lambda _:None)
            collect_evm(c,'2026-10-08','eip155:56',[100,101])
            with patch('views.read_csv',return_value=[]):
                build_registry(Path(d),cfg);first=sha(Path(d)/'processed/registry.csv');build_registry(Path(d),cfg)
            a=Path(d)/'processed/creation_events.csv';b=Path(d)/'processed/registry.csv'
            self.assertEqual(sha(a),first);self.assertEqual(sha(a),sha(b));self.assertEqual(a.stat().st_ino,b.stat().st_ino)
    def test_authorized_orchestrator_orders_steps_without_actual_network(self):
        from unittest.mock import patch
        calls=[];cfg=default_config();cfg['candidate_end_utc']='2026-10-09T00:00:00Z'
        with tempfile.TemporaryDirectory(dir=ROOT/'test_outputs') as d:
            complete=[{'chain':c,'day':'2026-10-08','status':'complete_test_scope'} for c in CHAINS]
            with patch('pipeline.preflight',return_value={'status':'passed'}),patch('pipeline.import_p2_day',side_effect=lambda *a:calls.append('import')),patch('pipeline.scope_rows',return_value=complete),patch('pipeline.collect_markets',side_effect=lambda *a:calls.append('markets')),patch('pipeline.build_all',side_effect=lambda *a:calls.append('build')),patch('pipeline.native_qa',side_effect=lambda *a:calls.append('qa')),patch('pipeline.reproduce',side_effect=lambda *a:calls.append('reproduce')),patch('pipeline.validate',return_value={'status':'passed_test_only'}),patch('pipeline.artifacts'):
                run(Path(d),cfg,authorized=True)
            self.assertEqual(calls,['import','markets','build','qa','reproduce'])
            self.assertTrue(load(Path(d)/'configs/protocol.json')['formal_window_frozen'])
            self.assertEqual(load(Path(d)/'reports/run_receipt.json')['network_requests_this_invocation'],0)
            self.assertFalse((Path(d)/'.run.lock').exists())
    def test_daily_preflight_failure_does_not_freeze_scope_or_mark_complete(self):
        from unittest.mock import patch
        cfg=default_config();cfg['candidate_start_utc']='2026-10-09T00:00:00Z';cfg['candidate_end_utc']='2026-10-10T00:00:00Z'
        with tempfile.TemporaryDirectory(dir=ROOT/'test_outputs') as d:
            with patch('pipeline.preflight',return_value={'status':'passed'}),patch('pipeline.prepare_day',side_effect=Halt('unavailable historical source')):
                with self.assertRaises(Halt):run(Path(d),cfg,authorized=True)
            self.assertFalse(load(Path(d)/'configs/protocol.json')['formal_window_frozen'])
            receipt=load(Path(d)/'reports/run_receipt.json');self.assertEqual(receipt['status'],'stopped_with_saved_checkpoints');self.assertIn('unavailable historical source',receipt['stop_reason'])
    def test_incomplete_collection_defers_large_derived_rebuild(self):
        from unittest.mock import patch
        cfg=default_config();cfg['candidate_start_utc']='2026-10-08T00:00:00Z';cfg['candidate_end_utc']='2026-10-10T00:00:00Z'
        with tempfile.TemporaryDirectory(dir=ROOT/'test_outputs') as d:
            root=Path(d)
            for day in ['2026-10-08']:
                for chain in CHAINS:save(root/'days'/day/(chain.replace(':','_')+'_receipt.json'),{'status':'complete_test_scope'})
            def fail_source(*args):raise Halt('temporary test source failure')
            fake_bounds={'bounds':{'solana:mainnet':[1,2],'eip155:8453':[1,2],'eip155:56':[1,2]}}
            with patch('pipeline.preflight',return_value={'status':'passed'}),patch('pipeline.prepare_day',return_value=fake_bounds),patch('pipeline.collect_evm',side_effect=fail_source),patch('pipeline.collect_solana',side_effect=fail_source),patch('pipeline.collect_markets',side_effect=AssertionError('deferred')),patch('pipeline.build_all',side_effect=AssertionError('deferred')),patch('pipeline.native_qa',side_effect=AssertionError('deferred')),patch('pipeline.reproduce',side_effect=AssertionError('deferred')),patch('pipeline.validate',side_effect=AssertionError('deferred')),patch('pipeline.artifacts',side_effect=AssertionError('deferred')):
                result=run(root,cfg,authorized=True)
            self.assertEqual(result['status'],'collection_pending_coverage');self.assertTrue(result['derived_build_deferred']);self.assertEqual(len(result['pending_chain_days']),3)
            receipt=load(root/'reports/run_receipt.json');self.assertEqual(receipt['status'],'collection_pending_coverage');self.assertFalse((root/'.run.lock').exists())

if __name__=='__main__':unittest.main()
