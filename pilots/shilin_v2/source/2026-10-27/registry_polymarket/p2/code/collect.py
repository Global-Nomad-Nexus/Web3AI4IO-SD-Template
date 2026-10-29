"""Enumerate the frozen whole-day native creation queries with restartable ledger."""
from p2io import *
import argparse,copy

def query_for(chain,registry):
    if chain=='solana:mainnet':
        return {'type':'solana','fields':{'block':{'number':True,'hash':True,'timestamp':True},'instruction':{'programId':True,'accounts':True,'data':True,'isCommitted':True,'error':True,'instructionAddress':True,'transactionIndex':True},'transaction':{'transactionIndex':True,'signatures':True,'err':True,'feePayer':True,'version':True}},'instructions':[{'programId':['6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'],'d8':['0x181ec828051c0777','0xd6904cec5f8b31b4'],'transaction':True}]}
    filters=[{'address':[r['address']],'topic0':[r['topic0']],'transaction':True} for r in registry if r['chain_key']==chain]
    return {'type':'evm','fields':{'block':{'number':True,'hash':True,'timestamp':True},'log':{'address':True,'topics':True,'data':True,'logIndex':True,'transactionIndex':True,'transactionHash':True},'transaction':{'hash':True,'status':True,'from':True,'to':True,'transactionIndex':True}},'logs':filters}

def run(chains=None):
    config=json.loads((ROOT/'configs/pilot_protocol.json').read_text());registry=json.loads((ROOT/'configs/platform_events.json').read_text())
    c=Client(budget=500);ledger_path=ROOT/'reports'/('query_ledger_'+chains[0].replace(':','_')+'.csv' if chains and len(chains)==1 else 'query_ledger.csv')
    ledger=read_csv(ledger_path) if ledger_path.exists() else []
    endpoints={'solana:mainnet':'solana-mainnet','eip155:8453':'base-mainnet','eip155:56':'binance-mainnet'}
    for chain in chains or list(endpoints):
        start,end=config['chain_bounds_inclusive_start_exclusive_end'][chain];chunk=config['chunk_sizes'][chain]
        template=query_for(chain,registry);path=config.get('endpoint_path_by_chain',{}).get(chain,'stream');url='https://portal.sqd.dev/datasets/'+endpoints[chain]+'/'+path
        for chunk_start in range(start,end,chunk):
            chunk_end=min(end,chunk_start+chunk)-1;current=chunk_start
            while current<=chunk_end:
                done=next((r for r in ledger if r['chain_key']==chain and r['status']=='complete_segment' and int(r['from_block'])<=current<=int(r['scanned_through'])),None)
                if done:current=int(done['scanned_through'])+1;continue
                query_end=min(chunk_end,current+config.get('query_span_caps',{}).get(chain,chunk)-1)
                q={**copy.deepcopy(template),'fromBlock':current,'toBlock':query_end}
                b,m=c.request(url,q,'whole_window_native_creation_filter')
                row={'chain_key':chain,'from_block':current,'query_to_block':query_end,'scanned_through':'','status':'request_failed','returned_block_rows':0,'returned_creation_candidates':0,'request_id':m['request_id'],'raw_ref':m['raw_ref'],'raw_sha256':m['sha256'],'retrieved_at_utc':m['retrieved_at_utc'],'filter_sha256':sid(template),'error':m['error']}
                if m['ok']:
                    data=blocks(b)
                    if data:
                        heights=[x['header']['number'] for x in data]
                        if heights!=sorted(set(heights)) or heights[0]<current or heights[-1]>query_end:raise RuntimeError('Invalid stream ordering/bounds')
                        row.update(scanned_through=heights[-1],status='complete_segment',returned_block_rows=len(data),returned_creation_candidates=sum(len(x.get('instructions',x.get('logs',[]))) for x in data))
                    elif chain=='solana:mainnet':
                        remaining,rm=c.rpc('https://api.mainnet-beta.solana.com','getBlocks',[current,chunk_end,{'commitment':'finalized'}],'verify_empty_skipped_slot_tail')
                        if remaining==[]:row.update(scanned_through=chunk_end,status='complete_segment',error='Remaining slots independently verified skipped; '+rm['raw_ref'])
                ledger.append(row);write_csv(ledger_path,ledger)
                print(chain,current,chunk_end,row['status'],row['scanned_through'],row['returned_creation_candidates'],flush=True)
                if row['status']!='complete_segment':raise RuntimeError('Unresolved query segment; resume from recorded checkpoint after diagnosis')
                current=int(row['scanned_through'])+1
    write_json(ROOT/'reports/collection_receipt.json',{'completed_at_utc':now(),'status':'frozen_ranges_enumerated','actual_network_calls_this_invocation':c.calls,'segments':sum(r['status']=='complete_segment' for r in ledger),'source_scope':'single archive filtered enumeration; independent native RPC QA follows','no_claim':'not all platforms/all program versions or a trustless census'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--chain',action='append');run(p.parse_args().chain)
