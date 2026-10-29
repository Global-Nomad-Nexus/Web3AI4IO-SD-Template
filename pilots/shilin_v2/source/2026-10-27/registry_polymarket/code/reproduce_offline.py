"""Recompute P0 and P1 joins from archived inputs; never calls HTTP."""
import collections
import resource
import subprocess
import sys
import time
from common import *

def fingerprint():
    result={}
    for name in ['token_id_crosswalk','registry','creation_events','metadata_coverage','pm_mapping','token_expectations_at_creation','context_daily']:
        p=ROOT/'processed'/(name+'.csv')
        if not p.exists():continue
        rows=read_csv(p)
        normalized=[{k:v for k,v in r.items() if k not in ['imported_at_utc','mapping_created_at_utc']} for r in rows]
        result[name]=sid(sorted(json.dumps(r,sort_keys=True) for r in normalized))
    return result

def run():
    before=fingerprint();start=now();clock=time.monotonic();steps=[]
    for script in ['p0_baseline.py','build_views.py','validate.py']:
        t=time.monotonic()
        p=subprocess.run([sys.executable,str(ROOT/'code'/script)],capture_output=True,text=True)
        steps.append({'script':script,'exit_code':p.returncode,'elapsed_seconds':round(time.monotonic()-t,4),'stdout':p.stdout,'stderr':p.stderr})
        if p.returncode:break
    after=fingerprint()
    report={'started_at_utc':start,'completed_at_utc':now(),'elapsed_seconds':round(time.monotonic()-clock,4),'network_calls':0,'steps':steps,'semantic_fingerprints_before':before,'semantic_fingerprints_after':after,'same_semantic_outputs':before==after,'excluded_clock_fields':['imported_at_utc','mapping_created_at_utc'],'child_peak_rss_raw':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'rss_unit':'bytes_on_macOS;KiB_on_Linux','status':'passed' if before==after and all(x['exit_code']==0 for x in steps) else 'failed'}
    write_json(ROOT/'reports/offline_reproduction.json',report)
    print(json.dumps({k:report[k] for k in ['status','network_calls','same_semantic_outputs','elapsed_seconds','child_peak_rss_raw']}))
    if report['status']=='failed':raise SystemExit(1)

if __name__=='__main__':run()
