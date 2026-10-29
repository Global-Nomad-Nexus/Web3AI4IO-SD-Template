"""Verify exact UTC boundaries and freeze a one-day, address/version scoped cohort."""
from p2io import *
import importlib.util,shutil
sys.path.insert(0,str(ROOT/'vendor'))
from eth_utils import keccak

def run():
    c=Client(budget=120);bounds={};evidence=[]
    def sol_time(n):
        t,m=c.rpc('https://api.mainnet-beta.solana.com','getBlockTime',[n],'exact_Solana_boundary_binary_search')
        if t is None:
            slots,sm=c.rpc('https://api.mainnet-beta.solana.com','getBlocks',[n,n+8,{'commitment':'finalized'}],'resolve_skipped_slot')
            if not slots:raise RuntimeError('Unobservable Solana boundary slot')
            n=slots[0];t,m=c.rpc('https://api.mainnet-beta.solana.com','getBlockTime',[n],'resolved_slot_time')
        if t is None:raise RuntimeError('Missing block time')
        return n,t,m
    for target in [1791417600,1791504000]:
        lo,hi=454000000,455000000
        while lo<hi:
            mid=(lo+hi)//2;n,t,m=sol_time(mid)
            if t<target:lo=n+1
            else:hi=mid
        n,t,m=sol_time(lo)
        prev,pm=c.rpc('https://api.mainnet-beta.solana.com','getBlocks',[max(0,n-8),n-1,{'commitment':'finalized'}],'previous_produced_slot_boundary')
        if not prev:raise RuntimeError('Cannot bracket boundary')
        pn,pt,pmeta=sol_time(prev[-1])
        if not pt<target<=t:raise RuntimeError('UTC boundary bracket failed')
        evidence.append({'chain_key':'solana:mainnet','target_utc':iso(target),'first_block_or_slot':n,'first_time_utc':iso(t),'previous_block_or_slot':pn,'previous_time_utc':iso(pt),'raw_ref':m['raw_ref'],'previous_raw_ref':pmeta['raw_ref'],'check':'previous_time < target <= first_time'})
        bounds.setdefault('solana:mainnet',[]).append(n)
        print('BOUNDARY solana',iso(target),n,t,flush=True)
    for chain,url,numbers in [('eip155:8453','https://mainnet.base.org',[52314127,52357327]),('eip155:56','https://bsc-dataseed.bnbchain.org',[126344214,126536085])]:
        for target,n in zip([1791417600,1791504000],numbers):
            b,m=c.rpc(url,'eth_getBlockByNumber',[hex(n),False],'EVM_boundary_block')
            prev,pm=c.rpc(url,'eth_getBlockByNumber',[hex(n-1),False],'EVM_previous_boundary_block')
            if not b or not prev or not int(prev['timestamp'],16)<target<=int(b['timestamp'],16):raise RuntimeError('EVM boundary mismatch')
            bounds.setdefault(chain,[]).append(n)
            evidence.append({'chain_key':chain,'target_utc':iso(target),'first_block_or_slot':n,'first_time_utc':iso(int(b['timestamp'],16)),'previous_block_or_slot':n-1,'previous_time_utc':iso(int(prev['timestamp'],16)),'raw_ref':m['raw_ref'],'previous_raw_ref':pm['raw_ref'],'check':'previous_time < target <= first_time'})
    spec=importlib.util.spec_from_file_location('abi_registry',PILOT/'claire_demo/registry.py');abi_reg=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi_reg)
    versions=read_csv(PARENT/'configs/platform_versions.csv');registry=[]
    for v in versions:
        if v['platform_id']=='clanker':
            p=ROOT/'configs'/('clanker_'+v['version']+'.ts');abi=abi_reg.abi_from_typescript(p)
            ev=next(e for e in abi if e.get('type')=='event' and e.get('name')=='TokenCreated')
        elif v['platform_id']=='four.meme':
            if v['version']=='v1':continue # No verified native layout; retained as an explicit excluded version below.
            p=ROOT/'configs/four_meme_v2_events.json';abi=json.loads(p.read_text());ev=next(e for e in abi if e.get('type')=='event' and e.get('name')=='TokenCreate')
        else:continue
        signature=ev['name']+'('+','.join(x['type'] for x in ev['inputs'])+')'
        registry.append({'chain_key':v['chain_id'],'platform_id':v['platform_id'],'version':v['version'],'address':v['program_or_contract'].lower(),'event_name':ev['name'],'event_signature':signature,'topic0':'0x'+keccak(text=signature).hex(),'event_abi':ev,'source_revision':v['source_revision'],'abi_path':str(p.relative_to(ROOT)),'abi_sha256':sha(p),'historical_scope':'observed native event matching pinned ABI at listed address in frozen day; proxy implementation lineage not fully reconstructed'})
    write_json(ROOT/'configs/platform_events.json',registry)
    write_csv(ROOT/'reports/window_boundaries.csv',evidence)
    config={'protocol_version':'registry_pm_p2_20261008_v1','frozen_at_utc':now(),'creation_start_utc':'2026-10-08T00:00:00Z','creation_end_utc':'2026-10-09T00:00:00Z','interval':'[start,end)','selection_reason':'first predeclared legacy-day candidate; selected by obtainable history, not token success or price direction','chain_bounds_inclusive_start_exclusive_end':bounds,'source':'SQD public Portal /stream; only historical blocks well behind finalized heads; independent native RPC checks','creation_eligibility':'successful committed Pump.fun create/create_v2; exact TokenCreated/TokenCreate topic at explicitly listed factories; no URI/trade/graduation/metadata-success filter','known_scope_exclusions':[{'chain':'eip155:56','platform':'four.meme','version':'v1','address':'0xec4549cadce5da21df6e6422d448034b5233bfbc','reason':'native layout not verified; separately query all logs and report whether creation-like unknown topics occur; do not call full platform census'}],'chunk_sizes':{'solana:mainnet':20000,'eip155:8453':10000,'eip155:56':40000},'expected_stream_progress':'each response may be partial; resume last header.number+1 to inclusive toBlock; boundaries must be seen','request_budget_per_invocation':500,'max_response_bytes':64000000,'max_total_raw_bytes':512000000,'max_retries_transient':3,'timeout_seconds':45,'primary_max_price_age_hours':24,'strict_information_end_before_creation':True,'polymarket_mapping':'shared_economic_event:fomc:2026-10-28; retrospective demonstration with existing P1 limitations','lifecycle_enabled':False,'common_cutoff_utc':None,'code_scope':'all official SDK listed Base factories v0,v1,v2,v3,v3.1,v4; BSC v2 manager; named Pump.fun program create discriminators'}
    path=ROOT/'configs/pilot_protocol.json'
    if path.exists():
        old=json.loads(path.read_text())
        if old['chain_bounds_inclusive_start_exclusive_end']!=bounds:raise RuntimeError('Cannot silently alter frozen boundaries')
    else:write_json(path,config)
    print(json.dumps(bounds),flush=True)
if __name__=='__main__':run()
