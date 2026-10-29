#!/usr/bin/env python3
"""One P3 entry point. Default commands are offline; run requires explicit opt-in."""
import argparse,sys,traceback
from core import *
from pipeline import preflight,replay,run,smoke,build_all,validate,artifacts,reproduce,guard_output,apply_reviews

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=ROOT/'configs/protocol.json')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('preflight');sub.add_parser('plan')
    r=sub.add_parser('replay-p2');r.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('smoke');s.add_argument('--output',type=Path,required=True);s.add_argument('--online',action='store_true')
    r=sub.add_parser('run');r.add_argument('--output',type=Path,required=True);r.add_argument('--authorize-formal-run',action='store_true')
    r=sub.add_parser('rebuild');r.add_argument('--output',type=Path,required=True)
    r=sub.add_parser('reproduce');r.add_argument('--output',type=Path,required=True)
    r=sub.add_parser('apply-reviews');r.add_argument('--output',type=Path,required=True);r.add_argument('--reviews',type=Path,required=True);r.add_argument('--defer-rebuild',action='store_true',help='Validate and save review amendment; mark old derived validation pending until the following formal run rebuilds it')
    a=p.parse_args(argv);cfg=check_config(load(a.config))
    if hasattr(a,'output'):a.output=guard_output(a.output)
    if a.command=='plan':
        result={'state':'prepared_waiting_for_user_start','candidate_window':[cfg['candidate_start_utc'],cfg['candidate_end_utc']],'days':utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc']),'steps':['verify frozen P0-P2 inputs','per-day historical version/boundary preflight','freeze formal protocol only after checks','reuse validated day1 native evidence','collect remaining days with checkpoints','expand all seven market categories','Registry + multi-outcome joins','whole legacy week differences + metadata','validation + offline reproducibility + artifacts'],'formal_collection_started':False}
    elif a.command=='preflight':result=preflight(cfg);save(ROOT/'reports/preflight.json',result)
    elif a.command=='replay-p2':result=replay(a.output,cfg)
    elif a.command=='smoke':
        if not a.online:raise Halt('smoke requires --online; it performs seven tiny source probes')
        result=smoke(a.output,cfg)
    elif a.command=='run':result=run(a.output,cfg,a.authorize_formal_run)
    elif a.command=='apply-reviews':result=apply_reviews(a.output,a.reviews,a.defer_rebuild)
    else:
        local=load(a.output/'configs/protocol.json')
        if local is None:raise Halt('No frozen run protocol')
        with run_lock(a.output):
            if a.command=='reproduce':
                result=reproduce(a.output,local);print(json.dumps({k:v for k,v in result.items() if k not in ['input_hashes','first_output_hashes','second_output_hashes']},ensure_ascii=False,indent=2));return 0
            build_all(a.output,local);result=validate(a.output,local,local.get('dataset_kind')=='real_archived_replay');artifacts(a.output,local,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result.get('status')=='failed':return 1
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (Halt,ValueError,KeyError) as e:
        print('P3_STOP: '+str(e),file=sys.stderr);raise SystemExit(2)
