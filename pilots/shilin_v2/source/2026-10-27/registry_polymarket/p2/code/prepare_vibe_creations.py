"""Zero-network native creation decode with independent header evidence.

Unknown inner commitments require explicit saved SQD instruction-state evidence.
An index row alone is never admitted as a creation.
"""
from p2io import *
from native_call_tree import native_creations,PROGRAM
from decode import pump_args
from collections import Counter

def archive_evidence():
    records={}
    for path in [ROOT/'reports/query_ledger_solana_mainnet.csv',ROOT/'reports/solana_light_query_ledger.csv',ROOT/'reports/solana_targeted_state_queries.csv']:
        if not path.exists():continue
        for seg in read_csv(path):
            if seg['status']!='complete_segment':continue
            if sha(ROOT/seg['raw_ref'])!=seg['raw_sha256']:raise RuntimeError('Archive raw hash conflict')
            for b in blocks(read_body(ROOT/seg['raw_ref'])):
                txs={t['transactionIndex']:t for t in b.get('transactions',[])}
                for i in b.get('instructions',[]):
                    tx=txs[i['transactionIndex']];key=(tx['signatures'][0],tuple(i['instructionAddress']));v={'item':i,'err':tx['err'],'header':b['header'],'raw_ref':seg['raw_ref']}
                    old=records.get(key)
                    if old and (old['item']['isCommitted']!=i['isCommitted'] or old['header']!=b['header']):raise RuntimeError('Conflicting archive event evidence')
                    if not old or 'data' in i:records[key]=v
    return records

def run():
    receipt=json.loads((ROOT/'reports/vibe_history_receipt.json').read_text())
    if receipt['status']!='passed_complete_cross_source_candidate_set':raise RuntimeError('Full cross-source transaction set required')
    headers={int(r['number']):r for r in read_csv(ROOT/'data/solana_header_sources.csv')};archive=archive_evidence();segments=[];unknown=[];conflicts=[];decoding=[];candidate_status=[];admitted=excluded=compared=0
    for page in read_csv(ROOT/'reports/vibe_history_partitions.csv'):
        path=ROOT/page['raw_ref']
        if sha(path)!=page['sha256']:raise RuntimeError('Native page hash conflict')
        data=json.loads(read_body(path))['result']['data'];envelopes=[]
        for tx in data:
            sig=tx['transaction']['signatures'][0];slot=tx['slot'];h=headers[slot]
            if int(h['timestamp'])!=tx['blockTime']:raise RuntimeError('Native transaction/header timestamp conflict')
            try:instructions=native_creations(tx)
            except Exception as e:decoding.append({'signature':sig,'slot':slot,'raw_ref':page['raw_ref'],'error':str(e)});continue
            count=0
            for item in instructions:
                key=(sig,tuple(item['instructionAddress']));old=archive.get(key)
                if old:
                    expected=old['item']['isCommitted'] is True and old['item'].get('error') is None and old['err'] is None
                    if old['header']['hash']!=h['hash'] or old['header']['timestamp']!=tx['blockTime']:conflicts.append({'signature':sig,'path':str(key[1]),'reason':'block_header_conflict'})
                    if old['item']['transactionIndex']!=tx['transactionIndex']:conflicts.append({'signature':sig,'path':str(key[1]),'reason':'native_transaction_index_conflict'})
                    for field in ['accounts','data']:
                        if field in old['item'] and old['item'][field]!=item[field]:conflicts.append({'signature':sig,'path':str(key[1]),'reason':field+'_conflict'})
                    if item['isCommitted'] is not None and item['isCommitted']!=expected:conflicts.append({'signature':sig,'path':str(key[1]),'reason':'commitment_conflict'})
                    if item['isCommitted'] is None:item['isCommitted']=expected;item['error']=old['item'].get('error');item['commitment_evidence_rule']='saved_independent_SQD_instruction_state'
                    item['instruction_commitment_evidence_ref']=old['raw_ref'];compared+=1
                else:item['instruction_commitment_evidence_ref']=page['raw_ref']
                if item['isCommitted'] is None:unknown.append({'signature':sig,'slot':slot,'instruction_path':json.dumps(item['instructionAddress'],separators=(',',':')),'native_raw_ref':page['raw_ref'],'reason':item['commitment_evidence_rule']});continue
                if item['isCommitted']:
                    args=pump_args(item['data'])
                    if item['accounts'][1]!='TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM':raise RuntimeError('Qualified native creation violates frozen mandatory PDA')
                    count+=1;admitted+=1
                else:excluded+=1
            candidate_status.append({'signature':sig,'slot':slot,'native_tx_status':'success' if tx['meta']['err'] is None else 'failed_atomic_transaction','qualified_committed_creations':count,'recognized_create_instructions':len(instructions),'raw_ref':page['raw_ref']})
            msg=tx['transaction']['message'];key0=msg['accountKeys'][0];fee_payer=key0['pubkey'] if isinstance(key0,dict) else key0
            envelopes.append({'header':{'number':slot,'hash':h['hash'],'timestamp':tx['blockTime']},'transactions':[{'transactionIndex':tx['transactionIndex'],'signatures':[sig],'err':tx['meta']['err'],'feePayer':fee_payer,'version':tx.get('version',''),'receipt_raw_ref':page['raw_ref']}],'instructions':[i for i in instructions if i['isCommitted'] is not None],'header_raw_ref':h['source_raw_ref'],'native_source':'Vibe_public_RPC+independent_block_header_source'})
        norm=ROOT/'data'/('vibe_creation_page_'+str(page['partition']).zfill(4)+'.ndjson');norm.write_text(''.join(json.dumps(b,ensure_ascii=False,separators=(',',':'))+'\n' for b in envelopes))
        segments.append({'chain_key':'solana:mainnet','status':'complete_segment','returned_block_rows':len(envelopes),'raw_ref':str(norm.relative_to(ROOT)),'raw_sha256':sha(norm),'retrieved_at_utc':page['retrieved_at_utc'],'request_id':page['request_id'],'source_page_raw_ref':page['raw_ref'],'enumeration_unit':'mandatory_creation_PDA_index_transaction_page'})
    write_csv(ROOT/'reports/vibe_creation_segments.csv',segments)
    write_csv(ROOT/'reports/solana_unresolved_commitments.csv',unknown,['signature','slot','instruction_path','native_raw_ref','reason']);write_csv(ROOT/'reports/solana_native_archive_conflicts.csv',conflicts,['signature','path','reason']);write_csv(ROOT/'reports/solana_native_decode_errors.csv',decoding,['signature','slot','raw_ref','error']);write_csv(ROOT/'reports/solana_candidate_resolution.csv',candidate_status)
    report={'status':'passed_complete_native_creation_resolution' if not unknown and not conflicts and not decoding else 'pending_or_conflicting_native_evidence','full_native_transactions':len(candidate_status),'successful_transaction_candidates':sum(r['native_tx_status']=='success' for r in candidate_status),'committed_creation_instructions':admitted,'excluded_recognized_failed_or_rolled_back_instructions':excluded,'successful_candidates_without_committed_creation':sum(r['native_tx_status']=='success' and not r['qualified_committed_creations'] for r in candidate_status),'unknown_commitment_instructions':len(unknown),'archive_native_instruction_comparisons':compared,'conflicts':len(conflicts),'decode_errors':len(decoding),'coverage_method':'complete mandatory PDA transaction index; every native transaction resolved; exact frozen program/discriminators; all block times/hashes sourced; no claim of a completed all-slot SQD scan','completed_at_utc':now()};write_json(ROOT/'reports/solana_native_creation_receipt.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':run()
