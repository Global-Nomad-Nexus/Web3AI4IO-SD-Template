"""Fixed-seed native RPC replay checks of archive-derived creation records."""
from p2io import *
from decode import pump_args,exact_evm
from collections import defaultdict
import random,argparse

def run(limit=10):
    c=Client(budget=180);rows=read_csv(ROOT/'processed/registry.csv');groups=defaultdict(list)
    for r in rows:
        if r['chain_key']!='eip155:8453':groups[(r['chain_key'],r['platform_version_id'])].append(r)
    versions=json.loads((ROOT/'configs/platform_events.json').read_text());results=[]
    for group,data in sorted(groups.items()):
        rng=random.Random(20261027);samples=rng.sample(sorted(data,key=lambda r:r['creation_event_id']),min(limit,len(data)))
        # Supplement the fixed random draw with boundary and known-risk examples.
        chronological=sorted(data,key=lambda r:(r['created_at_utc'],r['creation_event_id']))
        extra=[chronological[0],chronological[-1]]
        if group[0]=='solana:mainnet':
            for predicate in [lambda r:r.get('transaction_format_version')=='1',lambda r:len(json.loads(r['native_instruction_path']))>1,lambda r:not r['initial_metadata_uri']]:
                candidate=next((r for r in chronological if predicate(r)),None)
                if candidate:extra.append(candidate)
        samples=list({r['creation_event_id']:r for r in samples+extra}.values())
        for r in samples:
            chain=r['chain_key'];sig=r['creation_tx_hash_or_signature'];err='';checks={};refs=[]
            try:
                if chain=='solana:mainnet':
                    tx,m=c.rpc('https://api.mainnet-beta.solana.com','getTransaction',[sig,{'commitment':'finalized','encoding':'jsonParsed','maxSupportedTransactionVersion':1}],'Solana_creation_native_replay_QA');refs.append(m['raw_ref'])
                    if not tx:raise ValueError('RPC transaction unavailable: '+m['error'])
                    msg=tx['transaction']['message'];accounts=[a['pubkey'] if isinstance(a,dict) else a for a in msg['accountKeys']]
                    ix=list(msg.get('instructions',[]))+[i for g in tx['meta'].get('innerInstructions',[]) for i in g['instructions']]
                    found=[]
                    for i in ix:
                        program=i.get('programId',accounts[i['programIdIndex']] if 'programIdIndex' in i else '')
                        if program!=r['program_or_factory_address'] or not i.get('data'):continue
                        try:args=pump_args(i['data'])
                        except ValueError:continue
                        acc=[accounts[x] if isinstance(x,int) else x for x in i.get('accounts',[])]
                        if acc and acc[0]==r['token_address_canonical']:found.append(args)
                    checks={'execution_success':tx['meta']['err'] is None,'slot':str(tx['slot'])==r['block_height_or_slot'],'time':iso(tx['blockTime'])==r['created_at_utc'],'mint_creator_name_symbol':any(a['creator']==r['creator_address'] and a['name']==r['initial_name'] and a['symbol']==r['initial_symbol'] for a in found)}
                    b,bm=c.rpc('https://api.mainnet-beta.solana.com','getBlock',[int(r['block_height_or_slot']),{'commitment':'finalized','transactionDetails':'none','rewards':False,'maxSupportedTransactionVersion':1}],'Solana_creation_block_hash_QA');refs.append(bm['raw_ref']);checks['block_hash']=bool(b) and b['blockhash']==r['block_hash']
                else:
                    tx,m=c.rpc('https://bsc-dataseed.bnbchain.org','eth_getTransactionReceipt',[sig],'BSC_archive_creation_native_receipt_QA');refs.append(m['raw_ref'])
                    if not tx:raise ValueError('Native receipt unavailable: '+m['error'])
                    v=next(v for v in versions if v['chain_key']==chain and v['version']==r['platform_version_id'])
                    logs=[l for l in tx['logs'] if int(l['logIndex'],16)==int(r['log_index']) and l['address'].lower()==r['program_or_factory_address'] and l['topics'][0]==v['topic0']]
                    args=exact_evm(v['event_abi'],logs[0]['topics'],logs[0]['data']) if len(logs)==1 else {}
                    checks={'execution_success':tx['status']=='0x1','block_height':str(int(tx['blockNumber'],16))==r['block_height_or_slot'],'block_hash':tx['blockHash']==r['block_hash'],'mint_and_creator':args.get('token','').lower()==r['token_address_canonical'] and args.get('creator','').lower()==r['creator_address'].lower()}
                    b,bm=c.rpc('https://bsc-dataseed.bnbchain.org','eth_getBlockByNumber',[tx['blockNumber'],False],'BSC_creation_block_time_QA');refs.append(bm['raw_ref']);checks['time']=bool(b) and iso(int(b['timestamp'],16))==r['created_at_utc']
            except Exception as e:err=type(e).__name__+': '+str(e)
            results.append({'chain_key':chain,'platform_version_id':r['platform_version_id'],'creation_event_id':r['creation_event_id'],'token_id':r['token_id'],'selection_rule':'fixed_seed_20261027_per_chain_version_plus_boundary_version1_nested_emptyURI_cases','sample_limit':limit,'checks_json':json.dumps(checks,sort_keys=True),'status':'passed' if checks and all(checks.values()) and not err else 'failed','error':err,'native_raw_refs':'|'.join(refs),'archive_raw_ref':r['raw_ref']})
            write_csv(ROOT/'reports/native_QA.csv',results);print(chain,r['token_id'],results[-1]['status'],err,flush=True)
    base=json.loads((ROOT/'reports/base_rpc_receipt.json').read_text())
    write_json(ROOT/'reports/native_QA_receipt.json',{'executed_at_utc':now(),'archive_sample_checks':len(results),'archive_sample_failures':sum(r['status']!='passed' for r in results),'native_Base_logs_all_receipt_checked':base['log_rows'],'status':'passed' if all(r['status']=='passed' for r in results) else 'failed','scope':'automated native-source replay check, not human manual QA; not proof of all-chain census'})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=10);run(p.parse_args().limit)
