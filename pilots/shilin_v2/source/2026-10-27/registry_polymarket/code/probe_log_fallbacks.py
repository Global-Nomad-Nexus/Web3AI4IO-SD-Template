"""Independent provider diagnostic after primary endpoints deny historical logs."""
from common import *

def run():
    rows=read_csv(ROOT/'reports/source_capability.csv');versions=read_csv(ROOT/'configs/platform_versions.csv')
    c=EvidenceClient(budget=14)
    original=list(rows)
    for chain,url in [('eip155:8453','https://base-rpc.publicnode.com'),('eip155:56','https://bsc-rpc.publicnode.com'),('eip155:56','https://public.1rpc.io/bnb')]:
        addresses=[v['program_or_contract'] for v in versions if v['chain_id']==chain]
        for bound in [r for r in original if r['chain_key']==chain and r['method']=='timestamp_boundary_verified']:
            if any(r['endpoint']==url and r['method']=='eth_getLogs' and r['target_date_utc']==bound['target_date_utc'] for r in rows):continue
            n=int(bound['block_number']);params={'fromBlock':hex(n),'toBlock':hex(n+19),'address':addresses}
            data,m=c.rpc(url,'eth_getLogs',[params],'independent_provider_20block_factory_log_diagnostic')
            result=data.get('result') if isinstance(data,dict) else None
            rows.append({'chain_key':chain,'endpoint':url,'method':'eth_getLogs','target_date_utc':bound['target_date_utc'],'query_purpose':bound['query_purpose']+'_independent_provider_all_registered_factories_20blocks','http_status':m['http_status'],'response_state':'error' if m['error'] else ('null_result' if result is None else 'returned'),'error':m['error'],'actual_record_count':len(result) if isinstance(result,list) else 0,'elapsed_seconds':m['elapsed_seconds'],'request_id':m['request_id'],'raw_ref':m['raw_ref'],'retrieved_at_utc':m['retrieved_at_utc'],'requires_credentials':False,'earliest_available_history':'finite_target_only','pagination_can_advance':'not_applicable','full_window_coverage':'not_tested','block_number':n})
            print(chain,bound['query_purpose'],m['error'],len(result) if isinstance(result,list) else None,flush=True)
            if result:
                receipt,rm=c.rpc(url,'eth_getTransactionReceipt',[result[0]['transactionHash']],'factory_log_receipt_consistency')
                write_json(ROOT/f'reports/{chain.replace(":","_")}_{bound["query_purpose"]}_factory_receipt_check.json',{'log_raw_ref':m['raw_ref'],'receipt_raw_ref':rm['raw_ref'],'receipt_status':receipt.get('result',{}).get('status') if isinstance(receipt,dict) else None,'scope':'transport consistency; event topics and historical platform version applicability need P2 validation'})
            # A method-wide provider refusal is a capability finding; stop this provider.
            if m['http_status'] in [403,429] or (m['error'] and 'limit' in m['error'].lower()):break
    write_csv(ROOT/'reports/source_capability.csv',rows)
    write_json(ROOT/'reports/log_fallback_receipt.json',{'completed_at_utc':now(),'network_calls_this_invocation':c.calls,'reason':'Primary public providers returned log-method refusal; one bounded independent-provider capability diagnostic, no rate-limit retry loop.'})

if __name__=='__main__':run()
