"""Official public SVS full-transaction account-history pagination.

The official /historical/gettransactionsforaddress schema explicitly lists
the public, no-auth server.100 full transactions is its documented page max.
No batch-cost tricks: one method call/page, <=1 request/s, below free5RPS.
"""
from p2io import *
from solana_index import AUTHORITY

def run():
    c=Client(budget=900);path=ROOT/'reports/vibe_history_pages.csv';ledger=read_csv(path) if path.exists() else []
    if ledger and ledger[-1]['status']=='complete_final_page':print('VIBE_ALREADY_COMPLETE');return
    cursor=ledger[-1]['next_pagination_token'] if ledger else None;seen=set();successful=set();failed=set();previous=None;last_request=0
    for row in ledger:
        for r in json.loads(read_body(ROOT/row['raw_ref']))['result']['data']:
            sig=r['transaction']['signatures'][0];seen.add(sig);previous=(r['slot'],r['transactionIndex']);(successful if r['meta']['err'] is None else failed).add(sig)
    for page in range(len(ledger)+1,901):
        config={'transactionDetails':'full','sortOrder':'asc','limit':100,'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1,'filters':{'slot':{'gte':454377023,'lt':454698759},'blockTime':{'gte':1791417600,'lt':1791504000}}}
        if cursor:config['paginationToken']=cursor
        time.sleep(max(0,1-(time.monotonic()-last_request)));last_request=time.monotonic()
        result,m=c.rpc('https://public.rpc.solanavibestation.com/historical','getTransactionsForAddress',[AUTHORITY,config],'public_Vibe_full_history_page_capability')
        if not m['ok'] or not isinstance(result,dict) or not isinstance(result.get('data'),list):raise RuntimeError('Vibe page failed: '+m['error'])
        data=result['data'];next_cursor=result.get('paginationToken')
        for r in data:
            sig=r['transaction']['signatures'][0];position=(r['slot'],r['transactionIndex'])
            if sig in seen or previous is not None and position<=previous:raise RuntimeError('Duplicate/nonmonotone full-history page')
            if not 454377023<=r['slot']<454698759 or not 1791417600<=r['blockTime']<1791504000:raise RuntimeError('Source ignored frozen time/slot filters')
            seen.add(sig);previous=position;(successful if r['meta']['err'] is None else failed).add(sig)
        if next_cursor==cursor and next_cursor:raise RuntimeError('Pagination cursor did not advance')
        ledger.append({'page':page,'requested_pagination_token':cursor or '', 'next_pagination_token':next_cursor or '', 'rows':len(data),'first_slot':data[0]['slot'] if data else '', 'last_slot':data[-1]['slot'] if data else '', 'status':'complete_page' if next_cursor else 'complete_final_page','request_id':m['request_id'],'raw_ref':m['raw_ref'],'sha256':m['sha256'],'retrieved_at_utc':m['retrieved_at_utc']});write_csv(path,ledger)
        print('VIBE_PAGE',page,'transactions',len(seen),'last_slot',previous[0] if previous else None,flush=True)
        if not next_cursor:break
        cursor=next_cursor
    if ledger[-1]['status']!='complete_final_page':raise RuntimeError('Full-history page budget exhausted')
    native={r['signature'] for r in read_csv(ROOT/'reports/solana_native_creation_candidates.csv')};native_failed={r['signature'] for r in read_csv(ROOT/'reports/solana_native_index_failed_transactions.csv')};missing=(native-successful)|(native_failed-failed);extra=(successful-native)|(failed-native_failed)
    receipt={'status':'passed_complete_cross_source_candidate_set' if not missing and not extra else 'failed','full_transactions':len(seen),'successful_transaction_candidates':len(successful),'failed_transactions_excluded':len(failed),'pages':len(ledger),'official_RPC_index_successful_candidates':len(native),'official_RPC_index_failed_candidates':len(native_failed),'missing_from_Vibe':len(missing),'extra_from_Vibe':len(extra),'set_difference_signatures':sorted(missing|extra),'authority':AUTHORITY,'public_no_auth_documentation':'https://docs.solanavibestation.com/api-reference/historical/gettransactionsforaddress.md','rate_policy':'single individual call/page;100 records/page official maximum;<=1 HTTP request/s; free limit5RPS','primary_cohort_admission':'Only after actual create instruction decode and committed verification; index membership alone is not creation proof','status_filter_anomaly':'Probe status=success still returned failed transactions; omit server status filter, explicitly classify native meta.err on client and reconcile both sets.','completed_at_utc':now()}
    write_json(ROOT/'reports/vibe_history_receipt.json',receipt);print(json.dumps(receipt),flush=True)
    if receipt['status']!='passed_complete_cross_source_candidate_set':raise RuntimeError('Independent candidate sets differ')
if __name__=='__main__':run()
