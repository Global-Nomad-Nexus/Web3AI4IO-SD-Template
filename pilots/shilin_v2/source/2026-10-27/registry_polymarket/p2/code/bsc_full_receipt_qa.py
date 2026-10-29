"""Check every admitted BSC creation against native receipt and block header."""
from p2io import *
from decode import exact_evm

def run():
    c=Client(budget=1000);rows=[r for r in read_csv(ROOT/'processed/registry.csv') if r['chain_key']=='eip155:56']
    version=next(v for v in json.loads((ROOT/'configs/platform_events.json').read_text()) if v['chain_key']=='eip155:56')
    calls=[('receipt',s) for s in sorted({r['creation_tx_hash_or_signature'] for r in rows})]+[('header',s) for s in sorted({r['block_height_or_slot'] for r in rows},key=int)]
    receipts={};headers={};refs={}
    for offset in range(0,len(calls),20):
        batch=calls[offset:offset+20]
        payload=[{'jsonrpc':'2.0','id':i,'method':'eth_getTransactionReceipt' if kind=='receipt' else 'eth_getBlockByNumber','params':[key] if kind=='receipt' else [hex(int(key)),False]} for i,(kind,key) in enumerate(batch)]
        data,m=c.json('https://bsc-dataseed.bnbchain.org',payload,'BSC_all_creation_native_receipt_header_QA')
        if not m['ok'] or not isinstance(data,list):raise RuntimeError('BSC native batch failed: '+m['error'])
        byid={x.get('id'):x for x in data}
        if len(byid)!=len(batch):raise RuntimeError('BSC batch identity mismatch')
        for i,(kind,key) in enumerate(batch):
            result=byid[i].get('result')
            if result is None or byid[i].get('error'):raise RuntimeError('BSC batch result missing: '+str(byid[i].get('error')))
            (receipts if kind=='receipt' else headers)[key]=result;refs[(kind,key)]=m['raw_ref']
        print('BSC_FULL_QA_BATCH',min(offset+20,len(calls)),len(calls),flush=True)
        time.sleep(.3)
    out=[]
    for r in rows:
        sig=r['creation_tx_hash_or_signature'];rc=receipts[sig];h=headers[r['block_height_or_slot']];checks={};error=''
        try:
            logs=[l for l in rc['logs'] if int(l['logIndex'],16)==int(r['log_index']) and l['address'].lower()==r['program_or_factory_address'] and l['topics'][0]==version['topic0']]
            if len(logs)!=1:raise ValueError('Creation log not uniquely present in native receipt')
            l=logs[0];args=exact_evm(version['event_abi'],l['topics'],l['data'])
            checks={'receipt_success':rc['status']=='0x1','tx_identity':rc['transactionHash']==sig,'block_height':str(int(rc['blockNumber'],16))==r['block_height_or_slot'],'block_hash':rc['blockHash']==h['hash']==r['block_hash'],'block_time':iso(int(h['timestamp'],16))==r['created_at_utc'],'transaction_index':str(int(rc['transactionIndex'],16))==r['transaction_index'],'sender':rc['from'].lower()==r['tx_sender_or_signer'].lower(),'not_removed':not l.get('removed',False),'mint':args['token'].lower()==r['token_address_canonical'],'creator':args['creator'].lower()==r['creator_address'].lower(),'complete_event_fields':args==json.loads(r['initial_attributes_json'])}
        except Exception as e:error=type(e).__name__+': '+str(e)
        out.append({'creation_event_id':r['creation_event_id'],'token_id':r['token_id'],'status':'passed' if checks and all(checks.values()) and not error else 'failed','checks_json':json.dumps(checks,sort_keys=True),'error':error,'receipt_raw_ref':refs[('receipt',sig)],'header_raw_ref':refs[('header',r['block_height_or_slot'])]})
    write_csv(ROOT/'reports/bsc_all_native_QA.csv',out)
    report={'status':'passed' if all(r['status']=='passed' for r in out) and out else 'failed','creation_logs_checked':len(out),'native_receipts':len(receipts),'native_headers':len(headers),'failures':sum(r['status']!='passed' for r in out),'cohort_event_ids_hash':sid(sorted(r['creation_event_id'] for r in rows)),'all_creation_fields_checked':True,'completed_at_utc':now()}
    write_json(ROOT/'reports/bsc_all_native_QA_receipt.json',report);print(json.dumps(report),flush=True)
    if report['status']!='passed':raise RuntimeError('Native BSC creation conflicts require review')
if __name__=='__main__':run()
