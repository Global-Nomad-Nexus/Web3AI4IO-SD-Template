import copy, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code'))
from lifecycle_adapter import Adapter, identity, timestamp, VERSION
CONFIG=json.loads((ROOT/'configs/adapter_config.json').read_text())
DATA=json.loads((ROOT/'tests/fixtures/lifecycle_cases.json').read_text())

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.reg=copy.deepcopy(DATA['registry']);self.a=Adapter(self.reg,CONFIG,DATA['crosswalk'],'synthetic_test')
        self.event=copy.deepcopy(DATA['events'][0]);self.cover=copy.deepcopy(DATA['coverage'][0]);self.cut=DATA['cutoff']
    def events(self,*events):return self.a.events(events or [self.event],cutoff=self.cut)
    def outcome(self,events=(),coverage=None,target='first_trade'):
        cov=self.a.coverage(coverage if coverage is not None else [self.cover])
        return self.a.followup(events,cov,self.cut,{target:'trades'})[0]
    def test_cross_chain_same_address(self):self.assertNotEqual(self.reg[0]['token_id'],self.reg[1]['token_id'])
    def test_solana_case_preserved(self):self.assertNotEqual(self.reg[2]['token_id'],self.reg[3]['token_id'])
    def test_evm_case_normalized(self):self.assertEqual(identity('eip155:8453','0x'+'AB'*20),self.reg[0]['token_id'])
    def test_explicit_field_mapping(self):
        e=self.events()[0];self.assertEqual(e['token_id'],self.reg[0]['token_id']);self.assertEqual(e['event_time_utc'],'2026-10-08T02:00:00Z')
    def test_crosswalk_object_id(self):
        e={k:v for k,v in self.event.items() if k!='token_address'};e['object_id']='old-1'
        self.assertEqual(self.events(e)[0]['token_id'],self.reg[0]['token_id'])
    def test_ambiguous_crosswalk_rejected(self):
        with self.assertRaises(ValueError):Adapter(self.reg,CONFIG,DATA['crosswalk']+[{**DATA['crosswalk'][0],'token_id':self.reg[1]['token_id']}])
    def test_chain_free_address_rejected(self):
        e={k:v for k,v in self.event.items() if k!='chain_id'};self.assertEqual(self.events(e),[]);self.assertIn('chain',self.a.errors[0]['reason'])
    def test_conflicting_identity_rejected(self):
        e={**self.event,'token_id':self.reg[1]['token_id']};self.assertEqual(self.events(e),[])
    def test_unknown_registry_token_quarantined(self):
        e={**self.event,'token_address':'0x'+'cc'*20};self.assertEqual(self.events(e),[])
    def test_alias_conflict_rejected(self):
        self.assertEqual(self.events({**self.event,'event_time_utc':'2026-10-08T03:00:00Z'}),[])
    def test_exact_repeated_event_audited(self):
        self.assertEqual(len(self.events(self.event,self.event)),1);self.assertEqual(self.a.notes[0]['rows'],2)
    def test_conflicting_repeats_all_quarantined(self):
        e={**self.event,'timestamp':'2026-10-08T03:00:00Z'}
        self.assertEqual(self.events(self.event,e),[]);self.assertEqual(len(self.a.errors),2)
    def test_conflict_order_independent(self):
        e={**self.event,'timestamp':'2026-10-08T03:00:00Z'};self.assertEqual(self.events(e,self.event),[])
    def test_multiple_events_keep_registry(self):
        e={**self.event,'event_index':'log:2','timestamp':'2026-10-08T03:00:00Z'}
        joined=self.a.join(self.events(self.event,e),[]);self.assertEqual(len(joined),4);self.assertEqual(joined[0]['lifecycle_event_count'],2)
    def test_missing_record_is_unknown(self):
        joined=self.a.join([],[]);self.assertEqual(len(joined),4);self.assertEqual(joined[0]['ecosystem_match_status'],'ecosystem_unmatched')
        outcome=self.outcome(coverage=[]);self.assertEqual(outcome['status'],'unknown');self.assertIsNone(outcome['is_right_censored'])
    def test_first_seen_does_not_overwrite_creation(self):
        before=copy.deepcopy(self.reg);self.events({**self.event,'first_seen_in_window':'2026-10-08T05:00:00Z'})
        self.assertEqual(self.a.registry[self.reg[0]['token_id']]['created_at_utc'],before[0]['created_at_utc']);self.assertEqual(self.reg,before)
    def test_creation_conflict_rejected(self):self.assertEqual(self.events({**self.event,'created_at_utc':'2026-10-08T01:00:00Z'}),[])
    def test_creator_role_conflict_rejected(self):
        self.assertEqual(self.events({**self.event,'creator_address':self.reg[0]['creator_address'],'creator_role_definition':'tx_sender'}),[])
    def test_creator_role_only_conflict_rejected(self):
        self.assertEqual(self.events({**self.event,'creator_role_definition':'tx_sender'}),[])
    def test_native_position_leading_zero_deduplication(self):
        self.assertEqual(len(self.events(self.event,{**self.event,'event_index':'log:01'})),1)
    def test_equivalent_chain_aliases(self):
        self.assertEqual(len(self.events({**self.event,'chain_key':'eip155:8453'})),1)
    def test_numeric_epoch_only_with_declaration(self):
        config=copy.deepcopy(CONFIG);config['time_units']={'event_time_utc':'epoch_seconds','observed_at_utc':'epoch_seconds'}
        a=Adapter(self.reg,config,DATA['crosswalk'],'synthetic_test')
        event={**self.event,'timestamp':timestamp(self.event['timestamp']).timestamp(),'retrieved_at':timestamp(self.event['retrieved_at']).timestamp()}
        self.assertEqual(a.events([event])[0]['event_time_utc'],self.event['timestamp'])
    def test_event_before_creation(self):self.assertEqual(self.events({**self.event,'timestamp':'2026-10-07T23:00:00Z'}),[])
    def test_observation_before_event(self):self.assertEqual(self.events({**self.event,'retrieved_at':'2026-10-08T01:00:00Z'}),[])
    def test_naive_time_rejected(self):self.assertEqual(self.events({**self.event,'timestamp':'2026-10-08T02:00:00'}),[])
    def test_epoch_requires_explicit_unit(self):
        with self.assertRaises(ValueError):timestamp('1791417600')
        with self.assertRaises(ValueError):timestamp('1791417600000','epoch_seconds')
        self.assertEqual(timestamp('1791417600','epoch_seconds').tzinfo.utcoffset(None).total_seconds(),0)
    def test_native_position_required(self):self.assertEqual(self.events({**self.event,'event_index':''}),[])
    def test_unknown_version_rejected(self):self.assertEqual(self.events({**self.event,'interface_version':'v99'}),[])
    def test_missing_venue_needs_reason(self):self.assertEqual(self.events({**self.event,'venue_id':''}),[])
    def test_complete_to_cutoff_right_censored(self):
        o=self.outcome();self.assertEqual(o['status'],'administrative_right_censored');self.assertTrue(o['is_right_censored']);self.assertTrue(o['coverage_evidence_refs'])
    def test_adjacent_coverage_closes(self):
        left={**self.cover,'end':'2026-10-08T04:00:00Z'};right={**self.cover,'start':'2026-10-08T04:00:00Z'}
        self.assertEqual(self.outcome(coverage=[right,left])['status'],'administrative_right_censored')
    def test_coverage_gap_loss_to_followup(self):
        left={**self.cover,'end':'2026-10-08T04:00:00Z'};right={**self.cover,'start':'2026-10-08T05:00:00Z'}
        o=self.outcome(coverage=[right,left]);self.assertEqual(o['status'],'loss_to_followup');self.assertEqual(o['followup_end_utc'],'2026-10-08T04:00:00Z')
    def test_late_start_is_unknown(self):self.assertEqual(self.outcome(coverage=[{**self.cover,'start':'2026-10-08T01:00:00Z'}])['status'],'unknown')
    def test_partial_cannot_be_complete(self):
        self.assertEqual(self.outcome(coverage=[{**self.cover,'coverage_status':'partial','missing_reason':'gap'}])['status'],'unknown')
    def test_noncomplete_needs_missing_reason(self):self.assertEqual(self.a.coverage([{**self.cover,'coverage_status':'source_missing'}]),[])
    def test_reversed_coverage_rejected(self):self.assertEqual(self.a.coverage([{**self.cover,'start':self.cut,'end':'2026-10-08T00:00:00Z'}]),[])
    def test_coverage_overlap_conflict(self):
        cov=self.a.coverage([self.cover,{**self.cover,'coverage_status':'unknown','missing_reason':'conflicting evidence'}]);self.assertEqual(cov,[]);self.assertEqual(len(self.a.errors),2)
    def test_target_specific_coverage(self):self.assertEqual(self.outcome(coverage=[{**self.cover,'layer_or_venue':'migration'}])['status'],'unknown')
    def test_postcutoff_event_retained_excluded(self):
        events=self.events({**self.event,'timestamp':'2026-10-09T01:00:00Z','retrieved_at':'2026-10-10T00:00:00Z'})
        self.assertFalse(events[0]['analysis_eligible']);self.assertEqual(self.outcome(events)['status'],'administrative_right_censored')
    def test_event_exact_cutoff_excluded(self):
        self.assertEqual(self.outcome(self.events({**self.event,'timestamp':self.cut}))['status'],'administrative_right_censored')
    def test_observed_event_not_censored(self):
        o=self.outcome(self.events());self.assertEqual(o['status'],'observed_event');self.assertFalse(o['is_right_censored']);self.assertTrue(o['first_occurrence_verified'])
    def test_event_after_gap_first_occurrence_unverified(self):
        o=self.outcome(self.events(),[{**self.cover,'start':'2026-10-08T01:00:00Z'}]);self.assertEqual(o['status'],'observed_event');self.assertFalse(o['first_occurrence_verified'])
    def test_inactivity_reactivation_preserved(self):
        events=self.events({**self.event,'event_type':'inactivity'},{**self.event,'event_type':'reactivation','event_index':'log:2','timestamp':'2026-10-08T04:00:00Z'})
        self.assertEqual([e['event_type'] for e in events],['inactivity','reactivation']);self.assertNotIn('death',[e['event_type'] for e in events])
    def test_real_mode_rejects_fixture(self):
        a=Adapter([{k:v for k,v in r.items() if k!='dataset_kind'} for r in self.reg],CONFIG)
        self.assertEqual(a.events([self.event]),[]);self.assertIn('synthetic',a.errors[0]['reason'])
    def test_fixture_requires_label(self):
        self.assertEqual(self.events({k:v for k,v in self.event.items() if k!='dataset_kind'}),[])
    def test_diagnostic_file_and_line(self):
        self.a.events([{**self.event,'timestamp':'invalid'}],source='broken.csv');self.assertEqual(self.a.errors[0]['source_file'],'broken.csv');self.assertEqual(self.a.errors[0]['row_number'],2)


class ExpectationGateTests(unittest.TestCase):
    def setUp(self):
        from lifecycle_adapter import validate_expectation_proxy
        self.gate=validate_expectation_proxy
        self.price={'price_role':'historical_bucket','is_settlement_point':False,'bucket_start_utc':'2026-10-08T10:00:00Z','bucket_end_utc':'2026-10-08T11:00:00Z','price':'0.4','price_definition_status':'unconfirmed_API_scalar'}
    def test_partial_bucket_future_leak_rejected(self):
        with self.assertRaises(ValueError):self.gate(self.price,'2026-10-08T10:15:00Z')
    def test_exact_bucket_end_rejected(self):
        with self.assertRaises(ValueError):self.gate(self.price,'2026-10-08T11:00:00Z')
    def test_current_price_rejected(self):
        with self.assertRaises(ValueError):self.gate({**self.price,'price_role':'current_quote'},'2026-10-08T12:00:00Z')
    def test_settlement_payout_rejected(self):
        with self.assertRaises(ValueError):self.gate({**self.price,'is_settlement_point':True},'2026-10-08T12:00:00Z')
    def test_historical_scalar_retains_limitation(self):
        self.assertEqual(self.gate(self.price,'2026-10-08T12:00:00Z'),'retrospective_demonstration_only')

if __name__=='__main__':unittest.main()
