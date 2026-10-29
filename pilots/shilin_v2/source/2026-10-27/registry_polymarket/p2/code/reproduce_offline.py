"""Zero-network rebuild of the current fixed input checkpoint, with input-change guard."""
from p2io import *
import subprocess,resource

def inputs():
    paths=list((ROOT/'configs').glob('*.json'))+list((ROOT/'reports').glob('query_ledger*.csv'))+list((ROOT/'code').glob('*.py'))
    paths+=list((ROOT/'reports').glob('base_rpc*.csv'))+list((ROOT/'reports').glob('base_rpc_receipt.json'))
    paths += [ROOT/'reports/native_QA.csv',ROOT/'reports/bsc_all_native_QA.csv']
    paths += [ROOT/'reports/vibe_history_partitions.csv',ROOT/'reports/vibe_history_receipt.json',ROOT/'reports/cryptohouse_header_partitions.csv',ROOT/'data/solana_header_sources.csv',ROOT/'reports/solana_light_query_ledger.csv',ROOT/'reports/solana_targeted_state_queries.csv']
    paths += [ROOT/'reports/solana_native_index_pages.csv',ROOT/'reports/solana_native_creation_candidates.csv',ROOT/'reports/solana_native_index_failed_transactions.csv',ROOT/'reports/solana_native_index_receipt.json']
    for row in read_csv(ROOT/'reports/solana_native_index_pages.csv'):paths.append(ROOT/row['raw_ref'])
    for file,hashkey in [(ROOT/'reports/vibe_history_partitions.csv','sha256'),(ROOT/'reports/cryptohouse_header_partitions.csv','sha256'),(ROOT/'reports/solana_light_query_ledger.csv','raw_sha256')]:
        if file.exists():
            for row in read_csv(file):
                if row.get('raw_ref'):paths.append(ROOT/row['raw_ref'])
    for name in ['pm_markets','pm_outcomes','pm_prices','pm_mapping']:paths.append(PARENT/'processed'/(name+'.csv'))
    for path in (ROOT/'reports').glob('query_ledger*.csv'):
        for r in read_csv(path):
            if r['status']=='complete_segment':paths.append(ROOT/r['raw_ref'])
    if (ROOT/'raw/base_native_normalized.ndjson').exists():paths.append(ROOT/'raw/base_native_normalized.ndjson')
    return {str(p):sha(p) for p in sorted(set(paths)) if p.exists()}

def fingerprints():return {p.name:sha(p) for p in sorted((ROOT/'processed').glob('*.csv'))}

def run():
    begin=now();clock=time.monotonic();before=inputs();steps=[]
    pipeline=['prepare_vibe_creations.py','decode.py','build.py'] if (ROOT/'reports/vibe_history_receipt.json').exists() else ['decode.py','build.py']
    for name in pipeline:
        p=subprocess.run([sys.executable,str(ROOT/'code'/name)],capture_output=True,text=True);steps.append({'script':name,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        if p.returncode:raise RuntimeError(p.stderr)
    first=fingerprints()
    for name in pipeline:
        p=subprocess.run([sys.executable,str(ROOT/'code'/name)],capture_output=True,text=True);steps.append({'script':name,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        if p.returncode:raise RuntimeError(p.stderr)
    second=fingerprints();after=inputs()
    fixed=before==after
    report={'started_at_utc':begin,'completed_at_utc':now(),'network_requests':0,'input_snapshot_unchanged':fixed,'input_hashes':before,'first_output_hashes':first,'second_output_hashes':second,'byte_identical_processed_outputs':first==second,'steps':steps,'elapsed_seconds':round(time.monotonic()-clock,3),'child_peak_RSS_raw':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'RSS_unit':'bytes on this macOS; KiB on Linux','status':'passed_for_fixed_checkpoint' if fixed and first==second else 'not_fixed_inputs_or_nondeterministic','completion_scope':'A checkpoint replay does not upgrade incomplete whole-window coverage.'}
    write_json(ROOT/'reports/offline_reproduction.json',report);print(json.dumps({k:report[k] for k in ['status','network_requests','input_snapshot_unchanged','byte_identical_processed_outputs','elapsed_seconds']}),flush=True)
if __name__=='__main__':run()
