"""Parameterised historical collectors; all progress persisted below a run root."""
from __future__ import annotations
from core import *
from native_decode import exact_evm, pump_args, b58decode
from native_call_tree import native_creations
from collections import Counter
from urllib.parse import urlencode

def check_pump_idl(idl):
    expected={'create':'181ec828051c0777','create_v2':'d6904cec5f8b31b4'}
    by_name={i['name']:i for i in idl['instructions']}
    for name,disc in expected.items():
        i=by_name[name]
        if bytes(i['discriminator']).hex()!=disc:raise Halt('Pump discriminator changed')
        if [a['name'] for a in i['accounts'][:2]]!=['mint','mint_authority']:raise Halt('Pump mandatory account layout changed')
        if [a['name'] for a in i['args'][:4]]!=['name','symbol','uri','creator']:raise Halt('Pump prefix arguments changed')
        if [a['type'] for a in i['args'][:3]]!=['string']*3 or i['args'][3]['type']!='pubkey':raise Halt('Pump prefix argument types changed')
        user=5 if name=='create_v2' else 7
        if i['accounts'][user]['name']!='user':raise Halt('Pump user account position changed')
        authority=i['accounts'][1]
        if authority.get('address') not in (None,AUTHORITY):raise Halt('Different mint authority')
        seeds=authority.get('pda',{}).get('seeds',[])
        if not any(s.get('kind')=='const' and bytes(s.get('value',[]))==b'mint-authority' for s in seeds):raise Halt('Mandatory PDA seed not proven')
    if b58decode(PROGRAM).__len__()!=32:raise Halt('Invalid program')
    calculated=hashlib.sha256(b'mint-authority'+bytes([255])+b58decode(PROGRAM)+b'ProgramDerivedAddress').digest()
    if calculated!=b58decode(AUTHORITY):raise Halt('PDA derivation mismatch')
    return True

def version_check(client,day):
    start,end=day_window(day);base='https://api.github.com/repos/pump-fun/pump-public-docs/commits'
    revisions=[];refs=[]
    # Include predecessor and every IDL revision in the day, not just today's IDL.
    predecessor,m=client.json(base+'?'+urlencode({'path':'idl/pump.json','until':iso(start),'per_page':1}),label='Pump_IDL_predecessor_'+day)
    if not isinstance(predecessor,list) or not predecessor:raise Halt('No historical Pump IDL predecessor')
    revisions.append(predecessor[0]['sha']);refs.append(m['raw_ref'])
    for page in range(1,6):
        entries,m=client.json(base+'?'+urlencode({'path':'idl/pump.json','since':iso(start),'until':iso(end),'per_page':100,'page':page}),label='Pump_IDL_changes_'+day)
        if not isinstance(entries,list):raise Halt('Bad GitHub history response')
        revisions.extend(x['sha'] for x in entries);refs.append(m['raw_ref'])
        if len(entries)<100:break
    else:raise Halt('IDL commit pagination incomplete')
    for revision in sorted(set(revisions)):
        d,m=client.json('https://raw.githubusercontent.com/pump-fun/pump-public-docs/'+revision+'/idl/pump.json',label='Pump_historical_IDL_'+revision)
        check_pump_idl(d);refs.append(m['raw_ref'])
    events=load(ROOT/'configs/platform_events.json')
    version_rows=[]
    for v in events:
        if sha(ROOT/v['abi_path'])!=v['abi_sha256']:raise Halt('Pinned ABI hash changed')
        url=client.cfg['sources']['base_rpc' if v['chain_key']=='eip155:8453' else 'bsc_rpc']
        version_rows.append({**v,'day':day,'status':'pinned_exact_address_topic_ABI;full_upgrade_history_not_claimed','source_url':url})
    result={'day':day,'status':'passed_for_declared_layout_scope','Pump_IDL_revisions':sorted(set(revisions)),'Pump_evidence_refs':refs,'evm_versions':[{'chain':v['chain_key'],'version':v['version'],'address':v['address'],'topic0':v['topic0']} for v in version_rows],'exclusions':['Four.meme V1','other factories/topics','complete deployment/proxy lineage'],'checked_at_utc':now()}
    save(client.root/'days'/day/'version_check.json',result);return result

def locate(client,chain,target):
    """Return first produced block at/after target, with preceding-block proof."""
    known=read_csv(P2/'reports/window_boundaries.csv')
    for r in known:
        if r['chain_key']==chain and int(epoch(r['target_utc']))==target:
            n=int(r['first_block_or_slot']);break
    else:
        anchors={'solana:mainnet':(454377023,2.7),'eip155:8453':(52314127,.5),'eip155:56':(126344214,2.3)}
        n0,speed=anchors[chain];n=max(1,int(n0+(target-1791417600)*speed))
    url=client.cfg['sources'][{'solana:mainnet':'solana_rpc','eip155:8453':'base_rpc','eip155:56':'bsc_rpc'}[chain]]
    def timed(number):
        if chain=='solana:mainnet':
            slots,sm=client.rpc(url,'getBlocks',[number,number+64,{'commitment':'finalized'}],'boundary_produced_slots')
            if not slots:raise Halt('Unobservable boundary; skipped slots not inferred from empty source')
            number=int(slots[0]);t,m=client.rpc(url,'getBlockTime',[number],'boundary_time')
            return number,int(t),m
        b,m=client.rpc(url,'eth_getBlockByNumber',[hex(number),False],'boundary_block')
        if int(b['number'],16)!=number:raise Halt('Wrong EVM block identity')
        return number,int(b['timestamp'],16),m
    step=4096;lo=max(1,n-step);hi=n+step
    for _ in range(30):
        ln,lt,lm=timed(lo);hn,ht,hm=timed(hi)
        if lt<target<=ht:break
        step*=2
        if lt>=target:hi=lo;lo=max(1,lo-step)
        else:lo=hi;hi+=step
    else:raise Halt('Cannot bracket target UTC boundary')
    while lo<hi:
        mid=(lo+hi)//2;actual,t,m=timed(mid)
        if t<target:lo=actual+1
        else:hi=mid
    actual,t,m=timed(lo)
    if chain=='solana:mainnet':
        prev,pm=client.rpc(url,'getBlocks',[max(0,actual-64),actual-1,{'commitment':'finalized'}],'previous_produced_boundary')
        if not prev:raise Halt('Previous produced boundary unavailable')
        pn,pt,pmeta=timed(prev[-1])
    else:pn,pt,pmeta=timed(actual-1)
    if not pt<target<=t or pn>=actual:raise Halt('UTC boundary bracket invalid')
    return {'chain_key':chain,'target_utc':iso(target),'first_block_or_slot':actual,'first_time_utc':iso(t),'previous_block_or_slot':pn,'previous_time_utc':iso(pt),'raw_ref':m['raw_ref'],'previous_raw_ref':pmeta['raw_ref']}

def prepare_day(client,day):
    out=client.root/'days'/day;path=out/'bounds.json'
    if path.exists():return load(path)
    version_check(client,day);start,end=day_window(day);bounds={};rows=[]
    for chain in CHAINS:
        a=locate(client,chain,start);b=locate(client,chain,end);rows.extend([a,b]);bounds[chain]=[a['first_block_or_slot'],b['first_block_or_slot']]
    result={'day':day,'start_utc':iso(start),'end_utc':iso(end),'bounds':bounds,'boundary_evidence':rows,'status':'verified_native_brackets'}
    save(path,result);return result

def validate_stream(data,start,end):
    if not data:raise Halt('Empty stream does not prove zero events/coverage')
    heights=[b['header']['number'] for b in data]
    if heights!=sorted(set(heights)) or heights[0]<start or heights[-1]>end:raise Halt('Stream positions unordered or out of bounds')
    return heights[-1]+1

def bsc_stream_logs(data):
    """Attach parent block identity to SQD logs, whose schema omits it."""
    out=[]
    for block in data:
        header=block.get('header') or {}
        number=header.get('number')
        if not isinstance(number,int) or isinstance(number,bool):raise Halt('BSC stream block number missing or invalid')
        for source_log in block.get('logs',[]):
            if not isinstance(source_log,dict):raise Halt('BSC stream log is not an object')
            log=dict(source_log)
            if 'blockNumber' in log:
                value=log['blockNumber'];found=int(value,16) if isinstance(value,str) and value.lower().startswith('0x') else int(value)
                if found!=number:raise Halt('BSC log/block number conflict')
            if log.get('blockHash') and header.get('hash') and log['blockHash'].lower()!=header['hash'].lower():
                raise Halt('BSC log/block hash conflict')
            log['blockNumber']=number
            if header.get('hash'):log['blockHash']=header['hash']
            else:raise Halt('BSC log parent block hash missing')
            out.append(log)
    return out

def evm_logs(client,day,chain,bounds):
    out=client.root/'days'/day;path=out/(chain.replace(':','_')+'_queries.json')
    state=load(path,{'next':bounds[0],'segments':[]});start,end=bounds
    versions=[v for v in load(ROOT/'configs/platform_events.json') if v['chain_key']==chain]
    logs=[]
    for s in state['segments']:
        p=resolve(client.root,s['raw_ref'])
        if sha(p)!=s['sha256']:raise Halt('Query segment hash changed')
        d=json.loads(read_body(p)) if chain=='eip155:8453' else [json.loads(x) for x in read_body(p).splitlines() if x.strip()]
        logs.extend(d['result'] if chain=='eip155:8453' else bsc_stream_logs(d))
    while state['next']<end:
        a=state['next'];z=min(a+(10000 if chain=='eip155:8453' else 1000),end)-1
        if chain=='eip155:8453':
            params={'fromBlock':hex(a),'toBlock':hex(z),'address':[v['address'] for v in versions],'topics':[sorted({v['topic0'] for v in versions})]}
            # Shrink explicit limit errors; other failures remain visible and stop.
            while True:
                try:d,m=client.rpc(client.cfg['sources']['base_rpc'],'eth_getLogs',[params],'Base_creation_range');break
                except Halt as e:
                    if z<=a or not any(x in str(e).lower() for x in ['limit','too large','too many','response cap']):raise
                    z=a+(z-a)//2;params['toBlock']=hex(z)
            if not isinstance(d,list):raise Halt('eth_getLogs did not return a list')
            if any(not a<=int(l['blockNumber'],16)<=z for l in d):raise Halt('Out-of-range native log')
            next_position=z+1;logs.extend(d)
        else:
            q={'type':'evm','fromBlock':a,'toBlock':z,'includeAllBlocks':True,'fields':{'block':{'number':True,'hash':True,'timestamp':True},'log':{'address':True,'topics':True,'data':True,'logIndex':True,'transactionIndex':True,'transactionHash':True},'transaction':{'hash':True,'status':True,'from':True,'to':True,'transactionIndex':True}},'logs':[{'address':[v['address']],'topic0':[v['topic0']],'transaction':True} for v in versions]}
            body,m=client.request(client.cfg['sources']['bsc_archive'],q,'BSC_creation_range');d=[json.loads(x) for x in body.splitlines() if x.strip()]
            next_position=validate_stream(d,a,z)
            if [b['header']['number'] for b in d]!=list(range(a,next_position)):raise Halt('All-block BSC stream has unexplained position gaps')
            logs.extend(bsc_stream_logs(d))
        state['segments'].append({'start':a,'end_exclusive':next_position,'raw_ref':m['raw_ref'],'sha256':m['sha256'],'request_id':m['request_id']});state['next']=next_position;save(path,state)
    unique={}
    for log in logs:
        k=(log['transactionHash'],int(log['logIndex'],16) if isinstance(log['logIndex'],str) else log['logIndex'])
        fingerprint={**log,'logIndex':k[1],'transactionIndex':int(log['transactionIndex'],16) if isinstance(log['transactionIndex'],str) else log['transactionIndex']}
        if k in unique and canonical(unique[k])!=canonical(fingerprint):raise Halt('Conflicting duplicate EVM log')
        unique[k]=fingerprint
    return list(unique.values()),state

def rpc_batch(client,url,calls):
    """Stable request keys make interrupted batches replayable from cache."""
    output={}
    for offset in range(0,len(calls),20):
        batch=calls[offset:offset+20];payload=[{'jsonrpc':'2.0','id':i,'method':method,'params':params} for i,(key,method,params) in enumerate(batch)]
        data,m=client.json(url,payload,'all_creation_native_evidence')
        if not isinstance(data,list) or len(data)!=len(batch) or {x.get('id') for x in data}!=set(range(len(batch))):raise Halt('RPC batch identities missing/duplicated')
        for item in data:
            if item.get('error') or item.get('result') is None:raise Halt('Unresolved native batch result')
            output[batch[item['id']][0]]=(item['result'],m)
    return output

def collect_evm(client,day,chain,bounds):
    logs,state=evm_logs(client,day,chain,bounds);url=client.cfg['sources']['base_rpc' if chain=='eip155:8453' else 'bsc_rpc']
    versions={(v['address'],v['topic0']):v for v in load(ROOT/'configs/platform_events.json') if v['chain_key']==chain}
    txids=sorted({l['transactionHash'] for l in logs});heights=sorted({int(l['blockNumber'],16) if isinstance(l['blockNumber'],str) else l['blockNumber'] for l in logs})
    calls=[('tx:'+s,'eth_getTransactionReceipt',[s]) for s in txids]+[('block:'+str(n),'eth_getBlockByNumber',[hex(n),False]) for n in heights]
    evidence=rpc_batch(client,url,calls);envelopes=[]
    for l in logs:
        rc,rm=evidence['tx:'+l['transactionHash']];n=int(l['blockNumber'],16) if isinstance(l['blockNumber'],str) else l['blockNumber'];h,hm=evidence['block:'+str(n)]
        if int(rc['status'],16)!=1 or rc['transactionHash']!=l['transactionHash'] or rc['blockHash']!=h['hash'] or int(rc['blockNumber'],16)!=n or int(h['number'],16)!=n:raise Halt('Native receipt/header conflict')
        if int(rc['transactionIndex'],16)!=l['transactionIndex']:raise Halt('Native transaction index conflict')
        if l.get('blockHash') and l['blockHash']!=h['hash']:raise Halt('Archive/native block hash conflict')
        candidates=[x for x in rc['logs'] if int(x['logIndex'],16)==l['logIndex']]
        if len(candidates)!=1:raise Halt('Native receipt log not unique')
        actual=candidates[0]
        if actual.get('removed') or l.get('removed') or any(actual[k]!=l[k] for k in ['data','topics']) or actual['address'].lower()!=l['address'].lower():raise Halt('Archive/native event differs')
        v=versions.get((l['address'].lower(),l['topics'][0].lower()))
        if not v:raise Halt('Unknown address/topic')
        exact_evm(v['event_abi'],l['topics'],l['data'])
        envelopes.append({'chain':chain,'header':{'number':n,'hash':h['hash'],'timestamp':int(h['timestamp'],16)},'transactions':[{'hash':rc['transactionHash'],'status':1,'transactionIndex':l['transactionIndex'],'from':rc['from'],'to':rc.get('to',''),'receipt_raw_ref':rm['raw_ref']}],'logs':[l],'header_raw_ref':hm['raw_ref'],'native_source':'public_RPC_all_receipts_and_headers'})
    write_envelopes(client.root/'days'/day/(chain.replace(':','_')+'_normalized.ndjson'),envelopes)
    receipt={'status':'complete_for_declared_address_topic_scope','enumeration_unit':'block_positions','start':bounds[0],'end_exclusive':bounds[1],'positions_complete':state['next']==bounds[1],'native_logs_checked':len(logs),'versions':[v['version'] for v in versions.values()],'zero_log_versions':[v['version'] for v in versions.values() if not any(l['address'].lower()==v['address'] for l in logs)],'day':day,'chain':chain}
    save(client.root/'days'/day/(chain.replace(':','_')+'_receipt.json'),receipt);return receipt

def write_envelopes(path,rows):
    atomic(path,b''.join((canonical(r)+'\n').encode() for r in rows))

def solana_index(client,day,bounds):
    start,end=day_window(day);out=client.root/'days'/day;path=out/'solana_index.json';state=load(path)
    if state is None:
        # A real post-window account transaction anchors official RPC pagination.
        q={'transactionDetails':'full','sortOrder':'asc','limit':1,'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1,'filters':{'blockTime':{'gte':end},'slot':{'gte':bounds[1]}}}
        d,m=client.rpc(client.cfg['sources']['vibe'],'getTransactionsForAddress',[AUTHORITY,q],'post_window_index_anchor')
        data=d.get('data',[])
        if not data or data[0]['blockTime']<end:raise Halt('No proven post-window anchor')
        sig=data[0]['transaction']['signatures'][0]
        state={'anchor_signature':sig,'anchor_time':data[0]['blockTime'],'anchor_raw_ref':m['raw_ref'],'cursor':sig,'pages':[],'candidates':[],'complete':False}
    seen={r['signature'] for r in state['candidates']};seen_page=set()
    for p in state['pages']:
        if sha(resolve(client.root,p['raw_ref']))!=p['sha256']:raise Halt('Index page hash changed')
        seen_page.update(r['signature'] for r in json.loads(read_body(resolve(client.root,p['raw_ref'])))['result'])
    while not state['complete']:
        if len(state['pages'])>=client.cfg['budgets']['max_index_pages_per_day']:raise Halt('Index page cap reached before boundary')
        rows,m=client.rpc(client.cfg['sources']['solana_rpc'],'getSignaturesForAddress',[AUTHORITY,{'before':state['cursor'],'limit':1000,'commitment':'finalized'}],'mandatory_PDA_complete_index')
        if not isinstance(rows,list) or not rows:raise Halt('Empty index page before boundary; completeness unproved')
        if any(r.get('blockTime') is None or r.get('confirmationStatus')!='finalized' for r in rows):raise Halt('Index time/finality unknown')
        slots=[r['slot'] for r in rows]
        if slots!=sorted(slots,reverse=True):raise Halt('Nonmonotone index page')
        if seen_page.intersection(r['signature'] for r in rows) or len({r['signature'] for r in rows})!=len(rows):raise Halt('Duplicate index signature')
        for r in rows:
            if start<=r['blockTime']<end:
                if r['signature'] in seen:raise Halt('Duplicate candidate signature')
                state['candidates'].append(r);seen.add(r['signature'])
        state['pages'].append({'before':state['cursor'],'last':rows[-1]['signature'],'raw_ref':m['raw_ref'],'sha256':m['sha256']});state['cursor']=rows[-1]['signature']
        state['complete']=rows[-1]['blockTime']<start
        seen_page.update(r['signature'] for r in rows);save(path,state)
    return state

def native_supplement_transaction(root,item):
    """Reconstruct one full native transaction and prove its index in its block."""
    for field in ['transaction','block']:
        path=resolve(root,item[field+'_raw_ref'])
        if sha(path)!=item[field+'_sha256']:raise Halt('Native supplement evidence hash changed')
    tx=load_native_json(root,item['transaction_raw_ref'])['result']
    block=load_native_json(root,item['block_raw_ref'])['result']
    if not tx or not block:raise Halt('Native supplement missing transaction or block')
    sig=item['signature'];signatures=block.get('signatures',[])
    if signatures.count(sig)!=1 or tx['transaction']['signatures'][0]!=sig:raise Halt('Native supplement signature/order proof conflict')
    order=signatures.index(sig)
    if tx['slot']!=item['slot'] or tx['blockTime']!=item['blockTime'] or block['blockTime']!=item['blockTime'] or canonical(tx['meta']['err'])!=canonical(item['err']):raise Halt('Native supplement candidate state conflict')
    if tx.get('transactionIndex',order)!=order:raise Halt('Native supplement transaction index conflict')
    keys=tx['transaction']['message']['accountKeys']
    if AUTHORITY not in [x['pubkey'] if isinstance(x,dict) else x for x in keys]:raise Halt('Native supplement mandatory PDA missing')
    tx['transactionIndex']=order
    return tx,block

def load_native_json(root,raw_ref):
    return json.loads(read_body(resolve(root,raw_ref)))

def history_transactions(root,history):
    """Stream original history pages and separately evidenced native repairs."""
    for page in history['pages']:
        for tx in load_native_json(root,page['raw_ref'])['result']['data']:
            yield tx,{**page,'native_source':'Vibe_public_RPC+CryptoHouse_header'}
    for item in history.get('native_supplements',[]):
        tx,block=native_supplement_transaction(root,item)
        yield tx,{'raw_ref':item['transaction_raw_ref'],'native_source':'Solana_public_RPC_getTransaction+getBlock_signature_order+CryptoHouse_header','transaction_index_evidence_ref':item['block_raw_ref'],'native_block_hash':block['blockhash']}

def solana_history(client,day,bounds,index):
    start,end=day_window(day);out=client.root/'days'/day;path=out/'vibe_pages.json';state=load(path,{'pages':[],'cursor':None,'complete':False})
    seen={};prior=None
    def consume(data):
        nonlocal prior
        for tx in data:
            sig=tx['transaction']['signatures'][0];order=(tx['slot'],tx['transactionIndex'])
            if sig in seen or (prior is not None and order<=prior):raise Halt('Vibe duplicate/nonmonotone transaction')
            if not start<=tx['blockTime']<end or not bounds[0]<=tx['slot']<bounds[1]:raise Halt('Vibe transaction outside window')
            seen[sig]=(tx['slot'],tx['blockTime'],canonical(tx['meta']['err']));prior=order
    for page in state['pages']:
        p=resolve(client.root,page['raw_ref'])
        if sha(p)!=page['sha256']:raise Halt('Vibe page hash changed')
        consume(json.loads(read_body(p))['result']['data'])
    cursors={p['next_cursor'] for p in state['pages'] if p.get('next_cursor')}
    while not state['complete']:
        if len(state['pages'])>=client.cfg['budgets']['max_vibe_pages_per_day']:raise Halt('Vibe history page cap reached')
        q={'transactionDetails':'full','sortOrder':'asc','limit':100,'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1,'filters':{'slot':{'gte':bounds[0],'lt':bounds[1]},'blockTime':{'gte':start,'lt':end}}}
        if state['cursor']:q['paginationToken']=state['cursor']
        result,m=client.rpc(client.cfg['sources']['vibe'],'getTransactionsForAddress',[AUTHORITY,q],'full_native_history_page')
        data=result.get('data',[]);cursor=result.get('paginationToken');consume(data)
        if cursor and (cursor in cursors or not data):raise Halt('Repeated/nonadvancing Vibe cursor')
        state['pages'].append({'raw_ref':m['raw_ref'],'sha256':m['sha256'],'request_id':m['request_id'],'retrieved_at_utc':m['retrieved_at_utc'],'next_cursor':cursor,'rows':len(data)})
        state['cursor']=cursor;state['complete']=not cursor
        if cursor:cursors.add(cursor)
        save(path,state)
    expected={r['signature']:(r['slot'],r['blockTime'],canonical(r['err'])) for r in index['candidates']}
    if seen.keys()-expected.keys() or any(seen[s]!=expected[s] for s in seen.keys()&expected.keys()):raise Halt('Official index/Vibe full transaction membership or execution state conflict')
    # A full history walk can omit versioned transactions. Do not discard index
    # candidates: obtain each missing full transaction from the already declared
    # official RPC, and prove native transaction order from getBlock signatures.
    candidates={r['signature']:r for r in index['candidates']}
    for item in state.get('native_supplements',[]):
        tx,block=native_supplement_transaction(client.root,item);sig=item['signature']
        value=(tx['slot'],tx['blockTime'],canonical(tx['meta']['err']))
        if sig in seen or sig not in expected or value!=expected[sig]:raise Halt('Native supplement duplicate or candidate conflict')
        seen[sig]=value
    for sig in sorted(expected.keys()-seen.keys(),key=lambda s:(expected[s][0],s)):
        candidate=candidates[sig];url=client.cfg['sources']['solana_rpc']
        tx,tm=client.rpc(url,'getTransaction',[sig,{'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1}],'missing_index_candidate_full_native_transaction')
        if tx is None:raise Halt('Missing index candidate has no native transaction')
        block,bm=client.rpc(url,'getBlock',[candidate['slot'],{'transactionDetails':'signatures','rewards':False,'commitment':'finalized','maxSupportedTransactionVersion':1}],'missing_index_candidate_native_order')
        item={**candidate,'transaction_raw_ref':tm['raw_ref'],'transaction_sha256':tm['sha256'],'block_raw_ref':bm['raw_ref'],'block_sha256':bm['sha256'],'repair_reason':'absent_from_completed_Vibe_walk; official_index_candidate_preserved'}
        tx,block=native_supplement_transaction(client.root,item)
        seen[sig]=(tx['slot'],tx['blockTime'],canonical(tx['meta']['err']))
        state.setdefault('native_supplements',[]).append(item);save(path,state)
    if seen!=expected:raise Halt('Official index/full native transaction reconciliation failed')
    state['cross_source_set_verified']=True;state['candidate_count']=len(expected);save(path,state);return state

def solana_headers(client,day,history):
    out=client.root/'days'/day;path=out/'solana_headers.json';headers=load(path,{})
    wanted=set()
    wanted.update(tx['slot'] for tx,page in history_transactions(client.root,history))
    missing=sorted(n for n in wanted if str(n) not in headers)
    start,end=day_window(day)
    for offset in range(0,len(missing),400):
        group=missing[offset:offset+400]
        q="SELECT slot,block_hash,toUnixTimestamp(block_timestamp) AS timestamp FROM solana.blocks WHERE block_timestamp>=toDateTime('"+iso(start).replace('T',' ').replace('Z','')+"','UTC') AND block_timestamp<toDateTime('"+iso(end).replace('T',' ').replace('Z','')+"','UTC') AND slot IN ("+','.join(map(str,group))+") ORDER BY slot FORMAT JSON"
        body,m=client.request(client.cfg['sources']['headers_sql'],label='named_slot_headers',raw_sql=q);data=json.loads(body)['data']
        if {int(r['slot']) for r in data}!=set(group) or len(data)!=len(group):raise Halt('Missing/extra/duplicate SQL block headers')
        for r in data:headers[str(r['slot'])]={'number':int(r['slot']),'hash':r['block_hash'],'timestamp':int(r['timestamp']),'raw_ref':m['raw_ref'],'sha256':m['sha256']}
        save(path,headers)
    for h in headers.values():
        if sha(resolve(client.root,h['raw_ref']))!=h['sha256']:raise Halt('Header source hash changed')
    return headers

def targeted_commitments(client,slot,items):
    q={'type':'solana','fromBlock':slot,'toBlock':slot,'fields':{'block':{'number':True,'hash':True,'timestamp':True},'instruction':{'programId':True,'accounts':True,'data':True,'isCommitted':True,'error':True,'instructionAddress':True,'transactionIndex':True},'transaction':{'transactionIndex':True,'signatures':True,'err':True}},'instructions':[{'programId':[PROGRAM],'d8':['0x181ec828051c0777','0xd6904cec5f8b31b4'],'transaction':True}]}
    body,m=client.request(client.cfg['sources']['solana_archive'],q,'unknown_inner_commitment_single_slot')
    blocks=[json.loads(x) for x in body.splitlines() if x.strip()]
    if len(blocks)!=1 or blocks[0]['header']['number']!=slot:raise Halt('Unknown commitment remains unresolved')
    b=blocks[0];txs={t['transactionIndex']:t for t in b.get('transactions',[])}
    return {(txs[i['transactionIndex']]['signatures'][0],tuple(i['instructionAddress'])):(i,txs[i['transactionIndex']],b['header'],m) for i in b.get('instructions',[])}

def collect_solana(client,day,bounds):
    index=solana_index(client,day,bounds);history=solana_history(client,day,bounds,index);headers=solana_headers(client,day,history)
    out=client.root/'days'/day;normalized=out/'solana_mainnet_normalized.ndjson';tmp=normalized.with_suffix('.tmp');resolution=[];admitted=excluded=0
    out.mkdir(parents=True,exist_ok=True)
    try:
        with tmp.open('w',encoding='utf-8') as f:
            for tx,page in history_transactions(client.root,history):
                sig=tx['transaction']['signatures'][0];h=headers[str(tx['slot'])]
                if h['timestamp']!=tx['blockTime']:raise Halt('Header/native time conflict')
                if page.get('native_block_hash') and page['native_block_hash']!=h['hash']:raise Halt('Supplement native block hash/header conflict')
                selected=native_creations(tx);fallback=None;count=0
                for i in selected:
                    if i['isCommitted'] is None:
                        fallback=fallback or targeted_commitments(client,tx['slot'],selected)
                        item=fallback.get((sig,tuple(i['instructionAddress'])))
                        if not item:raise Halt('Unknown inner commitment absent from archive')
                        old,parent,head,meta=item
                        if old['accounts']!=i['accounts'] or old['data']!=i['data'] or head['hash']!=h['hash'] or old['transactionIndex']!=tx['transactionIndex']:raise Halt('Archive/native instruction conflict')
                        if not isinstance(old.get('isCommitted'),bool):raise Halt('Archive execution state unknown')
                        i['isCommitted']=old['isCommitted'] and old.get('error') is None and parent.get('err') is None
                        i['instruction_commitment_evidence_ref']=meta['raw_ref']
                    else:i['instruction_commitment_evidence_ref']=page['raw_ref']
                    if i['isCommitted']:
                        pump_args(i['data'])
                        if len(i['accounts'])<2 or i['accounts'][1]!=AUTHORITY:raise Halt('Mandatory authority missing')
                        admitted+=1;count+=1
                    else:excluded+=1
                keys=tx['transaction']['message']['accountKeys'];payer=keys[0]['pubkey'] if isinstance(keys[0],dict) else keys[0]
                envelope={'chain':'solana:mainnet','header':{'number':tx['slot'],'hash':h['hash'],'timestamp':tx['blockTime']},'transactions':[{'transactionIndex':tx['transactionIndex'],'signatures':[sig],'err':tx['meta']['err'],'feePayer':payer,'version':tx.get('version',''),'receipt_raw_ref':page['raw_ref'],'transaction_index_evidence_ref':page.get('transaction_index_evidence_ref','')}],'instructions':selected,'header_raw_ref':h['raw_ref'],'native_source':page['native_source']}
                f.write(canonical(envelope)+'\n');resolution.append({'signature':sig,'slot':tx['slot'],'state':'resolved','transaction_failed':tx['meta']['err'] is not None,'committed_creations':count,'raw_ref':page['raw_ref']})
        os.replace(tmp,normalized)
    finally:tmp.unlink(missing_ok=True)
    write_csv(out/'solana_resolution.csv',resolution,['signature','slot','state','transaction_failed','committed_creations','raw_ref'])
    report={'status':'complete_for_declared_address_topic_scope','enumeration_unit':'mandatory_PDA_transactions','candidate_count':len(index['candidates']),'resolved_candidates':len(resolution),'native_supplement_transactions':len(history.get('native_supplements',[])),'creations':admitted,'excluded_recognized_instructions':excluded,'unknown_commitments':0,'day':day,'chain':'solana:mainnet'}
    save(out/'solana_mainnet_receipt.json',report);return report
