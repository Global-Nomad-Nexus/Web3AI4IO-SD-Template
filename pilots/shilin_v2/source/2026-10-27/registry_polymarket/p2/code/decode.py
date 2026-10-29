"""Decode frozen native events. Never filter on URI availability or token success."""
from p2io import *
sys.path.insert(0,str(ROOT/'vendor'))
from eth_abi import decode as abi_decode,encode as abi_encode
from collections import Counter

ALPHABET='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58decode(s):
    n=0
    for ch in s:n=n*58+ALPHABET.index(ch)
    return b'\0'*(len(s)-len(s.lstrip('1')))+(n.to_bytes((n.bit_length()+7)//8,'big') if n else b'')
def b58encode(b):
    n=int.from_bytes(b,'big');out=''
    while n:n,k=divmod(n,58);out=ALPHABET[k]+out
    return '1'*(len(b)-len(b.lstrip(b'\0')))+out
def pump_args(data):
    b=b58decode(data);disc=b[:8].hex()
    if disc not in ['181ec828051c0777','d6904cec5f8b31b4']:raise ValueError('Not a qualified Pump create discriminator')
    offset=8;values={}
    for name in ['name','symbol','uri']:
        if offset+4>len(b):raise ValueError('Truncated string length')
        length=int.from_bytes(b[offset:offset+4],'little');offset+=4
        if offset+length>len(b):raise ValueError('Truncated Borsh string')
        values[name]=b[offset:offset+length].decode();offset+=length
    if offset+32>len(b):raise ValueError('Truncated creator')
    values['creator']=b58encode(b[offset:offset+32]);offset+=32
    values['native_instruction']='create' if disc=='181ec828051c0777' else 'create_v2'
    values['uninterpreted_optional_tail_hex']=b[offset:].hex()
    return values
def exact_evm(event,topics,data):
    regular=[x for x in event['inputs'] if not x.get('indexed')];indexed=[x for x in event['inputs'] if x.get('indexed')]
    if len(topics)!=1+len(indexed):raise ValueError('Wrong indexed topic count')
    types=[x['type'] for x in regular];raw=bytes.fromhex(data[2:]);vals=abi_decode(types,raw,strict=True)
    if abi_encode(types,vals)!=raw:raise ValueError('Noncanonical ABI payload')
    out={x['name']:v for x,v in zip(regular,vals)}
    for x,t in zip(indexed,topics[1:]):out[x['name']]=abi_decode([x['type']],bytes.fromhex(t[2:]),strict=True)[0]
    def precise(v):
        if isinstance(v,bytes):return '0x'+v.hex()
        if isinstance(v,(list,tuple)):return [precise(x) for x in v]
        if isinstance(v,int) and not isinstance(v,bool):return str(v)
        return v
    return {k:precise(v) for k,v in out.items()}

def run():
    protocol=json.loads((ROOT/'configs/pilot_protocol.json').read_text());versions=json.loads((ROOT/'configs/platform_events.json').read_text())
    vmap={(v['chain_key'],v['address'],v['topic0']):v for v in versions}
    events=[];excluded=[];bad=[];seen={};candidates=Counter();versions_seen=Counter()
    ledger=[]
    base_native=ROOT/'reports/base_rpc_receipt.json'
    sol_receipt_path=ROOT/'reports/solana_native_creation_receipt.json'
    sol_native=sol_receipt_path.exists() and json.loads(sol_receipt_path.read_text())['status']=='passed_complete_native_creation_resolution'
    for file in sorted((ROOT/'reports').glob('query_ledger*.csv')):
        for seg in read_csv(file):
            if seg['chain_key']=='eip155:8453' and base_native.exists():continue
            if seg['chain_key']=='solana:mainnet' and sol_native:continue
            ledger.append(seg)
    if sol_native:ledger.extend(read_csv(ROOT/'reports/vibe_creation_segments.csv'))
    if base_native.exists():
        m=json.loads(base_native.read_text());ledger.append({'chain_key':'eip155:8453','status':'complete_segment','returned_block_rows':'1','raw_ref':m['normalized_ref'],'raw_sha256':m['normalized_sha256'],'retrieved_at_utc':'see native source response timestamps','request_id':'native_base_receipt_checked'})
    for seg in ledger:
        if seg['status']!='complete_segment' or not int(seg['returned_block_rows']):continue
        chain=seg['chain_key'];path=ROOT/seg['raw_ref']
        if sha(path)!=seg['raw_sha256']:raise RuntimeError('Raw response hash mismatch')
        for block in blocks(path.read_bytes()):
            header=block['header'];t=header['timestamp']
            if not 1791417600<=t<1791504000:raise RuntimeError('Creation block outside frozen UTC window')
            txs=block.get('transactions',[])
            index={x['transactionIndex']:x for x in txs if 'transactionIndex' in x}
            hashes={x['hash']:x for x in txs if 'hash' in x}
            for item in block.get('instructions' if chain=='solana:mainnet' else 'logs',[]):
                candidates[chain]+=1;ref=seg['raw_ref']+'#block='+str(header['number'])
                try:
                    if chain=='solana:mainnet':
                        tx=index.get(item['transactionIndex'])
                        if tx is None:raise ValueError('Missing parent transaction by native transactionIndex')
                        sig=tx['signatures'][0];position=json.dumps(item['instructionAddress'],separators=(',',':'))
                        key=(chain,sig,position)
                        if item.get('isCommitted') is not True or item.get('error') is not None or tx.get('err') is not None:
                            excluded.append({'chain_key':chain,'transaction':sig,'position':position,'reason':'uncommitted_or_failed_instruction_or_transaction','raw_ref':ref});continue
                        args=pump_args(item['data']);address=item['accounts'][0];creator=args['creator']
                        version='pump_create_prefix_accounts_v1';program=item['programId'];platform='pump.fun';name=args['name'];symbol=args['symbol'];uri=args['uri'];role='creator argument;not assumed fee payer or user account'
                        sender=item['accounts'][5 if args['native_instruction']=='create_v2' else 7];args['instruction_user_signer_address']=sender;fee_payer=tx.get('feePayer','');outer=item['instructionAddress'][0];inner=json.dumps(item['instructionAddress'][1:]);log_index=''
                    else:
                        sig=item['transactionHash'];position=str(item['logIndex']);key=(chain,sig,position)
                        tx=hashes.get(sig)
                        if tx is None:raise ValueError('Missing parent EVM transaction')
                        if tx['status']!=1:
                            excluded.append({'chain_key':chain,'transaction':sig,'position':position,'reason':'failed_transaction','raw_ref':ref});continue
                        v=vmap.get((chain,item['address'].lower(),item['topics'][0].lower()))
                        if not v:raise ValueError('Unregistered address/topic')
                        args=exact_evm(v['event_abi'],item['topics'],item['data']);address=args.get('tokenAddress',args.get('token'));creator=args.get('creator',args.get('tokenAdmin',args.get('creatorAdmin',args.get('deployer',''))))
                        role='TokenCreate.creator' if v['platform_id']=='four.meme' else ('TokenCreated.tokenAdmin' if v['version']=='v4' else ('TokenCreated.creatorAdmin' if v['version']=='v3.1' else 'TokenCreated.deployer'))
                        version=v['version'];program=v['address'];platform=v['platform_id'];name=args.get('tokenName',args.get('name',''));symbol=args.get('tokenSymbol',args.get('symbol',''));uri='';sender=tx['from'];fee_payer='';outer='';inner='';log_index=item['logIndex']
                    if key in seen:
                        if seen[key]!=sid(item):raise ValueError('Conflicting duplicate native event')
                        continue
                    seen[key]=sid(item);cid='creation:'+sid(*key)
                    native_base=chain=='eip155:8453' and 'header_raw_ref' in block
                    row={'creation_event_id':cid,'token_id':token_id(chain,address),'chain_key':chain,'platform_id':platform,'platform_version_id':version,'program_or_factory_address':program,'token_address_raw':address,'token_address_canonical':address if chain=='solana:mainnet' else address.lower(),'creation_tx_hash_or_signature':sig,'block_height_or_slot':header['number'],'block_hash':header['hash'],'created_at_utc':iso(t),'transaction_index':item['transactionIndex'],'transaction_format_version':str(tx.get('version','')) if chain=='solana:mainnet' else '', 'native_instruction_path':position if chain=='solana:mainnet' else '', 'outer_instruction_index':outer,'inner_instruction_path':inner,'log_index':log_index,'creator_address':creator,'creator_role_definition':role,'tx_sender_or_signer':sender,'sender_role_definition':'IDL instruction user signer;not assumed creator or fee payer' if chain=='solana:mainnet' else 'native transaction.from','fee_payer':fee_payer,'initial_name':name,'initial_symbol':symbol,'initial_metadata_uri':uri,'initial_metadata_uri_status':'onchain_empty_preserved' if chain=='solana:mainnet' and not uri else ('onchain_declared' if uri else 'not_in_creation_event_schema'),'initial_attributes_json':json.dumps(args,ensure_ascii=False,sort_keys=True),'discovery_mode':'historical_backfill','retrieved_at_utc':seg['retrieved_at_utc'],'first_decoded_at_utc':'','historical_metadata_status':'not_collected_historically_P2','source_id':'Base_native_public_RPC' if native_base else 'SQD_public_portal','raw_ref':ref,'native_receipt_raw_ref':tx.get('receipt_raw_ref',''),'native_block_raw_ref':block.get('header_raw_ref',''),'query_request_id':seg['request_id'],'execution_status':'success_committed','decoder_version':'p2_native_creation_v1','cohort_id':protocol['protocol_version'],'validation_status':'every_native_receipt_and_header_checked' if native_base else 'native_decode_complete_RPC_QA_pending'}
                    if block.get('native_source'):
                        row['source_id']=block['native_source'];row['validation_status']='native_source_decoded_with_independent_block_header_evidence'
                    row['instruction_commitment_evidence_ref']=item.get('instruction_commitment_evidence_ref',ref) if chain=='solana:mainnet' else ''
                    events.append(row);versions_seen[(chain,version)]+=1
                except Exception as e:
                    bad.append({'chain_key':chain,'raw_ref':ref,'native_position':json.dumps(item.get('instructionAddress',item.get('logIndex'))),'error':type(e).__name__+': '+str(e),'native_item_json':json.dumps(item,ensure_ascii=False)})
    # Exclusion records have native-event grain, not query-attempt grain. Raw
    # duplicate observations remain independently available in the query ledger.
    exclusions={}
    for r in excluded:
        key=(r['chain_key'],r['transaction'],r['position'])
        if key not in exclusions:exclusions[key]=r
        elif r['raw_ref'] not in exclusions[key]['raw_ref'].split('|'):exclusions[key]['raw_ref']+='|'+r['raw_ref']
    excluded=list(exclusions.values())
    qa_by_id={}
    for file in [ROOT/'reports/native_QA.csv',ROOT/'reports/bsc_all_native_QA.csv']:
        if file.exists():qa_by_id.update({r['creation_event_id']:r for r in read_csv(file) if r['status']=='passed'})
    for r in events:
        q=qa_by_id.get(r['creation_event_id'])
        if q:
            r['validation_status']='native_RPC_creation_replay_checked'
            if q.get('receipt_raw_ref'):r['native_receipt_raw_ref']=q['receipt_raw_ref']
            if q.get('header_raw_ref'):r['native_block_raw_ref']=q['header_raw_ref']
        elif r['source_id']=='SQD_public_portal':r['validation_status']='native_decode_complete_not_individually_RPC_checked'
    events.sort(key=lambda r:(r['chain_key'],r['created_at_utc'],r['creation_event_id']))
    by_token={};conflicts=[]
    for r in events:
        if r['token_id'] in by_token:conflicts.append({'token_id':r['token_id'],'first_event':by_token[r['token_id']]['creation_event_id'],'second_event':r['creation_event_id'],'resolution':'unresolved;not_silently_deduplicated'})
        else:by_token[r['token_id']]=r
    write_csv(ROOT/'processed/creation_events.csv',events)
    write_csv(ROOT/'processed/registry.csv',list(by_token.values()))
    write_csv(ROOT/'reports/decode_errors.csv',bad,['chain_key','raw_ref','native_position','error','native_item_json'])
    write_csv(ROOT/'reports/excluded_failed_creations.csv',excluded,['chain_key','transaction','position','reason','raw_ref'])
    write_csv(ROOT/'reports/creation_conflicts.csv',conflicts,['token_id','first_event','second_event','resolution'])
    write_json(ROOT/'reports/decode_receipt.json',{'candidates_by_chain':dict(candidates),'admitted_by_chain':dict(Counter(r['chain_key'] for r in events)),'versions_seen':{':'.join(k):v for k,v in versions_seen.items()},'decode_errors':len(bad),'conflicting_token_creations':len(conflicts),'excluded_failed':len(excluded),'status':'passed' if not bad and not conflicts else 'failed','scope':'native onchain event signature/ABI and stable Pump argument prefix; no URI nonempty gate; optional versioned Pump tail retained uninterpreted'})
    print(json.dumps({'events':len(events),'by_chain':dict(Counter(r['chain_key'] for r in events)),'errors':len(bad),'conflicts':len(conflicts)}),flush=True)
if __name__=='__main__':run()
