"""Native RPC candidate resolution; never infer a creation from an index row.

One batch contains <=30 calls per method and starts >=8.2s apart: <40
calls per method/10s and <100 total/10s, counting every batch element.
"""
from p2io import *
from decode import b58decode,pump_args
from collections import Counter
import re

PROGRAM='6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
URL='https://api.mainnet.solana.com'

def normalize(tx,block,candidate,tx_ref,block_ref):
    if tx['meta']['err'] is not None:raise ValueError('Successful index candidate has failed native transaction')
    if tx['slot']!=int(candidate['slot']) or iso(tx['blockTime'])!=candidate['block_time_utc']:raise ValueError('Index/native slot or timestamp conflict')
    if block['blockTime']!=tx['blockTime']:raise ValueError('Native block and transaction time conflict')
    msg=tx['transaction']['message'];sig=tx['transaction']['signatures'][0]
    if sig!=candidate['signature']:raise ValueError('Native signature conflict')
    keys=[a['pubkey'] if isinstance(a,dict) else a for a in msg['accountKeys']]
    def instruction(i,path):
        program=i.get('programId',keys[i['programIdIndex']] if 'programIdIndex' in i else '')
        return {'programId':program,'accounts':[keys[a] if isinstance(a,int) else a for a in i.get('accounts',[])],'data':i.get('data',''),'instructionAddress':path,'transactionIndex':int(candidate['transaction_index_native'])}
    by_outer={g['index']:g['instructions'] for g in tx['meta'].get('innerInstructions',[])}
    instructions=[]
    for outer,i in enumerate(msg['instructions']):
        instructions.append(instruction(i,[outer]));stack=[[outer]];counts=Counter()
        for j in by_outer.get(outer,[]):
            height=j.get('stackHeight')
            if not isinstance(height,int) or height<2:raise ValueError('Missing native inner stackHeight')
            while len(stack)>=height:stack.pop()
            if len(stack)!=height-1:raise ValueError('Invalid native stackHeight transition')
            parent=tuple(stack[-1]);child=counts[parent];counts[parent]+=1;path=list(parent)+[child]
            instructions.append(instruction(j,path));stack.append(path)
    # Reconstruct invocation outcomes independently of the selected discriminator.
    # A successful child of a failed ancestor is rolled back and is not committed.
    traces=[];stack=[]
    for line in tx['meta'].get('logMessages',[]) or []:
        m=re.fullmatch(r'Program (\S+) invoke \[(\d+)\]',line)
        if m:
            height=int(m[2])
            if len(stack)!=height-1:raise ValueError('Incomplete native invocation logs')
            node={'program':m[1],'height':height,'ok':None,'ancestors':list(stack)};traces.append(node);stack.append(node);continue
        m=re.fullmatch(r'Program (\S+) (success|failed: .*)',line)
        if m:
            if not stack or stack[-1]['program']!=m[1]:raise ValueError('Unbalanced native invocation outcome')
            stack.pop()['ok']=m[2]=='success'
    if stack:raise ValueError('Truncated invocation outcome logs')
    pump_ix=[i for i in instructions if i['programId']==PROGRAM]
    pump_traces=[n for n in traces if n['program']==PROGRAM]
    if len(pump_ix)!=len(pump_traces):raise ValueError('Pump instruction/log invocation count mismatch')
    selected=[]
    for i,n in zip(pump_ix,pump_traces):
        if len(i['instructionAddress'])!=n['height']:raise ValueError('Pump instruction/log depth mismatch')
        raw=b58decode(i['data']) if i['data'] else b''
        if raw[:8].hex() not in ['181ec828051c0777','d6904cec5f8b31b4']:continue
        pump_args(i['data']) # Fail closed on malformed recognized creation prefix.
        i['isCommitted']=n['ok'] is True and all(a['ok'] is True for a in n['ancestors'])
        i['error']=None if n['ok'] is True else 'native_invocation_failed'
        selected.append(i)
    if not selected:resolution='resolved_no_qualified_create_instruction'
    elif all(not i['isCommitted'] for i in selected):resolution='resolved_only_rolled_back_create_instructions'
    else:resolution='resolved_committed_creations'
    ti=int(candidate['transaction_index_native'])
    envelope={'header':{'number':tx['slot'],'hash':block['blockhash'],'timestamp':tx['blockTime']},'transactions':[{'transactionIndex':ti,'signatures':[sig],'err':None,'feePayer':keys[0],'version':tx.get('version',''),'receipt_raw_ref':tx_ref}],'instructions':selected,'header_raw_ref':block_ref,'native_source':'Solana_native_public_RPC'}
    return envelope,resolution

def archive_intervals():
    path=ROOT/'reports/query_ledger_solana_mainnet.csv'
    return [(int(r['from_block']),int(r['scanned_through'])) for r in read_csv(path) if r['status']=='complete_segment']

def run(batch_size=30):
    index=json.loads((ROOT/'reports/solana_native_index_receipt.json').read_text())
    if index['status']!='index_pagination_complete':raise RuntimeError('Complete native account index required')
    candidates=read_csv(ROOT/'reports/solana_native_creation_candidates.csv')
    if any(not r['transaction_index_native'] for r in candidates):raise RuntimeError('Native index lacks transaction order; resolve from full block before proceeding')
    ledger_path=ROOT/'reports/solana_native_resolution.csv';ledger=read_csv(ledger_path) if ledger_path.exists() else []
    done={r['signature'] for r in ledger if r['status']=='resolved'};c=Client(budget=2500);last_batch=0
    while True:
        intervals=archive_intervals()
        remaining=[r for r in candidates if r['signature'] not in done and not any(a<=int(r['slot'])<=b for a,b in intervals)]
        if not remaining:break
        batch=remaining[:batch_size];slots=list(dict.fromkeys(int(r['slot']) for r in batch))
        time.sleep(max(0,8.2-(time.monotonic()-last_batch)));last_batch=time.monotonic()
        payload=[{'jsonrpc':'2.0','id':'tx:'+r['signature'],'method':'getTransaction','params':[r['signature'],{'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1}]} for r in batch]
        payload += [{'jsonrpc':'2.0','id':'block:'+str(slot),'method':'getBlock','params':[slot,{'commitment':'finalized','transactionDetails':'none','rewards':False,'maxSupportedTransactionVersion':1}]} for slot in slots]
        values,m=c.json(URL,payload,'mandatory_candidate_native_tx_and_header_batch')
        if not m['ok'] or not isinstance(values,list):raise RuntimeError('Native resolution batch failed: '+m['error'])
        ids=[r.get('id') for r in values]
        if len(ids)!=len(set(ids)) or set(ids)!={q['id'] for q in payload}:raise RuntimeError('Native batch response identity incomplete')
        results={r['id']:r for r in values};normalized=[];out=[]
        for r in batch:
            try:
                tx=results['tx:'+r['signature']];block=results['block:'+r['slot']]
                if tx.get('error') or block.get('error') or tx.get('result') is None or block.get('result') is None:raise ValueError('Native batch missing result: '+str(tx.get('error') or block.get('error')))
                envelope,resolution=normalize(tx['result'],block['result'],r,m['raw_ref'],m['raw_ref']);normalized.append(envelope)
                row={'signature':r['signature'],'slot':r['slot'],'status':'resolved','resolution':resolution,'committed_creations':sum(i['isCommitted'] for i in envelope['instructions']),'error':''}
            except Exception as e:row={'signature':r['signature'],'slot':r['slot'],'status':'unresolved','resolution':'','committed_creations':'','error':type(e).__name__+': '+str(e)}
            row.update(request_id=m['request_id'],raw_ref=m['raw_ref'],raw_sha256=m['sha256'],retrieved_at_utc=m['retrieved_at_utc']);out.append(row)
        np=ROOT/'raw'/('solana_normalized_'+m['request_id']+'.ndjson');np.write_text(''.join(json.dumps(b,ensure_ascii=False,separators=(',',':'))+'\n' for b in normalized))
        for row in out:row.update(normalized_ref=str(np.relative_to(ROOT)),normalized_sha256=sha(np))
        ledger.extend(out);write_csv(ledger_path,ledger);done.update(r['signature'] for r in out if r['status']=='resolved')
        print('NATIVE_RESOLUTION',len(done),'remaining',len(remaining)-len(batch),'batch_errors',sum(r['status']!='resolved' for r in out),flush=True)
        if any(r['status']!='resolved' for r in out):raise RuntimeError('Unresolved native candidate; inspect persisted evidence before resuming')
    write_json(ROOT/'reports/solana_native_resolution_receipt.json',{'status':'all_successful_candidates_resolved_by_native_or_closed_archive','index_candidates':len(candidates),'native_resolved_transactions':len(done),'archive_candidate_transactions':len(candidates)-len(done),'enumeration_unit':'fully paginated mandatory-account transaction index; each candidate resolved by native transaction/header or fully closed archive slot range','slot_scan_claim':False,'native_resolution_ledger':'reports/solana_native_resolution.csv','completed_at_utc':now()})
if __name__=='__main__':run()
