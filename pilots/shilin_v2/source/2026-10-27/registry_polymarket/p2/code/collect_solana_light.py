"""Complement existing full responses with lighter, identical-filter queries.

Native argument bytes/accounts are resolved from separately retained SVS full
transactions. Keep archive commitment, instruction path, tx ID, block hash/time.
"""
from p2io import *
from collect import query_for
import copy

def run():
    cfg=json.loads((ROOT/'configs/pilot_protocol.json').read_text());start,end=cfg['chain_bounds_inclusive_start_exclusive_end']['solana:mainnet'];path=ROOT/'reports/solana_light_query_ledger.csv';ledger=read_csv(path) if path.exists() else [];full=read_csv(ROOT/'reports/query_ledger_solana_mainnet.csv');c=Client(budget=2000)
    template=query_for('solana:mainnet',[])
    for field in ['accounts','data']:template['fields']['instruction'].pop(field)
    def missing():
        cursor=start;gaps=[]
        for r in sorted([r for r in full+ledger if r['status']=='complete_segment'],key=lambda r:int(r['from_block'])):
            a=int(r['from_block']);b=int(r['scanned_through'])
            if a>cursor:gaps.append((cursor,a))
            cursor=max(cursor,b+1)
        if cursor<end:gaps.append((cursor,end))
        return gaps
    while True:
        gaps=missing()
        if not gaps:break
        a,b=gaps[0];z=min(b-1,a+511);q={**copy.deepcopy(template),'fromBlock':a,'toBlock':z}
        body,m=c.request('https://portal.sqd.dev/datasets/solana-mainnet/finalized-stream',q,'light_creation_locator_commitment_and_block_header')
        row={'chain_key':'solana:mainnet','from_block':a,'query_to_block':z,'scanned_through':'','status':'request_failed','returned_block_rows':0,'returned_creation_candidates':0,'request_id':m['request_id'],'raw_ref':m['raw_ref'],'raw_sha256':m['sha256'],'retrieved_at_utc':m['retrieved_at_utc'],'filter_sha256':sid(template),'error':m['error']}
        if m['ok']:
            data=blocks(body)
            if data:
                heights=[d['header']['number'] for d in data]
                if heights!=sorted(set(heights)) or heights[0]<a or heights[-1]>z:raise RuntimeError('Invalid light stream bounds')
                row.update(status='complete_segment',scanned_through=heights[-1],returned_block_rows=len(data),returned_creation_candidates=sum(len(d.get('instructions',[])) for d in data))
            else:
                slots,sm=c.rpc('https://api.mainnet.solana.com','getBlocks',[a,z,{'commitment':'finalized'}],'verify_empty_light_query_skipped_slots')
                if slots==[]:row.update(status='complete_segment',scanned_through=z,error='Independently skipped slot tail; '+sm['raw_ref'])
        ledger.append(row);write_csv(path,ledger);print('LIGHT_SEGMENT',a,z,row['status'],row['scanned_through'],row['returned_creation_candidates'],flush=True)
        if row['status']!='complete_segment':raise RuntimeError('Unresolved light query; resume saved checkpoint')
    write_json(ROOT/'reports/solana_light_collection_receipt.json',{'status':'full_window_query_union_closed_pending_native_argument_join','completed_at_utc':now(),'full_ledger':'reports/query_ledger_solana_mainnet.csv','complement_light_ledger':'reports/solana_light_query_ledger.csv','unchanged_selector':template['instructions'],'not_yet_an_admitted_creation_table':True})
    print('LIGHT_FULL_WINDOW_QUERY_UNION_CLOSED',flush=True)
if __name__=='__main__':run()
