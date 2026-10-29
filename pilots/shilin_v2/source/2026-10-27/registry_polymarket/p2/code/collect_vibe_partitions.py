"""Resolve documented100-row keyset pages with four workers and global<=3.3RPS.

Public cursor format slot:transactionIndex is documented by SVS. Boundaries
come from the independently complete official RPC index. Each returned page
must match its expected100 exact native signatures/order, including failed
transactions. A source/index disagreement is an error, never silently dropped.
"""
from p2io import *
from solana_index import AUTHORITY
import threading,concurrent.futures

def run():
    index=read_csv(ROOT/'reports/solana_native_creation_candidates.csv')+read_csv(ROOT/'reports/solana_native_index_failed_transactions.csv')
    index.sort(key=lambda r:(int(r['slot']),int(r['transaction_index_native'])))
    path=ROOT/'reports/vibe_history_partitions.csv';ledger=read_csv(path) if path.exists() else []
    done={int(r['partition']) for r in ledger if r['status']=='passed_exact_index_partition'};lock=threading.Lock();stop=threading.Event();next_start=[0.0]
    def fetch(offset):
        expected=index[offset:offset+100];part=offset//100+1
        if part in done:return None
        cfg={'transactionDetails':'full','sortOrder':'asc','limit':100,'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1,'filters':{'slot':{'gte':454377023,'lt':454698759},'blockTime':{'gte':1791417600,'lt':1791504000}}}
        cursor=''
        if offset:
            prev=index[offset-1];cursor=prev['slot']+':'+prev['transaction_index_native'];cfg['paginationToken']=cursor
        payload={'jsonrpc':'2.0','id':1,'method':'getTransactionsForAddress','params':[AUTHORITY,cfg]};client=Client(budget=7)
        for attempt in range(7):
            if stop.is_set():raise RuntimeError('Stopped after another partition error')
            with lock:
                time.sleep(max(0,next_start[0]-time.monotonic()));next_start[0]=time.monotonic()+.31
            body,m=client.once('https://public.rpc.solanavibestation.com/historical',payload,'public_Vibe_full_history_page_capability')
            if m['ok']:break
            if m['http_status'] not in [None,429,502,503,504,529]:stop.set();raise RuntimeError('Non-retryable Vibe error: '+m['error'])
            delay=max(min(2**(attempt+1),20),float({k.lower():v for k,v in m['response_headers'].items()}.get('retry-after','0')))
            with lock:next_start[0]=max(next_start[0],time.monotonic()+delay)
        else:stop.set();raise RuntimeError('Vibe transient retries exhausted')
        result=json.loads(body)['result'];data=result['data'];actual=[(str(r['slot']),str(r['transactionIndex']),r['transaction']['signatures'][0],json.dumps(r['meta']['err'],sort_keys=True)) for r in data]
        target=[(r['slot'],r['transaction_index_native'],r['signature'],json.dumps(json.loads(r['err_json']),sort_keys=True)) for r in expected]
        if actual!=target:stop.set();raise RuntimeError('Vibe/official index partition differs at '+str(part))
        if any(not 1791417600<=r['blockTime']<1791504000 for r in data):stop.set();raise RuntimeError('Vibe time window violation')
        if offset+len(expected)==len(index) and result.get('paginationToken'):stop.set();raise RuntimeError('Unexplained Vibe records beyond independent index endpoint')
        return {'partition':part,'requested_pagination_token':cursor,'next_pagination_token':result.get('paginationToken') or '', 'rows':len(data),'first_slot':expected[0]['slot'],'last_slot':expected[-1]['slot'],'first_signature':expected[0]['signature'],'last_signature':expected[-1]['signature'],'expected_signature_set_hash':sid([r['signature'] for r in expected]),'status':'passed_exact_index_partition','request_id':m['request_id'],'raw_ref':m['raw_ref'],'sha256':m['sha256'],'retrieved_at_utc':m['retrieved_at_utc']}
    futures=[];pool=concurrent.futures.ThreadPoolExecutor(max_workers=4)
    try:
        futures=[pool.submit(fetch,o) for o in range(0,len(index),100) if o//100+1 not in done]
        for future in concurrent.futures.as_completed(futures):
            row=future.result()
            if row:
                ledger.append(row);ledger.sort(key=lambda r:int(r['partition']));write_csv(path,ledger);done.add(int(row['partition']))
                print('VIBE_PARTITIONS',len(done),'of',(len(index)+99)//100,'transactions',sum(int(r['rows']) for r in ledger),flush=True)
    except BaseException:
        stop.set()
        for future in futures:future.cancel()
        raise
    finally:pool.shutdown(wait=True,cancel_futures=True)
    if len(done)!=(len(index)+99)//100:raise RuntimeError('Incomplete Vibe partitions')
    receipt={'status':'passed_complete_cross_source_candidate_set','full_transactions':len(index),'successful_transaction_candidates':sum(json.loads(r['err_json']) is None for r in index),'failed_transactions_excluded':sum(json.loads(r['err_json']) is not None for r in index),'pages':len(done),'missing_from_Vibe':0,'extra_from_Vibe':0,'partition_order_and_execution_error_exactly_equal_to_official_index':True,'authority':AUTHORITY,'public_no_auth_documentation':'https://docs.solanavibestation.com/api-reference/historical/gettransactionsforaddress.md','rate_policy':'four in-flight public reads; global starts>=.31s apart;<=3.3 individual RPC/s, below5RPS; global Retry-After;100 returned rows is documented method pagination, not a batch of100 calls','status_filter_anomaly':'status=success probe returned failed transactions; no server status filter used; native meta.err reconciled exactly','full_transaction_admission':'not automatic: selected instructions must match native discriminator, call-tree location and SQD committed status','completed_at_utc':now()}
    write_json(ROOT/'reports/vibe_history_receipt.json',receipt);print(json.dumps(receipt),flush=True)
if __name__=='__main__':run()
