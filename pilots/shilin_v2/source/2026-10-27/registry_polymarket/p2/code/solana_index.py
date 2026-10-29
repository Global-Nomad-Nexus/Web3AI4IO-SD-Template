"""Independent complete-day transaction index via the mandatory creation PDA.

Index rows are candidates, NEVER automatically admitted creation records.
"""
from p2io import *
from decode import b58decode,b58encode
import hashlib

AUTHORITY='TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
PROGRAM='6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
def run():
    c=Client(budget=100);legacy=read_csv(PARENT/'processed/registry.csv')
    anchor=min([r for r in legacy if epoch(r['created_at_utc'])>=1791504000],key=lambda r:r['created_at_utc'])
    seed=b'mint-authority';matches=[b for b in range(255,-1,-1) if hashlib.sha256(seed+bytes([b])+b58decode(PROGRAM)+b'ProgramDerivedAddress').digest()==b58decode(AUTHORITY)]
    if len(matches)!=1:raise RuntimeError('Mandatory PDA does not match seed/program')
    idl=json.loads((ROOT/'configs/pump_8cda1fa30ea658b20909d8aedf002047119388d2.json').read_text())
    using=[i['name'] for i in idl['instructions'] if any(a.get('name')=='mint_authority' for a in i['accounts'])]
    if set(using)!={'create','create_v2'}:raise RuntimeError('Review mandatory-account selector before widening scope')
    cursor=anchor['creation_tx_hash_or_signature'];seen=set();pages=[];candidates=[];excluded=[];complete=False
    for page_number in range(100):
        rows,m=c.rpc('https://api.mainnet.solana.com','getSignaturesForAddress',[AUTHORITY,{'before':cursor,'limit':1000,'commitment':'finalized'}],'mandatory_create_account_window_index')
        if not isinstance(rows,list) or not m['ok']:raise RuntimeError('Native account index failed: '+m['error'])
        if not rows:raise RuntimeError('Empty page before reaching old time boundary; index completeness unproved')
        if any(r.get('blockTime') is None for r in rows):raise RuntimeError('Index row time unknown; cannot silently filter')
        slots=[r['slot'] for r in rows]
        if slots!=sorted(slots,reverse=True):raise RuntimeError('Nonmonotone native index page')
        if any(r['signature'] in seen for r in rows):raise RuntimeError('Repeated signature across native index pages')
        seen.update(r['signature'] for r in rows)
        for r in rows:
            if 1791417600<=r['blockTime']<1791504000:
                row={'signature':r['signature'],'slot':r['slot'],'block_time_utc':iso(r['blockTime']),'transaction_index_native':r.get('transactionIndex',''),'err_json':json.dumps(r['err']),'confirmation_status':r['confirmationStatus'],'page_request_id':m['request_id'],'page_raw_ref':m['raw_ref']}
                if r['err'] is None:candidates.append(row)
                else:excluded.append(row)
        pages.append({'page':page_number+1,'before_signature':cursor,'first_signature':rows[0]['signature'],'last_signature':rows[-1]['signature'],'first_time_utc':iso(rows[0]['blockTime']),'last_time_utc':iso(rows[-1]['blockTime']),'rows':len(rows),'request_id':m['request_id'],'raw_ref':m['raw_ref'],'sha256':m['sha256']})
        write_csv(ROOT/'reports/solana_native_index_pages.csv',pages)
        write_csv(ROOT/'reports/solana_native_creation_candidates.csv',candidates)
        write_csv(ROOT/'reports/solana_native_index_failed_transactions.csv',excluded,['signature','slot','block_time_utc','transaction_index_native','err_json','confirmation_status','page_request_id','page_raw_ref'])
        print('INDEX_PAGE',page_number+1,len(candidates),rows[-1]['slot'],iso(rows[-1]['blockTime']),flush=True)
        if rows[-1]['blockTime']<1791417600:complete=True;break
        cursor=rows[-1]['signature']
    write_json(ROOT/'reports/solana_native_index_receipt.json',{'status':'index_pagination_complete' if complete else 'partial','start_utc':'2026-10-08T00:00:00Z','end_utc':'2026-10-09T00:00:00Z','anchor_after_end_utc':anchor['created_at_utc'],'anchor_signature':anchor['creation_tx_hash_or_signature'],'authority':AUTHORITY,'program':PROGRAM,'PDA_seed_utf8':'mint-authority','PDA_bump':matches[0],'IDL_creation_instructions_using_authority':using,'IDL_sha256':sha(ROOT/'configs/pump_8cda1fa30ea658b20909d8aedf002047119388d2.json'),'successful_transaction_candidates':len(candidates),'failed_transaction_candidates':len(excluded),'pages':len(pages),'native_transaction_decoding':'not_yet_done;candidate_count_is_not_creation_count','access':'official_public_RPC_no_auth'})
    if not complete:raise RuntimeError('Native index page budget reached before start boundary')
if __name__=='__main__':run()
