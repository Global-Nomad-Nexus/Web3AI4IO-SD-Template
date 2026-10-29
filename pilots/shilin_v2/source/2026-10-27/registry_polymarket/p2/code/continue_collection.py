"""Bounded restart supervisor for completed/cache-backed chunks, not gap skipping."""
from p2io import *
import subprocess,argparse
def run(chain):
    for round_number in range(1,7):
        print('RESUME_ROUND',round_number,chain,flush=True)
        p=subprocess.run([sys.executable,str(ROOT/'code/collect.py'),'--chain',chain])
        if p.returncode==0:return
        ledger=read_csv(ROOT/'reports'/('query_ledger_'+chain.replace(':','_')+'.csv'))
        last=ledger[-1]
        if last['status']=='request_failed' and not any(x in last['error'] for x in ['529','502','503','504','429','timed out','reset','budget']):raise SystemExit(p.returncode)
        if round_number<6:time.sleep(30)
    raise SystemExit('Bounded resume rounds exhausted; retained exact remaining range')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--chain',required=True);run(p.parse_args().chain)
