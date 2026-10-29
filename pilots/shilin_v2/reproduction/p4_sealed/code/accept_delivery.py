"""Verify sealed files, extract in a NEW directory, deny original-data reads and networking,
rebuild final delivery, and compare tables, dictionary, figure sources, prose counts and hashes.
Requires Python 3.14.2 / macOS arm64 for the bundled eth_abi binary dependencies.
"""
import argparse,csv,gzip,hashlib,json,os,resource,shutil,subprocess,sys,tarfile,time
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
def read(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--release',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--forbidden-original',type=Path,default=Path('/nonexistent_original_project'));p.add_argument('--keep-workspace',action='store_true');a=p.parse_args()
 release=a.release.resolve();out=a.output.resolve()
 if out.exists():raise ValueError('independent output must not already exist')
 out.mkdir(parents=True);start=time.monotonic();checks=[]
 def check(name,count,bad,detail=''):
  checks.append(dict(check_id=name,scope='P4_final_delivery',tested_count=count,failure_count=len(bad) if isinstance(bad,list) else int(bad),failure_refs=bad if isinstance(bad,list) else [],detail=detail,status='passed' if not bad else 'failed'))
 # Compare the exact allowed file set, hash and bytes, including compressed data and fixtures.
 seal=load(release/'file_manifest.json');expected={r['path'] for r in seal}
 actual={str(p.relative_to(release)) for p in release.rglob('*') if p.is_file() and p.name!='file_manifest.json' and '__pycache__' not in p.parts}
 check('sealed_file_set',len(expected),sorted(expected^actual))
 failures=[r['path'] for r in seal if not (release/r['path']).is_file() or (release/r['path']).stat().st_size!=r['bytes'] or sha(release/r['path'])!=r['sha256']]
 check('sealed_file_hashes',len(seal),failures)
 # Publication metadata gets a local structure/reference check, separately from the
 # unavailable official Croissant validator and any legal/publishing certification.
 table_schema=load(release/'configs/table_schema.json')['tables'];data_manifest=read(release/'data_manifest.csv')
 check('actual_table_schema',len(data_manifest),[r['path'] for r in data_manifest if [x['name'] for x in table_schema.get(Path(r['path']).stem,{}).get('columns',[])]!=json.loads(r['columns']) or table_schema[Path(r['path']).stem]['sha256']!=r['sha256']])
 croissant=load(release/'configs/croissant.json');objects={r['@id']:r for r in croissant['distribution']};records={r['@id']:r for r in croissant['recordSet']};metabad=[]
 for r in data_manifest:
  name=Path(r['path']).stem;gzip_object=objects.get(name+'_gzip',{});csv_object=objects.get(name+'_csv',{});record=records.get(name,{})
  if gzip_object.get('sha256')!=sha(release/'data'/(name+'.csv.gz')) or csv_object.get('sha256')!=r['sha256']:metabad.append(name+':hash')
  if [x.get('name') for x in record.get('field',[])]!=json.loads(r['columns']):metabad.append(name+':fields')
  for f in record.get('field',[]):
   if f.get('source',{}).get('fileObject',{}).get('@id')!=name+'_csv' or f.get('source',{}).get('extract',{}).get('column')!=f['name']:metabad.append(name+':source')
 check('croissant_local_structure_and_file_references',len(data_manifest),metabad,'Official mlcroissant validator not run; no certification claim.')
 rights=read(release/'configs/source_rights.csv');required_rights=['source_id','provider','endpoint','purpose','official_docs_url','access_without_application','payment_required','credentials_required','actual_access_tested_at','acquisition_status','terms_url','license_url','terms_checked_at','local_retention_status','derived_publication_status','raw_redistribution_status','attribution','evidence_ref','limitations']
 check('source_rights_register_columns',len(rights),int(not rights or list(rights[0])!=required_rights))
 rai=load(release/'configs/rai_metadata.json');check('rai_limitations_and_use_documented',6,[k for k in ['rai:dataCollection','rai:dataLimitations','rai:dataBiases','rai:useCases','rai:dataSocialImpact','rai:dataReleaseMaintenance'] if not rai.get(k)])

 if any(c['status']=='failed' for c in checks):save(out/'acceptance.json',dict(status='failed',checks=checks));raise SystemExit(1)
 work=out/'workspace';work.mkdir()
 with tarfile.open(release/'inputs.tar.gz','r:gz') as tar:tar.extractall(work,filter='data')
 inputs=load(release/'input_manifest.json');bad=[r['path'] for r in inputs if not (work/r['path']).is_file() or sha(work/r['path'])!=r['sha256']]
 check('extracted_input_hashes',len(inputs),bad)
 root=work/load(release/'release.json')['original_run']
 # Static market extraction inputs are independently delivered and locked as P3 snapshots.
 # No copied Registry/expectation outputs exist before rebuilding.
 check('derived_outputs_not_prepopulated',1,int((root/'processed/registry.csv').exists()))
 logfile=out/'rebuild.log'
 with logfile.open('w') as log:
  proc=subprocess.run([sys.executable,'-I','-B',str(release/'code/rebuild_worker.py'),'--workspace',str(work),'--release',str(release),'--forbidden-original',str(a.forbidden_original)],stdout=log,stderr=subprocess.STDOUT,cwd=work)
 check('isolated_worker_exit',1,int(proc.returncode!=0))
 if proc.returncode:
  save(out/'acceptance.json',dict(status='failed',checks=checks,log=str(logfile)));raise SystemExit(proc.returncode)
 worker=load(work/'worker_receipt.json');save(out/'worker_receipt.json',worker)
 expected_data=read(release/'data_manifest.csv');bad=[];rowbad=[];dictbad=[];compressedbad=[]
 dictionary=read(release/'data_dictionary.csv');columns_by_table={}
 for r in dictionary:columns_by_table.setdefault(r['table'],[]).append(r['column'])
 for r in expected_data:
  path=root/r['path'];actual_sha=sha(path)
  if actual_sha!=r['sha256']:bad.append(r['path'])
  with path.open(newline='',encoding='utf-8') as f:
   reader=csv.DictReader(f);columns=reader.fieldnames;count=sum(1 for _ in reader)
  if count!=int(r['rows']):rowbad.append(r['path'])
  if columns!=json.loads(r['columns']) or columns_by_table.get(path.stem)!=columns:dictbad.append(r['path'])
  h=hashlib.sha256()
  with gzip.open(release/'data'/(path.name+'.gz'),'rb') as f:
   for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
  if h.hexdigest()!=actual_sha:compressedbad.append(path.name)
  print('matched',path.name,count,flush=True)
 check('rebuilt_data_byte_hashes',len(expected_data),bad);check('rebuilt_row_counts',len(expected_data),rowbad);check('dictionary_exact_column_order',len(expected_data),dictbad);check('delivered_gzip_equals_rebuilt_data',len(expected_data),compressedbad)
 for c in worker['validation_checks']:checks.append({**c,'scope':'P4_isolated_real_data_revalidation'})
 figpaths=list((release/'figures/data').glob('*.csv'))+[release/'figures/selection.json',release/'figures/shilin_gallery.svg',release/'figures/real_three_chain_preview.csv']
 figbad=[str(f.relative_to(release/'figures')) for f in figpaths if sha(f)!=sha(work/'figures'/f.relative_to(release/'figures'))]
 check('regenerated_figure_sources_and_svg',len(figpaths),figbad)
 # PNG renderer bytes are compared when the installed librsvg version matches.
 renderer=shutil.which('rsvg-convert')
 if renderer:
  subprocess.run([renderer,'--zoom','2','--dpi-x','300','--dpi-y','300','-o',str(work/'figures/shilin_gallery.png'),str(work/'figures/shilin_gallery.svg')],check=True)
  pngsame=sha(work/'figures/shilin_gallery.png')==sha(release/'figures/shilin_gallery.png')
  check('regenerated_png',1,int(not pngsame),'Environment-specific rendering; SVG and source CSV must match on every platform.')
 else:check('png_renderer_available',1,1,'librsvg rsvg-convert is required for the delivered PNG reproduction')
 # Fresh numeric audit of existing P3 prose, never revises an article.
 audit=subprocess.run([sys.executable,'-I','-B',str(release/'code/audit_counts.py'),'--run',str(root),'--output',str(out/'counts_audit'),'--report',str(work/'2026-10-27/registry_polymarket/p3/P3_详细实验报告.md')],cwd=work)
 check('existing_prose_and_numbers_audit',1,int(audit.returncode!=0))
 test=subprocess.run([sys.executable,'-I','-B',str(release/'code/run_interface_tests.py'),'--output',str(out/'test_outputs')],cwd=work)
 check('packaged_interface_tests',1,int(test.returncode!=0))
 fixture_scan=[];scanned=0
 # Scan all CSV bytes (including free text) for the reserved fixture marker.
 for f in (root/'processed').glob('*.csv'):
  tail=b''
  with f.open('rb') as stream:
   for chunk in iter(lambda:stream.read(2**20),b''):
    scanned+=len(chunk)
    if b'synthetic_test' in tail+chunk:fixture_scan.append(f.name);break
    tail=chunk[-32:]
 check('synthetic_marker_excluded_from_real_processed',len(expected_data),fixture_scan,f'{scanned} bytes scanned')
 # All capsule inputs that must be immutable remain identical after rebuilding;
 # output reports are deliberately overwritten by fresh validation.
 immutable=[r for r in inputs if not any(x in Path(r['path']).parts for x in ['reports','manuscript'])]
 check('immutable_inputs_unchanged',len(immutable),[r['path'] for r in immutable if sha(work/r['path'])!=r['sha256']])
 check('network_and_original_path_negative_controls',3,int(worker['blocked_negative_controls']['network']<2 or worker['blocked_negative_controls']['outside_file']<1))
 for c in checks:
  c.update(severity='error',executed_at_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),code_version=sha(release/'code/accept_delivery.py'))
 result=dict(status='passed' if all(c['status']=='passed' for c in checks) else 'failed',delivery_stage='personal_candidate',article_revision='excluded_by_user',real_lifecycle_integration_status='awaiting_integration',common_cutoff_utc=None,release_id=load(release/'release.json')['release_id'],checks=checks,elapsed_seconds=round(time.monotonic()-start,3),independent_directory=str(out),network_requests=0,network_negative_controls=2,filesystem_negative_controls=1,peak_worker_rss_bytes=worker['peak_rss_bytes'],workspace_retained=a.keep_workspace,completed_at_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
 save(out/'acceptance.json',result)
 # Keep audit evidence; huge regenerable tables are removed only within this new run.
 if not a.keep_workspace:shutil.rmtree(work)
 print('ACCEPTANCE',result['status'],len(checks),'checks',flush=True)
 if result['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
