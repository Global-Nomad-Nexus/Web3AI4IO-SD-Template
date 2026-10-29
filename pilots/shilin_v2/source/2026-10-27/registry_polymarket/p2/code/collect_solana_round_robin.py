"""One HTTP request at a time, round-robin unresolved disjoint intervals.

After overload, wait the global Retry-After before any other request. This
changes scheduling only, not access identity, quotas, filters or the cohort.
"""
from p2io import *
from collect import query_for
import copy

def run():
    cfg=json.loads((ROOT/'configs/pilot_protocol.json').read_text());start,end=cfg['chain_bounds_inclusive_start_exclusive_end']['solana:mainnet'];path=ROOT/'reports/query_ledger_solana_mainnet.csv'
    ledger=read_csv(path);c=Client(budget=3000);template=query_for('solana:mainnet',[]);url='https://portal.sqd.dev/datasets/solana-mainnet/finalized-stream'
    def cursor_for(a,b):
        current=a
        for s in sorted((r for r in ledger if r['status']=='complete_segment'),key=lambda r:int(r['from_block'])):
            if int(s['from_block'])<=current<=int(s['scanned_through']):current=int(s['scanned_through'])+1
        return min(current,b)
    partitions=[(a,min(end,a+20000)) for a in range(start,end,20000)]
    while True:
        pending=[(a,b,cursor_for(a,b)) for a,b in partitions if cursor_for(a,b)<b]
        if not pending:break
        for a,b,current in pending:
            # Re-evaluate after a neighboring partition may have closed a tail.
            current=cursor_for(a,b)
            if current>=b:continue
            query_end=min(b-1,current+511);q={**copy.deepcopy(template),'fromBlock':current,'toBlock':query_end}
            body,m=c.once(url,q,'whole_window_native_creation_filter_round_robin')
            row={'chain_key':'solana:mainnet','from_block':current,'query_to_block':query_end,'scanned_through':'','status':'request_failed','returned_block_rows':0,'returned_creation_candidates':0,'request_id':m['request_id'],'raw_ref':m['raw_ref'],'raw_sha256':m['sha256'],'retrieved_at_utc':m['retrieved_at_utc'],'filter_sha256':sid(template),'error':m['error']}
            if m['ok']:
                data=blocks(body)
                if data:
                    numbers=[x['header']['number'] for x in data]
                    if numbers!=sorted(set(numbers)) or numbers[0]<current or numbers[-1]>query_end:raise RuntimeError('Invalid stream ordering/bounds')
                    row.update(scanned_through=numbers[-1],status='complete_segment',returned_block_rows=len(data),returned_creation_candidates=sum(len(x.get('instructions',[])) for x in data))
                else:
                    produced,rm=c.rpc('https://api.mainnet.solana.com','getBlocks',[current,query_end,{'commitment':'finalized'}],'verify_empty_exact_slot_query_tail')
                    if produced==[]:row.update(scanned_through=query_end,status='complete_segment',error='All requested slots independently verified skipped; '+rm['raw_ref'])
                    else:raise RuntimeError('Empty archive response has unproved coverage')
            ledger.append(row);write_csv(path,ledger)
            print('ROUND_ROBIN',current,query_end,row['status'],row['scanned_through'],row['returned_creation_candidates'],flush=True)
            if not m['ok']:
                try:err=json.loads(body).get('error',{})
                except (ValueError,UnicodeDecodeError):err={}
                if err.get('type') in ['invalid_request_error','api_error'] or m['http_status'] in [401,403,400]:raise RuntimeError('Non-retryable source error; persisted for diagnosis')
                if m['http_status'] not in [None,429,502,503,504,529]:raise RuntimeError('Unexpected source failure')
                headers={k.lower():v for k,v in m['response_headers'].items()};delay=max(10,float(headers.get('retry-after','0')))
                print('GLOBAL_SOURCE_BACKOFF',delay,flush=True);time.sleep(delay)
    write_json(ROOT/'reports/solana_full_collection_receipt.json',{'status':'frozen_full_slot_interval_closed','start_inclusive':start,'end_exclusive':end,'actual_network_calls_this_invocation':c.calls,'completed_at_utc':now(),'scheduling':'single HTTP request at a time, rotate disjoint unfinished partitions, global Retry-After honored','filter_sha256':sid(template)})
    print('SOLANA_FULL_WINDOW_CLOSED',flush=True)
if __name__=='__main__':run()
