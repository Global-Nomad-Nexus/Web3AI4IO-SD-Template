"""Native full-range Base log path after a successful 10k-block capability probe."""
from p2io import *

def run():
    c=Client(budget=150);vs=[r for r in json.loads((ROOT/'configs/platform_events.json').read_text()) if r['chain_key']=='eip155:8453'];url='https://base-rpc.publicnode.com'
    cfg=json.loads((ROOT/'configs/pilot_protocol.json').read_text());start,end=cfg['chain_bounds_inclusive_start_exclusive_end']['eip155:8453'];all_logs=[];ledger=[]
    for a in range(start,end,10000):
        z=min(end-1,a+9999);params={'fromBlock':hex(a),'toBlock':hex(z),'address':[v['address'] for v in vs],'topics':[sorted({v['topic0'] for v in vs})]}
        data,m=c.rpc(url,'eth_getLogs',[params],'Base_native_creation_logs_full_chunk')
        if not isinstance(data,list) or not m['ok']:raise RuntimeError('Base native logs unavailable: '+m['error'])
        all_logs.extend(data);ledger.append({'chain_key':'eip155:8453','from_block':a,'query_to_block':z,'scanned_through':z,'status':'complete_segment','returned_block_rows':'RPC_logs','returned_creation_candidates':len(data),'request_id':m['request_id'],'raw_ref':m['raw_ref'],'raw_sha256':m['sha256'],'retrieved_at_utc':m['retrieved_at_utc'],'filter_sha256':sid(params['address'],params['topics']),'error':''})
        print(a,z,len(data),flush=True)
    receipts={};headers={};receipt_refs={};header_refs={}
    calls=[('receipt',sig) for sig in sorted({l['transactionHash'] for l in all_logs})]+[('header',number) for number in sorted({l['blockNumber'] for l in all_logs},key=lambda x:int(x,16))]
    for offset in range(0,len(calls),20):
        batch=calls[offset:offset+20];payload=[{'jsonrpc':'2.0','id':i,'method':'eth_getTransactionReceipt' if kind=='receipt' else 'eth_getBlockByNumber','params':[key] if kind=='receipt' else [key,False]} for i,(kind,key) in enumerate(batch)]
        data,m=c.json(url,payload,'Base_native_receipt_header_batch')
        if not isinstance(data,list) or not m['ok']:raise RuntimeError('Native RPC batch failed')
        by_id={x['id']:x for x in data}
        for i,(kind,key) in enumerate(batch):
            d=by_id[i].get('result')
            if not d:raise RuntimeError('Missing batch result')
            if kind=='receipt':receipts[key]=d;receipt_refs[key]=m['raw_ref']
            else:headers[key]=d;header_refs[key]=m['raw_ref']
        print('BATCH',offset,len(calls),flush=True)
    # Normalize native RPC data into the same stored block envelope consumed by decode.
    normalized=[]
    for key,h in sorted(headers.items(),key=lambda kv:int(kv[0],16)):
        logs=[l for l in all_logs if l['blockNumber']==key];txs=[]
        for sig in sorted({l['transactionHash'] for l in logs}):
            rc=receipts[sig]
            if rc['blockHash']!=h['hash']:raise RuntimeError('Receipt/header hash conflict')
            for l in [x for x in logs if x['transactionHash']==sig]:
                if l.get('removed'):raise RuntimeError('Removed log')
                if not any(x['logIndex']==l['logIndex'] and x['data']==l['data'] and x['topics']==l['topics'] and x['address'].lower()==l['address'].lower() for x in rc['logs']):raise RuntimeError('Selected log absent from receipt')
            txs.append({'hash':sig,'from':rc['from'],'to':rc['to'],'status':int(rc['status'],16),'transactionIndex':int(rc['transactionIndex'],16),'receipt_raw_ref':receipt_refs[sig]})
        normalized.append({'header':{'number':int(key,16),'hash':h['hash'],'timestamp':int(h['timestamp'],16)},'transactions':txs,'logs':[{**l,'logIndex':int(l['logIndex'],16),'transactionIndex':int(l['transactionIndex'],16)} for l in logs],'header_raw_ref':header_refs[key]})
    path=ROOT/'raw/base_native_normalized.ndjson';path.write_bytes(b'\n'.join(json.dumps(x).encode() for x in normalized)+b'\n')
    write_csv(ROOT/'reports/base_rpc_query_ledger.csv',ledger)
    write_json(ROOT/'reports/base_rpc_receipt.json',{'status':'passed','log_rows':len(all_logs),'receipts_checked':len(receipts),'block_headers_checked':len(headers),'normalized_ref':str(path.relative_to(ROOT)),'normalized_sha256':sha(path),'raw_query_refs':[r['raw_ref'] for r in ledger],'source':'native public Base RPC; every selected log checked against receipt and header'})
    print('BASE_COMPLETE',len(all_logs),flush=True)
if __name__=='__main__':run()
