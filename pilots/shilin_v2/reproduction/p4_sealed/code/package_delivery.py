"""Build a local-only, self-contained P4 delivery from frozen P3 v6 inputs."""
import csv,gzip,hashlib,json,os,shutil,sys,tarfile,time
from pathlib import Path
P4=Path(__file__).resolve().parents[1];PARENT=P4.parent;PROJECT=PARENT.parents[1]
P3=PARENT/'p3';RUN=P3/'runs/formal_20261008_15_v6';REL=RUN.relative_to(PROJECT)

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n')

def main():
 out=P4/'delivery/p4_personal_candidate_20261029';out.mkdir(parents=True,exist_ok=True)
 # Preserve original relative geometry so source references and rebuilt CSV bytes stay identical.
 included={}
 def add(p):
  if p.is_file() and not any(x in p.parts for x in ['__pycache__','.git']) and p.name!='.DS_Store':included[str(p.relative_to(PROJECT))]=p
 def tree(p):
  for x in p.rglob('*'):add(x)
 for d in [RUN/'days',RUN/'raw',RUN/'rules',RUN/'reports',RUN/'provenance',RUN/'configs',
           PARENT/'p2/raw',PARENT/'p2/vendor',PARENT/'p2/reports',PARENT/'p2/configs',
           PARENT/'raw',PARENT/'processed',PARENT/'reports',
           PROJECT/'1021/scientific-data-essential/data/7day-72h-20261008-release']:
  tree(d)
 for d in [P3/'code',P3/'configs']:tree(d)
 for name in ['pm_markets','pm_outcomes','pm_prices','pm_mapping','pm_activity','pm_candidate_catalogue']:add(RUN/'processed'/(name+'.csv'))
 # Snapshot documentation is read-only and explicitly not a new P4 article.
 tree(RUN/'manuscript');add(P3/'P3_详细实验报告.md')
 add(PARENT/'p2/code/native_call_tree.py')
 manifest=[];started=time.monotonic()
 archive=out/'inputs.tar.gz'
 with archive.open('wb') as f,gzip.GzipFile(fileobj=f,mode='wb',compresslevel=1,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tar:
  for i,(rel,p) in enumerate(sorted(included.items())):
   tar.add(p,arcname=rel,recursive=False)
   manifest.append(dict(path=rel,sha256=sha(p),bytes=p.stat().st_size))
   if i%1000==0:print('capsule',i,len(included),flush=True)
 save(out/'input_manifest.json',manifest)
 # Compact delivered data; acceptance compares regenerated uncompressed bytes to P3 locks.
 data=out/'data';data.mkdir(exist_ok=True)
 for p in sorted((RUN/'processed').glob('*.csv')):
  dst=data/(p.name+'.gz')
  with p.open('rb') as src,dst.open('wb') as f,gzip.GzipFile(fileobj=f,mode='wb',compresslevel=1,mtime=0) as gz:shutil.copyfileobj(src,gz,2**20)
  print('compressed',p.name,flush=True)
 shutil.copy2(RUN/'provenance/processed_manifest.csv',out/'data_manifest.csv')
 shutil.copy2(RUN/'configs/data_dictionary.csv',out/'data_dictionary.csv')
 # Code/tests/docs are synchronized again at final seal.
 save(out/'release.json',dict(release_id=out.name,delivery_stage='personal_candidate',distribution='local_review_only',
  original_run=str(REL),input_version='P3 formal_20261008_15_v6',protocol_sha256=sha(RUN/'configs/protocol.json'),
  code_commit=None,code_version='file_hash_locks; source tree not committed for this delivery',
  creation_window=['2026-10-08T00:00:00Z','2026-10-15T00:00:00Z'],common_cutoff_utc=None,
  real_lifecycle_integration_status='awaiting_integration',article_scope='existing P3 snapshot read-only; no article authored or revised',
  input_files=len(manifest),input_uncompressed_bytes=sum(x['bytes'] for x in manifest),capsule_sha256=sha(archive),
  capsule_elapsed_seconds=round(time.monotonic()-started,3),python_rebuild_version=sys.version,external_uploads=0))
 print('PACKAGE_BASE_READY',out,flush=True)
if __name__=='__main__':main()
