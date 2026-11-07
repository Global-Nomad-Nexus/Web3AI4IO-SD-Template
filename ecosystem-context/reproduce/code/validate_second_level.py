#!/usr/bin/env python3
"""Independent day-level output controls and bounded official-RPC identity checks."""
from build_aws_network_second import *
import math

def rpc(endpoint,method,params):
    payload={'jsonrpc':'2.0','id':1,'method':method,'params':params}
    r=SESSION.post(endpoint,json=payload,timeout=60);r.raise_for_status();d=r.json();assert 'result' in d,d
    return d['result'],{'endpoint':endpoint,'request':payload,'response':d}

def network(chain):
    layer=ROOT/chain/'layer2';ev=layer/'evidence/aws-selected';manifest=json.loads((layer/'evidence/aws-network-validation.json').read_text())
    path=layer/'output/aws_network_second.parquet';assert sha(path)==manifest['output_sha256'];pf=pq.ParquetFile(path)
    assert pf.metadata.num_rows==1814400 and pf.metadata.num_row_groups==21
    summaries=[]
    for i in range(21):
        date=f'2026-10-{i+1:02d}';expected=json.loads((ev/f'{date}-network-validation.json').read_text());d=pf.read_row_group(i).to_pandas()
        start=pd.Timestamp(date,tz='UTC');assert len(d)==86400
        assert d.interval_start_utc.iloc[0]==start and d.interval_start_utc.iloc[-1]==start+pd.Timedelta(seconds=86399)
        assert (d.interval_start_utc.diff().iloc[1:]==pd.Timedelta(seconds=1)).all()
        for col,k in [('block_count','blocks'),('transaction_count','transactions'),('gas_used','gas_used')]:assert int(d[col].sum())==expected[k]
        assert d.coverage_complete.all() and (d.transaction_count>=0).all()
        if chain=='base':
            for col in ['execution_fees_wei','l1_fees_reported_wei']:assert int(sum(d[col]))==int(expected[col])
            assert (d.successful_transaction_count+d.failed_transaction_count==d.transaction_count).all()
            assert np.array_equal(d.execution_fees_wei+d.l1_fees_reported_wei,d.execution_plus_reported_l1_fees_wei)
        summaries.append({k:expected[k] for k in ['date','first_height','last_height','blocks','transactions']})
    endpoint='https://mainnet.base.org' if chain=='base' else 'https://bsc-dataseed.bnbchain.org'
    evidence=[];checks=[]
    cid,e=rpc(endpoint,'eth_chainId',[]);evidence.append(e);assert int(cid,16)==(8453 if chain=='base' else 56)
    first=summaries[0]['first_height'];last=summaries[-1]['last_height']
    before,e=rpc(endpoint,'eth_getBlockByNumber',[hex(first-1),False]);evidence.append(e)
    after,e=rpc(endpoint,'eth_getBlockByNumber',[hex(last+1),False]);evidence.append(e)
    assert int(before['timestamp'],16)<1790812800 and int(after['timestamp'],16)>=1792627200
    for date in ['2026-10-01','2026-10-11','2026-10-21']:
        b=pq.read_table(ev/f'{date}-blocks-000.parquet').to_pandas();heightcol='BLOCK_NUMBER' if chain=='base' else 'number';b=b.sort_values(heightcol);row=b.iloc[len(b)//2];height=int(row[heightcol])
        block,e=rpc(endpoint,'eth_getBlockByNumber',[hex(height),False]);evidence.append(e)
        hashcol='BLOCK_HASH' if chain=='base' else 'hash';txcol='TRANSACTION_COUNT' if chain=='base' else 'transaction_count';gascol='GAS_USED' if chain=='base' else 'gas_used';timecol='TIMESTAMP' if chain=='base' else 'timestamp'
        assert block['hash']==row[hashcol] and int(block['timestamp'],16)==int(row[timecol]) and len(block['transactions'])==int(row[txcol]) and int(block['gasUsed'],16)==int(row[gascol])
        check={'date':date,'height':height,'block_hash_count_gas_timestamp_match':True}
        if chain=='base':
            receipts,e=rpc(endpoint,'eth_getBlockReceipts',[hex(height)]);evidence.append(e)
            assert {r['transactionHash'] for r in receipts}==set(block['transactions']) and all(r['blockHash']==block['hash'] for r in receipts)
            execution=sum(int(r['gasUsed'],16)*int(r['effectiveGasPrice'],16) for r in receipts)
            l1=sum(int(r.get('l1Fee','0x0'),16) for r in receipts)
            idx=(int(block['timestamp'],16)-1790812800)//86400;sec=(int(block['timestamp'],16)-1790812800)%86400
            computed=pf.read_row_group(idx).slice(sec,1).to_pylist()[0]
            assert execution==int(computed['execution_fees_wei']) and l1==int(computed['l1_fees_reported_wei'])
            check.update({'execution_fees_wei':str(execution),'l1_fees_wei':str(l1),'fee_components_match':True,'operator_fields_present':sorted({k for r in receipts for k in r if 'operator' in k.lower()})})
        checks.append(check)
    receipt={'status':'Verified','scope':'21 complete UTC output days; daily sums; 3 official RPC blocks and window-adjacent blocks; Base sample receipts fee components','chain':chain,'output_sha256':sha(path),'window_boundary_checks':True,'sample_checks':checks,'rpc_evidence':evidence}
    (layer/'evidence/aws-network-independent-validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='rpc_evidence'}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--chain',choices=['base','BSC'],required=True);args=p.parse_args();network(args.chain)
