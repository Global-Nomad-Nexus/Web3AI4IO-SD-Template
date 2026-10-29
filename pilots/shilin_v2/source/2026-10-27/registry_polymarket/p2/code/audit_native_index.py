"""Independent native index/creation comparison, never an index-to-creation cast."""
from p2io import *
from collections import Counter

def run():
    receipt=json.loads((ROOT/'reports/solana_native_index_receipt.json').read_text())
    pages=read_csv(ROOT/'reports/solana_native_index_pages.csv');candidates=read_csv(ROOT/'reports/solana_native_creation_candidates.csv');failed=read_csv(ROOT/'reports/solana_native_index_failed_transactions.csv')
    all_seen=set();errors=[];recovered=[];recovered_failed=[];previous_last=None
    for p in pages:
        path=ROOT/p['raw_ref']
        if sha(path)!=p['sha256']:errors.append('page_hash:'+p['page'])
        m=json.loads(path.read_text());data=m['result']
        if previous_last is not None and p['before_signature']!=previous_last:errors.append('page_cursor:'+p['page'])
        previous_last=data[-1]['signature']
        if data[0]['signature']!=p['first_signature'] or data[-1]['signature']!=p['last_signature']:errors.append('page_endpoint:'+p['page'])
        for r in data:
            if r['signature'] in all_seen:errors.append('duplicate_signature:'+r['signature'])
            all_seen.add(r['signature'])
            if r['blockTime'] is not None and 1791417600<=r['blockTime']<1791504000:
                (recovered if r['err'] is None else recovered_failed).append(r['signature'])
    if set(recovered)!={r['signature'] for r in candidates}:errors.append('successful_candidate_export_differs')
    if set(recovered_failed)!={r['signature'] for r in failed}:errors.append('failed_candidate_export_differs')
    final_data=json.loads((ROOT/pages[-1]['raw_ref']).read_text())['result']
    bounds=json.loads((ROOT/'configs/pilot_protocol.json').read_text())['chain_bounds_inclusive_start_exclusive_end']['solana:mainnet']
    if final_data[-1]['slot']>=bounds[0] or receipt['status']!='index_pagination_complete':errors.append('start_boundary_not_crossed')
    if epoch(receipt['anchor_after_end_utc'])<1791504000:errors.append('anchor_not_after_window')
    events=[r for r in read_csv(ROOT/'processed/creation_events.csv') if r['chain_key']=='solana:mainnet'];event_signatures={r['creation_tx_hash_or_signature'] for r in events};index={r['signature']:r for r in candidates}
    for r in events:
        ix=index.get(r['creation_tx_hash_or_signature'])
        if ix is None:errors.append('creation_not_in_successful_index:'+r['creation_event_id'])
        elif ix['slot']!=r['block_height_or_slot'] or ix['block_time_utc']!=r['created_at_utc'] or ix['transaction_index_native']!=r['transaction_index']:errors.append('index_native_locator_conflict:'+r['creation_event_id'])
    segments=[(int(r['from_block']),int(r['scanned_through'])) for r in read_csv(ROOT/'reports/query_ledger_solana_mainnet.csv') if r['status']=='complete_segment']
    native_receipt=ROOT/'reports/solana_native_creation_receipt.json'
    native_complete=native_receipt.exists() and json.loads(native_receipt.read_text())['status']=='passed_complete_native_creation_resolution'
    resolved={r['signature']:r for r in read_csv(ROOT/'reports/solana_candidate_resolution.csv')} if native_complete else {}
    unresolved=[];noncreation=[]
    for r in candidates:
        if r['signature'] in event_signatures:continue
        covered=any(a<=int(r['slot'])<=b for a,b in segments) or r['signature'] in resolved
        item={**r,'status':'full_native_transaction_resolved_no_committed_create' if r['signature'] in resolved else ('fully_scanned_slot_no_admitted_qualified_creation' if covered else 'archive_slot_not_yet_scanned'),'warning':'A successful transaction mentioning the authority is not automatically a creation.'}
        (noncreation if covered else unresolved).append(item)
    write_csv(ROOT/'reports/solana_index_noncreation_candidates.csv',noncreation,list(candidates[0])+['status','warning'])
    write_csv(ROOT/'reports/solana_index_pending_candidates.csv',unresolved,list(candidates[0])+['status','warning'])
    write_json(ROOT/'reports/solana_index_crosscheck.json',{'status':'passed' if not errors else 'failed','errors':errors,'successful_index_candidates':len(candidates),'failed_index_candidates_excluded':len(failed),'native_qualified_creation_events':len(events),'distinct_creation_transactions':len(event_signatures),'index_candidates_no_qualified_creation_in_fully_scanned_slot':len(noncreation),'index_candidates_not_yet_in_scanned_slots':len(unresolved),'candidate_pagination_complete':True,'not_a_primary_coverage_substitute':True,'checked_at_utc':now()})
    print(json.dumps({'status':'passed' if not errors else 'failed','errors':len(errors),'pending_candidates':len(unresolved),'noncreation_candidates':len(noncreation)}),flush=True)
if __name__=='__main__':run()
