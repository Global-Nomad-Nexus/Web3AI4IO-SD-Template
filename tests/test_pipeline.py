from pathlib import Path
import copy, shutil, subprocess, sys, tempfile, unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code/shared'))
import pipeline as p

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)

    def run_track(self,track):
        for stage in ('query_data','process_data','analyze_data','technical_validation'):
            w=p.run_stage(track,stage,self.base)
        return w

    def inputs(self):
        ev=p.read_csv(ROOT/'data/on_chain/processed_data/demo/events.csv',p.ON)
        docs=p.read_csv(ROOT/'data/off_chain/processed_data/demo/records.csv',p.OFF)
        cw=p.read_csv(ROOT/'data/integration/linkage/demo/crosswalk.csv',p.CW)
        return ev,docs,cw

    def test_all_tracks_match_frozen_reference(self):
        for track in p.TRACKS:
            with self.subTest(track=track):
                w=self.run_track(track)
                self.assertEqual(p.read_json(w/'reports/validation.json')['reference_comparison'],'PASS')

    def test_known_source_attrition_and_missingness(self):
        on=self.run_track('on_chain');off=self.run_track('off_chain')
        a=p.read_json(on/'reports/processing.json');b=p.read_json(off/'reports/processing.json')
        self.assertEqual((a['raw_rows'],a['exact_duplicates_removed'],a['noncanonical_removed'],a['processed_rows']),(8,1,1,6))
        self.assertEqual((b['raw_rows'],b['exact_duplicates_removed'],b['processed_rows'],b['missing_measure']),(7,1,6,1))

    def test_integration_runs_without_other_workspaces(self):
        w=self.run_track('integration')
        self.assertFalse((self.base/'on_chain').exists())
        self.assertFalse((self.base/'off_chain').exists())
        rows=p.read_csv(w/'processed_data/integrated.csv');by={r['event_id']:r for r in rows}
        self.assertEqual(len(rows),6)
        self.assertEqual([by[x]['record_id'] for x in ['e1','e2','e6']],['r1','r2','r4'])
        self.assertEqual([by[x]['link_status'] for x in ['e3','e4','e5']],['no_prior_record','unreviewed_link','no_crosswalk'])
        self.assertEqual(by['e6']['measure'],'')
        self.assertEqual(len(p.read_csv(w/'processed_data/unmatched_events.csv')),3)
        self.assertEqual(len(p.read_csv(w/'processed_data/unused_off_chain.csv')),3)

    def test_corrupted_acquired_input_stops(self):
        w=p.run_stage('on_chain','query_data',self.base)
        f=w/'queried_data/events.csv';f.write_bytes(f.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Checksum mismatch'):p.process('on_chain',w)

    def test_missing_acquired_asset_stops(self):
        w=p.run_stage('integration','query_data',self.base)
        (w/'queried_data/off_chain.csv').unlink()
        with self.assertRaisesRegex(ValueError,'Missing input'):p.process('integration',w)

    def test_conflicting_duplicate_stops(self):
        ev,_,_=self.inputs();bad=copy.deepcopy(ev[0]);bad['amount_units']='999'
        with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):
            p.deduplicate([ev[0],bad],['chain_id','transaction_id','log_index'])

    def test_ambiguous_approved_links_stop(self):
        ev,docs,cw=self.inputs();extra=copy.deepcopy(cw[0]);extra.update(crosswalk_id='extra',entity_id='org-beta')
        with self.assertRaisesRegex(ValueError,'Ambiguous approved'):p.join_records(ev,docs,cw+[extra])

    def test_future_publication_is_excluded(self):
        ev,docs,cw=self.inputs()
        for d in docs:
            if d['entity_id']=='org-alpha':d['published_at']='2025-01-25T00:00:00Z'
        rows=p.join_records(ev,docs,cw)
        self.assertTrue(all(r['link_status']=='no_prior_record' for r in rows if r['event_id'] in ('e1','e2')))

    def test_future_reference_period_is_excluded(self):
        ev,docs,cw=self.inputs()
        for d in docs:
            if d['entity_id']=='org-alpha':d['reference_end']='2025-01-31T23:59:59Z'
        rows=p.join_records(ev,docs,cw)
        self.assertTrue(all(r['link_status']=='no_prior_record' for r in rows if r['event_id'] in ('e1','e2')))

    def test_link_validity_end_is_exclusive(self):
        ev,docs,cw=self.inputs();cw[0]['valid_to']='2025-01-10T12:00:00Z'
        rows=p.join_records(ev,docs,cw)
        self.assertEqual(next(r for r in rows if r['event_id']=='e1')['link_status'],'no_crosswalk')

    def test_source_record_ties_stop(self):
        ev,docs,cw=self.inputs();other=copy.deepcopy(docs[0]);other['record_id']='new-id'
        with self.assertRaisesRegex(ValueError,'Tied source records'):p.join_records(ev,docs+[other],cw)

    def test_stricter_age_policy_changes_coverage(self):
        ev,docs,cw=self.inputs();rows=p.join_records(ev,docs,cw,max_age_days=7)
        self.assertEqual(sum(r['link_status']=='matched' for r in rows),2)

    def test_equivalent_timestamp_formats_still_count_as_ties(self):
        ev,docs,cw=self.inputs();other=copy.deepcopy(docs[0])
        other.update(record_id='format-variant',published_at='2025-01-01T00:00:00.000Z')
        with self.assertRaisesRegex(ValueError,'Tied source records'):p.join_records(ev,docs+[other],cw)

    def test_causal_promotion_fails_reference_contract(self):
        w=self.run_track('integration');path=w/'reports/analysis.json'
        obj=p.read_json(path);self.assertEqual(obj['inference'],'descriptive_only')
        obj['inference']='causal_effect_established';p.write_json(path,obj)
        with self.assertRaisesRegex(ValueError,'governed synthetic reference'):p.validate('integration',w)

    def test_changed_processed_result_stops(self):
        w=self.run_track('off_chain');path=w/'processed_data/records.csv'
        path.write_text(path.read_text().replace(',12,demo-index',',99,demo-index'))
        with self.assertRaisesRegex(ValueError,'governed synthetic reference'):p.validate('off_chain',w)

    def test_output_cannot_overwrite_source_tree(self):
        with self.assertRaisesRegex(ValueError,'overwrite repository sources'):p.workspace(ROOT/'data','on_chain')

    def test_unknown_unit_stops(self):
        ev,docs,cw=self.inputs();docs[0]['unit']='unspecified-currency'
        with self.assertRaisesRegex(ValueError,'Unexpected measurement unit'):p.join_records(ev,docs,cw)

    def test_retrieval_before_publication_stops(self):
        _,docs,_=self.inputs();docs[0]['retrieved_at']='2024-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'Retrieval before publication'):p.validate_off(docs)

    def test_hf_package_allowlist_and_stale_destination(self):
        dest=self.base/'package';cmd=[sys.executable,str(ROOT/'scripts/prepare_hf.py'),'--demo','--output',str(dest)]
        subprocess.run(cmd,check=True,capture_output=True,text=True)
        manifest=p.read_json(dest/'package_manifest.json')
        self.assertEqual(set(manifest['files']),{'on_chain.csv','off_chain.csv','integration.csv','crosswalk.csv','unmatched_events.csv','unused_off_chain.csv','data_dictionary.csv','field_provenance.csv','LICENSE','README.md'})
        for filename,expected in manifest['files'].items():self.assertEqual(p.sha(dest/filename),expected)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)

    def test_hf_packaging_rejects_corrupted_archive(self):
        isolated=self.base/'repo'
        shutil.copytree(ROOT,isolated,ignore=shutil.ignore_patterns('.git','outputs','dist','__pycache__'))
        path=isolated/'data/on_chain/processed_data/demo/events.csv'
        path.write_bytes(path.read_bytes()+b'\n')
        dest=self.base/'corrupt-package'
        result=subprocess.run([sys.executable,str(isolated/'scripts/prepare_hf.py'),'--demo','--output',str(dest)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Checksum mismatch',result.stderr)
        self.assertFalse(dest.exists())

    def test_validation_checks_survive_python_optimization(self):
        for module in ('check_repository','check_notebooks'):
            command = f"import sys; sys.path.insert(0, {str(ROOT/'scripts')!r}); from {module} import require; require(False, 'intentional validation failure')"
            result = subprocess.run([sys.executable,'-O','-c',command],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('intentional validation failure',result.stderr)

if __name__=='__main__':unittest.main()
