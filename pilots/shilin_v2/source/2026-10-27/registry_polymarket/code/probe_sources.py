"""Bounded public historical RPC probes; never claim whole-window coverage."""
import argparse
from common import *

def run(refresh=False):
    c=EvidenceClient(refresh=refresh,budget=220);rows=[]
    def call(chain,url,method,params,target='',purpose=''):
        data,m=c.rpc(url,method,params,purpose)
        result=data.get('result') if isinstance(data,dict) else None
        rows.append({'chain_key':chain,'endpoint':url,'method':method,'target_date_utc':target,
          'query_purpose':purpose,'http_status':m['http_status'],'response_state':'error' if m['error'] else ('null_result' if result is None else 'returned'),
          'error':m['error'],'actual_record_count':len(result) if isinstance(result,list) else (1 if result is not None else 0),
          'elapsed_seconds':m['elapsed_seconds'],'request_id':m['request_id'],'raw_ref':m['raw_ref'],
          'retrieved_at_utc':m['retrieved_at_utc'],'requires_credentials':False,'earliest_available_history':'not_established_by_finite_probe','pagination_can_advance':'not_applicable','full_window_coverage':'not_tested'})
        write_csv(ROOT/'reports/source_capability.csv',rows)
        print(chain,method,purpose,rows[-1]['response_state'],m['error'][:90],flush=True)
        return result,m
    events=sorted(read_csv(RELEASE/'launch_events.csv'),key=lambda r:int(r['block_time']))
    targets=[('start',events[0]),('mid',min(events,key=lambda r:abs(int(r['block_time'])-1791720000))),('end',events[-1])]
    sol_endpoint=None
    for endpoint in ['https://solana-rpc.publicnode.com','https://api.mainnet-beta.solana.com']:
        result,m=call('solana:mainnet',endpoint,'getSlot',[{'commitment':'finalized'}],purpose='public_current_connectivity_only')
        if result is not None and not m['error']:
            sol_endpoint=endpoint;break
    if sol_endpoint:
        call('solana:mainnet',sol_endpoint,'getFirstAvailableBlock',[],purpose='reported_first_retained_block_not_archive_guarantee')
        for name,r in targets:
            t=iso(r['block_time']);slot=int(r['slot'])
            call('solana:mainnet',sol_endpoint,'getBlock',[slot,{'commitment':'finalized','transactionDetails':'none','rewards':False,'maxSupportedTransactionVersion':0}],t,'legacy_'+name+'_block')
            tx,meta=call('solana:mainnet',sol_endpoint,'getTransaction',[r['transaction_signature'],{'commitment':'finalized','encoding':'jsonParsed','maxSupportedTransactionVersion':0}],t,'legacy_'+name+'_versioned_tx_inner_instructions')
            if tx:
                write_json(ROOT/f'reports/solana_{name}_transaction_check.json',{'legacy_event_key':r['event_key'],'raw_ref':meta['raw_ref'],'meta_err':tx.get('meta',{}).get('err'),'version':tx.get('version'),'slot_matches':str(tx.get('slot'))==r['slot'],'block_time_matches':str(tx.get('blockTime'))==r['block_time'],'inner_instruction_groups':len(tx.get('meta',{}).get('innerInstructions') or []),'validation_scope':'transport and native transaction fields; legacy create decoder not silently generalized'})
        r=targets[-1][1];params={'before':r['transaction_signature'],'limit':5,'commitment':'finalized'}
        a,m=call('solana:mainnet',sol_endpoint,'getSignaturesForAddress',['6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P',params],iso(r['block_time']),'historical_program_page1')
        if a:
            b,n=call('solana:mainnet',sol_endpoint,'getSignaturesForAddress',['6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P',{'before':a[-1]['signature'],'limit':5,'commitment':'finalized'}],iso(r['block_time']),'historical_program_page2')
            progressed=bool(b) and not ({x['signature'] for x in a}&{x['signature'] for x in b})
            rows[-1]['pagination_can_advance']=progressed
    versions=read_csv(ROOT/'configs/platform_versions.csv')
    for chain,urls in [('eip155:8453',['https://mainnet.base.org','https://base-rpc.publicnode.com']),('eip155:56',['https://bsc-dataseed.bnbchain.org','https://bsc-rpc.publicnode.com'])]:
        url=None;tip=None
        for candidate in urls:
            head,m=call(chain,candidate,'eth_blockNumber',[],purpose='public_current_connectivity_only')
            if head and not m['error']:url=candidate;tip=int(head,16);break
        if not url:continue
        blockcache={}
        def block(n):
            if n not in blockcache:
                result,m=call(chain,url,'eth_getBlockByNumber',[hex(n),False],purpose='timestamp_boundary_search')
                if not result:raise ValueError('historical block unavailable')
                blockcache[n]=(result,m)
            return blockcache[n]
        def at_time(t):
            lo=1;hi=tip
            while lo<hi:
                mid=(lo+hi)//2;b,m=block(mid)
                if int(b['timestamp'],16)<t:lo=mid+1
                else:hi=mid
            return lo
        bounds=[]
        for name,t in [('start',1791417600),('mid',1791720000),('end',1792022399)]:
            try:
                n=at_time(t);b,m=block(n);prev,pm=block(n-1)
                rows.append({'chain_key':chain,'endpoint':url,'method':'timestamp_boundary_verified','target_date_utc':iso(t),'query_purpose':name,'http_status':200,'response_state':'returned','error':'','actual_record_count':1,'elapsed_seconds':0,'request_id':m['request_id'],'raw_ref':m['raw_ref'],'retrieved_at_utc':m['retrieved_at_utc'],'requires_credentials':False,'earliest_available_history':'finite_target_only','pagination_can_advance':'block_ranges_tested','full_window_coverage':'not_tested','block_number':n,'block_time_utc':iso(int(b['timestamp'],16)),'boundary_bracket_valid':int(prev['timestamp'],16)<t<=int(b['timestamp'],16)})
                bounds.append((name,n,b,m))
                if b.get('transactions'):
                    call(chain,url,'eth_getTransactionReceipt',[b['transactions'][0]],iso(t),name+'_receipt_probe')
            except (ValueError,RuntimeError) as e:
                print('BOUNDARY_FAILURE',chain,name,str(e),flush=True);break
        method_blocked=False
        for name,n,b,m in bounds:
            if method_blocked:break
            for v in versions:
                if v['chain_id']!=chain:continue
                # All factory logs in a finite 20-block diagnostic chunk. No full cohort claim.
                logs,lm=call(chain,url,'eth_getLogs',[{'fromBlock':hex(n),'toBlock':hex(n+19),'address':v['program_or_contract']}],iso(int(b['timestamp'],16)),name+'_'+v['platform_id']+'_'+v['version']+'_factory_logs_20blocks')
                if lm['http_status'] in [403,429] or (lm['error'] and 'limit' in lm['error'].lower()):
                    method_blocked=True
                    break
    write_csv(ROOT/'reports/source_capability.csv',rows)
    write_json(ROOT/'reports/source_probe_receipt.json',{'completed_at_utc':now(),'network_calls_this_invocation':c.calls,'capability_rows':len(rows),'status':'finite_probes_only','warning':'Historical blocks/logs success does not establish complete platform version bounds or whole-window creation coverage.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');run(p.parse_args().refresh)
