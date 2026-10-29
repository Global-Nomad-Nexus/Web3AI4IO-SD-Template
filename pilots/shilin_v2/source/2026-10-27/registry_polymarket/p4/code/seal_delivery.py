"""Synchronize review artifacts and seal the deliverable file set, never modify P3."""
import csv,hashlib,json,shutil,sys,os
from pathlib import Path
P4=Path(__file__).resolve().parents[1];RELEASE=P4/'delivery/p4_personal_candidate_20261029'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def main():
 for name in ['code','configs','tests','docs','figures']:
  shutil.copytree(P4/name,RELEASE/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 # Include local test evidence outside official real data; fixture labels remain intact.
 shutil.copytree(P4/'test_outputs',RELEASE/'test_outputs',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copy2(P4/'README.md',RELEASE/'README.md')
 for p in [P4/'handoff_to_claire.md',P4/'joint_revision_checklist.md']:shutil.copy2(p,RELEASE/p.name)
 if (P4/'reports/counts_audit').exists():shutil.copytree(P4/'reports/counts_audit',RELEASE/'reports/counts_audit',dirs_exist_ok=True)
 (RELEASE/'reports').mkdir(exist_ok=True)
 for name in ['interface_test_report.md','release_scope.json','acceptance_checklist.csv']:
  if (P4/'reports'/name).exists():shutil.copy2(P4/'reports'/name,RELEASE/'reports'/name)
 rel=json.loads((RELEASE/'release.json').read_text());rel['p4_code_lock']={p.name:sha(p) for p in sorted((RELEASE/'code').glob('*.py'))};rel['interface_version']='shilin_lifecycle_adapter_v1';rel['png_renderer']='rsvg-convert 2.63.2';rel['schema_metadata_status']='Croissant 1.1 descriptor; locally structural checked; official validator not run; publication metadata pending';rel['sealed_scope']='all files except file_manifest.json itself; checksum for manifest stored externally';(RELEASE/'release.json').write_text(json.dumps(rel,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 rows=[]
 for p in sorted(RELEASE.rglob('*')):
  if p.is_file() and p.name!='file_manifest.json' and '__pycache__' not in p.parts:
   rows.append(dict(path=str(p.relative_to(RELEASE)),sha256=sha(p),bytes=p.stat().st_size,delivery_stage='personal_candidate',input_version='P3_v6',protocol_sha256=rel['protocol_sha256'],interface_version=rel['interface_version']))
 (RELEASE/'file_manifest.json').write_text(json.dumps(rows,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 (P4/'reports/delivery_manifest.sha256').write_text(sha(RELEASE/'file_manifest.json')+'  file_manifest.json\n')
 print('SEALED',len(rows),'files',flush=True)
if __name__=='__main__':main()
