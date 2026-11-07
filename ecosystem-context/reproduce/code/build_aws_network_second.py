#!/usr/bin/env python3
"""Anonymous AWS column-selective census; integer fee arithmetic, daily checkpoints."""
import argparse, datetime as dt, hashlib, io, json, pathlib, time, urllib.parse, xml.etree.ElementTree as ET
import requests
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import psutil

ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='https://aws-public-blockchain.s3.us-east-2.amazonaws.com/'
SESSION=requests.Session()
MEMORY_LIMIT_BYTES=2*1024**3
OFFLINE=False
RECOMPUTE=False
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def guard():
    if psutil.Process().memory_info().rss>MEMORY_LIMIT_BYTES or psutil.virtual_memory().available<1024**3:
        raise MemoryError('STOP: ask user before continuing; memory budget reached')
def request(url,**kw):
    for a in range(4):
        try:
            r=SESSION.get(url,timeout=90,**kw);r.raise_for_status();return r
        except requests.RequestException:
            if a==3:raise
            time.sleep(2**a)
def listing(prefix):
    result=[];token=None
    while True:
        params={'list-type':'2','prefix':prefix}
        if token:params['continuation-token']=token
        r=request(BASE,params=params);x=ET.fromstring(r.content);ns={'s':'http://s3.amazonaws.com/doc/2006-03-01/'}
        for c in x.findall('s:Contents',ns):
            key=c.findtext('s:Key',namespaces=ns)
            if key.endswith('.parquet'):result.append({'key':key,'size':int(c.findtext('s:Size',namespaces=ns)),'etag':c.findtext('s:ETag',namespaces=ns)})
        if x.findtext('s:IsTruncated',namespaces=ns)!='true':break
        token=x.findtext('s:NextContinuationToken',namespaces=ns)
    assert result,prefix
    return result

class Remote(io.RawIOBase):
    def __init__(self,entry):self.entry=entry;self.pos=0;self.bytes=0;self.ranges=[]
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,n,whence=0):
        self.pos=n if whence==0 else (self.pos+n if whence==1 else self.entry['size']+n);return self.pos
    def read(self,n=-1):
        guard();n=min(n if n>=0 else self.entry['size']-self.pos,self.entry['size']-self.pos)
        if not n:return b''
        begin=self.pos
        r=request(BASE+self.entry['key'],headers={'Range':f'bytes={begin}-{begin+n-1}','If-Match':self.entry['etag']})
        assert r.status_code==206 and len(r.content)==n,(r.status_code,len(r.content),n)
        assert r.headers['Content-Range']==f'bytes {begin}-{begin+n-1}/{self.entry["size"]}'
        self.pos+=n;self.bytes+=n
        self.ranges.append([begin,n,hashlib.sha256(r.content).hexdigest()])
        return r.content

def projection(entry,columns,destination):
    receipt=destination.with_suffix('.json')
    if destination.exists() and receipt.exists():
        info=json.loads(receipt.read_text())
        assert info['source']==entry and info['columns']==columns and info['sha256']==sha(destination)
        return info
    if OFFLINE:raise FileNotFoundError(f'Offline projection missing: {destination}')
    remote=Remote(entry);pf=pq.ParquetFile(remote);writer=None;tmp=destination.with_suffix('.partial')
    try:
        for batch in pf.iter_batches(batch_size=65536,columns=columns,use_threads=False):
            guard()
            if writer is None:writer=pq.ParquetWriter(tmp,batch.schema,compression='zstd')
            writer.write_batch(batch)
        writer.close();writer=None;tmp.replace(destination)
    finally:
        if writer:writer.close()
    info={'source':entry,'columns':columns,'source_rows':pf.metadata.num_rows,'source_schema':str(pf.schema_arrow),'http_bytes':remote.bytes,'requested_ranges':remote.ranges,'sha256':sha(destination),'bytes':destination.stat().st_size}
    receipt.write_text(json.dumps(info,indent=2)+'\n');return info

def day(chain,date):
    layer=ROOT/chain/'layer2';ev=layer/'evidence/aws-selected';ev.mkdir(exist_ok=True)
    manifest=ev/f'{date}-network-validation.json';daily=ev/f'{date}-network-second.parquet'
    if manifest.exists() and daily.exists() and not RECOMPUTE:
        r=json.loads(manifest.read_text());assert r['output_sha256']==sha(daily);return r
    saved=json.loads(manifest.read_text()) if OFFLINE else None
    def entries_for(table):
        if saved is not None:
            return [x['source'] for x in saved['source_files'] if f'/{table}/' in x['source']['key']]
        return listing(f'{prefix}/{table}/date={date}/')
    prefix='v1.1/sonarx/base' if chain=='base' else 'v1.1/bnb'
    blockcols=['BLOCK_NUMBER','TIMESTAMP','BLOCK_HASH','BLOCK_PARENT_HASH','TRANSACTION_COUNT','GAS_USED','GAS_LIMIT','SIZE','BASE_FEE_PER_GAS','BLOB_GAS_USED'] if chain=='base' else ['number','timestamp','hash','parent_hash','transaction_count','gas_used','gas_limit','size','base_fee_per_gas','blob_gas_used']
    block_entries=entries_for('blocks');blocks=[];evidence=[]
    for j,e in enumerate(block_entries):
        p=ev/f'{date}-blocks-{j:03d}.parquet';evidence.append(projection(e,blockcols,p));blocks.append(pq.read_table(p).to_pandas())
    b=pd.concat(blocks,ignore_index=True);b.columns=['height','timestamp','hash','parent_hash','tx_count','gas_used','gas_limit','size','base_fee','blob_gas']
    for c in ['height','timestamp','tx_count','gas_used','gas_limit','size','base_fee','blob_gas']:
        assert b[c].notna().all(),(chain,date,c,'null block field');b[c]=b[c].astype('int64')
    b=b.sort_values('height').reset_index(drop=True)
    assert (np.diff(b.height)==1).all() and (np.diff(b.timestamp)>=0).all()
    assert np.array_equal(b.parent_hash.to_numpy()[1:],b.hash.to_numpy()[:-1])
    start=int(dt.datetime.fromisoformat(date).replace(tzinfo=dt.timezone.utc).timestamp())
    second=b.timestamp.to_numpy()-start
    assert second.min()>=0 and second.max()<86400
    # Adjacent block heights establish day boundaries; endpoint samples are checked separately by RPC.
    out=pd.DataFrame({'interval_start_utc':pd.to_datetime(np.arange(start,start+86400),unit='s',utc=True)})
    out['block_count']=np.bincount(second,minlength=86400)
    for c,name in [('tx_count','transaction_count'),('gas_used','gas_used'),('gas_limit','gas_limit'),('size','block_size_bytes'),('blob_gas','blob_gas_used')]:
        a=np.zeros(86400,dtype='int64');np.add.at(a,second,b[c].to_numpy());out[name]=a
    out['gas_utilization']=np.divide(out.gas_used,out.gas_limit,out=np.full(86400,np.nan),where=out.gas_limit>0)
    out['coverage_complete']=True
    extra={}
    if chain=='base':
        txcounts=b.tx_count.to_numpy();offset=np.r_[0,np.cumsum(txcounts)];seen=np.zeros(int(offset[-1]),dtype=bool)
        gas_check=np.zeros(len(b),dtype='int64');counts=np.zeros(len(b),dtype='int64')
        fees=np.zeros(86400,dtype=object);l1=np.zeros(86400,dtype=object);failedfee=np.zeros(86400,dtype=object)
        failed=np.zeros(86400,dtype='int64');paid=np.zeros(86400,dtype='int64');l1missing=np.zeros(86400,dtype='int64')
        columns=['BLOCK_NUMBER','TRANSACTION_INDEX','GAS_USED','EFFECTIVE_GAS_PRICE','L1_FEE','STATUS']
        entries=entries_for('receipts')
        for j,e in enumerate(entries):
            p=ev/f'{date}-receipts-{j:03d}.parquet';info=projection(e,columns,p);evidence.append(info)
            for batch in pq.ParquetFile(p).iter_batches(batch_size=65536):
                guard();d=batch.to_pandas();bi=d.BLOCK_NUMBER.to_numpy(dtype='int64')-int(b.height.iloc[0]);ti=d.TRANSACTION_INDEX.to_numpy(dtype='int64')
                assert (bi>=0).all() and (bi<len(b)).all() and (ti>=0).all() and (ti<txcounts[bi]).all()
                ix=offset[bi]+ti;assert len(np.unique(ix))==len(ix) and not seen[ix].any();seen[ix]=True
                gu=d.GAS_USED.to_numpy(dtype='int64');gp=d.EFFECTIVE_GAS_PRICE.to_numpy(dtype='int64');st=d.STATUS.to_numpy(dtype='int64')
                assert np.isin(st,[0,1]).all() and (gu>=0).all() and (gp>=0).all()
                sec=second[bi];ef=gu.astype(object)*gp.astype(object)
                np.add.at(counts,bi,1);np.add.at(gas_check,bi,gu);np.add.at(fees,sec,ef)
                np.add.at(failed,sec,(st==0).astype('int64'));np.add.at(paid,sec,(gp>0).astype('int64'));np.add.at(failedfee,sec,ef*(st==0))
                miss=d.L1_FEE.isna().to_numpy();np.add.at(l1missing,sec,miss.astype('int64'))
                # Null L1 fee on system/deposit receipts is preserved in missing-count metadata.
                lf=d.L1_FEE.map(lambda x:0 if pd.isna(x) else int(x)).to_numpy(dtype=object)
                assert all(x>=0 for x in lf);np.add.at(l1,sec,lf)
            print(json.dumps({'chain':chain,'date':date,'receipt_file':j+1,'files':len(entries),'rss_mb':round(psutil.Process().memory_info().rss/1e6)}),flush=True)
        assert seen.all() and np.array_equal(counts,txcounts) and np.array_equal(gas_check,b.gas_used.to_numpy())
        out['failed_transaction_count']=failed;out['successful_transaction_count']=out.transaction_count-failed;out['positive_effective_gas_price_count']=paid;out['l1_fee_missing_receipt_count']=l1missing
        table=pa.Table.from_pandas(out,preserve_index=False)
        for name,a in [('execution_fees_wei',fees),('l1_fees_reported_wei',l1),('execution_plus_reported_l1_fees_wei',fees+l1),('failed_execution_fees_wei',failedfee)]:
            table=table.append_column(name,pa.array([int(x) for x in a],type=pa.decimal128(38,0)))
        # The dataset has no operator-fee field; totals remain explicitly component subtotals.
        extra={'execution_fees_wei':str(sum(fees)),'l1_fees_reported_wei':str(sum(l1)),'l1_fee_missing_receipts':int(l1missing.sum()),'failed_transactions':int(failed.sum()),'positive_effective_gas_price_count':int(paid.sum()),'receipt_position_uniqueness_and_completeness':True,'receipt_gas_equals_every_block_header':True}
    else:table=pa.Table.from_pandas(out,preserve_index=False)
    table=table.replace_schema_metadata({b'source':b'AWS Public Blockchain Data',b'chain':chain.encode(),b'native_precision':b'block timestamp, aggregated into UTC seconds; not transaction arrival time',b'publication_status':b'local computation; not a new public release'})
    pq.write_table(table,daily,compression='zstd')
    result={'date':date,'chain':chain,'status':'Verified within AWS census; RPC checks separate','first_height':int(b.height.iloc[0]),'last_height':int(b.height.iloc[-1]),'first_hash':b.hash.iloc[0],'first_parent_hash':b.parent_hash.iloc[0],'last_hash':b.hash.iloc[-1],'first_timestamp':int(b.timestamp.iloc[0]),'last_timestamp':int(b.timestamp.iloc[-1]),'blocks':len(b),'transactions':int(b.tx_count.sum()),'gas_used':int(b.gas_used.sum()),'seconds_with_blocks':int((out.block_count>0).sum()),'rows':86400,'output_sha256':sha(daily),'output_bytes':daily.stat().st_size,'http_bytes':sum(e['http_bytes'] for e in evidence),'selected_bytes':sum(e['bytes'] for e in evidence),'source_files':evidence,'rss_at_day_completion_bytes':psutil.Process().memory_info().rss,**extra}
    manifest.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['source_files']}),flush=True);return result

def combine(chain):
    layer=ROOT/chain/'layer2';ev=layer/'evidence/aws-selected';target=layer/'output/aws_network_second.parquet';tmp=target.with_suffix('.partial');writer=None;results=[]
    try:
        for n in range(21):
            date=str(dt.date(2026,10,1)+dt.timedelta(days=n));r=day(chain,date)
            if results:
                assert r['first_height']==results[-1]['last_height']+1
                assert r['first_parent_hash']==results[-1]['last_hash']
            results.append(r);t=pq.read_table(ev/f'{date}-network-second.parquet')
            if chain=='base':
                # OP Stack repurposes this header field as DA footprint after Jovian.
                metadata=t.schema.metadata
                t=t.rename_columns(['header_blob_gas_used_raw' if c=='blob_gas_used' else c for c in t.column_names]).replace_schema_metadata(metadata)
            if writer is None:writer=pq.ParquetWriter(tmp,t.schema,compression='zstd')
            writer.write_table(t,row_group_size=86400)
        writer.close();writer=None;tmp.replace(target)
    finally:
        if writer:writer.close()
    summary={'chain':chain,'rows':21*86400,'blocks':sum(r['blocks'] for r in results),'transactions':sum(r['transactions'] for r in results),'gas_used':sum(r['gas_used'] for r in results),'http_bytes':sum(r['http_bytes'] for r in results),'selected_bytes':sum(r['selected_bytes'] for r in results),'output_bytes':target.stat().st_size,'output_sha256':sha(target),'daily_validation_files':[f'aws-selected/{r["date"]}-network-validation.json' for r in results],'contiguous_unique_height_and_parent_hash_chain':True,'memory_limit_bytes':2*1024**3}
    (layer/'evidence/aws-network-validation.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--chain',choices=['base','BSC'],required=True);a.add_argument('--day');a.add_argument('--offline',action='store_true');a.add_argument('--recompute',action='store_true');args=a.parse_args()
    OFFLINE=args.offline;RECOMPUTE=args.recompute
    if args.day:day(args.chain,args.day)
    else:combine(args.chain)
