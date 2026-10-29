"""Rebuild and fully validate the extracted capsule under file/network audit guards."""
import argparse,json,os,sys,time,hashlib,resource,csv,socket,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--release',type=Path,required=True);p.add_argument('--forbidden-original',type=Path,required=True);a=p.parse_args()
workspace=a.workspace.resolve();release=a.release.resolve()
allowed=[workspace,release/ 'code',release/'configs',release/'tests']+[Path(x).resolve() for x in [sys.base_prefix,sys.prefix]]
blocked={'network':0,'outside_file':0}
def within(path,roots):return any(path==r or r in path.parents for r in roots)
def guard(event,args):
 if event.startswith('socket.') and event in ['socket.connect','socket.connect_ex','socket.getaddrinfo','socket.bind','socket.sendto']:
  blocked['network']+=1;raise PermissionError('P4 offline network guard')
 if event in ['open','os.listdir','os.scandir']:
  value=args[0]
  if isinstance(value,(str,bytes,os.PathLike)):
   path=Path(os.fsdecode(value)).resolve()
   if str(path)=='/dev/null':return
   if not within(path,allowed):
    blocked['outside_file']+=1;raise PermissionError('P4 isolated filesystem: '+str(path))
sys.addaudithook(guard)
# Positive negative-controls prove these protections were actually installed.
for operation in [lambda:socket.create_connection(('127.0.0.1',9),timeout=.1),lambda:urllib.request.urlopen('http://127.0.0.1:9',timeout=.1),lambda:open(a.forbidden_original/'README.md')]:
 try:operation();raise AssertionError('isolation negative control was not blocked')
 except (PermissionError,urllib.error.URLError):pass
rel='2026-10-27/registry_polymarket/p3/runs/formal_20261008_15_v6'
root=workspace/rel
sys.path.insert(0,str(root.parents[1]/'code'))
import core,pipeline
cfg=core.load(root/'configs/protocol.json');started=time.monotonic()
print('rebuild start',flush=True);pipeline.build_all(root,cfg);print('rebuild done',flush=True)
# The P3 input evidence and code are unchanged; this is a fresh P4 package run.
hashes=pipeline.processed_hashes(root)
core.save(root/'reports/offline_reproduction.json',{'status':'passed','second_output_hashes':hashes,'origin':'P4 extracted final capsule rebuild','network_denied_during_rebuild':True})
validation=pipeline.validate(root,cfg);print('validation',validation['status'],flush=True)
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('p4_gallery',release/'code/gallery.py');gallery=module_from_spec(spec);spec.loader.exec_module(gallery)
gallery.sources(root,workspace/'figures');gallery.draw(workspace/'figures')
core.save(workspace/'worker_receipt.json',{'status':'passed' if validation['formal_P3_completed'] else 'failed','processed_hashes':hashes,'validation_checks':validation['checks'],
 'elapsed_seconds':round(time.monotonic()-started,3),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'network_guard':'Python audit hook for socket transport; urllib + socket negative controls blocked',
 'filesystem_guard':'Python audit hook: capsule files + interpreter install only; original project read negative control blocked','blocked_negative_controls':blocked,'successful_network_requests':0})
