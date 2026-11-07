#!/usr/bin/env python3
"""AWS logs -> one explicitly scoped Base Uniswap V2 WETH/USDC pool.

Scans address column first, fetches event columns only for matching row groups.
Opening reserves and daily end states are checked with Base official RPC.
"""
from build_aws_network_second import *
import concurrent.futures, decimal, gc
import pyarrow.compute as pc
import build_aws_network_second as network_io
pa.set_memory_pool(pa.system_memory_pool())
# Eight small projections are bounded at 4 GiB total; stop for user input if reached.
network_io.MEMORY_LIMIT_BYTES=4*1024**3

LAYER=ROOT/'base/layer2';EV=LAYER/'evidence/aws-selected'
OPENING=json.loads((LAYER/'evidence/aws-pool-opening-probe.json').read_text())
POOL=OPENING['pool']
SYNC='0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1'
SWAP='0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
OFFLINE=False

def scan(entry):
    remote=Remote(entry);pf=pq.ParquetFile(remote);events=[];matched_groups=0
    for rg in range(pf.metadata.num_row_groups):
        addresses=pf.read_row_group(rg,columns=['ADDRESS'],use_threads=False)['ADDRESS']
        match=pc.equal(pc.utf8_lower(addresses),POOL)
        if not pc.any(match).as_py():continue
        matched_groups+=1
        t=pf.read_row_group(rg,columns=['BLOCK_NUMBER','TIMESTAMP','TRANSACTION_INDEX','LOG_INDEX','TOPIC1','DATA'],use_threads=False).filter(match)
        for r in t.to_pylist():
            events.append({k:(int(v) if isinstance(v,decimal.Decimal) else v) for k,v in r.items()})
        del t,addresses,match
    info={'source':entry,'rows_scanned':pf.metadata.num_rows,'matched_row_groups':matched_groups,'pool_events':len(events),'http_bytes':remote.bytes,'requested_ranges':remote.ranges}
    pf.close();del pf,remote;gc.collect();pa.default_memory_pool().release_unused()
    return events,info

def collect_day(date):
    manifest=EV/f'{date}-pool-log-scan.json';out=EV/f'{date}-pool-events.json'
    if OFFLINE:
        m=json.loads(manifest.read_text());assert m['events_sha256']==sha(out)
        return json.loads(out.read_text()),m
    entries=listing(f'v1.1/sonarx/base/logs/date={date}/')
    if manifest.exists() and out.exists():
        m=json.loads(manifest.read_text());assert m['events_sha256']==sha(out) and [r['source'] for r in m['source_files']]==entries
        return json.loads(out.read_text()),m
    events=[];infos=[]
    # Per-object checkpoint avoids repeating multi-gigabyte scans after interruption.
    jobs=[]
    for j,e in enumerate(entries):
        cp=EV/f'{date}-pool-log-{j:03d}.json'
        if cp.exists():
            c=json.loads(cp.read_text());assert c['info']['source']==e
            events.extend(c['events']);infos.append(c['info'])
        else:jobs.append((j,e,cp))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures={executor.submit(scan,e):(j,e,cp) for j,e,cp in jobs}
        for future in concurrent.futures.as_completed(futures):
            j,e,cp=futures[future];new,info=future.result();cp.write_text(json.dumps({'events':new,'info':info},indent=2)+'\n')
            events.extend(new);infos.append(info)
            print(json.dumps({'date':date,'log_files_done':len(infos),'files':len(entries),'events':len(events),'http_mb':round(sum(x['http_bytes'] for x in infos)/1e6),'rss_mb':round(psutil.Process().memory_info().rss/1e6)}),flush=True)
    infos.sort(key=lambda x:x['source']['key']);events.sort(key=lambda x:(x['BLOCK_NUMBER'],x['LOG_INDEX']))
    assert len({(r['BLOCK_NUMBER'],r['LOG_INDEX']) for r in events})==len(events)
    out.write_text(json.dumps(events,indent=2)+'\n');m={'date':date,'pool':POOL,'source_files':infos,'events':len(events),'http_bytes':sum(x['http_bytes'] for x in infos),'events_sha256':sha(out)}
    manifest.write_text(json.dumps(m,indent=2)+'\n');return events,m

def rpc(method,params):
    payload={'jsonrpc':'2.0','id':1,'method':method,'params':params}
    for attempt in range(3):
        try:
            r=SESSION.post('https://mainnet.base.org',json=payload,timeout=60);r.raise_for_status();data=r.json();assert 'result' in data,data
            return data['result'],{'request':payload,'response':data}
        except Exception:
            if attempt==2:raise
            time.sleep(2**attempt)

def words(data):
    s=data[2:] if data.startswith('0x') else data
    assert len(s)%64==0
    return [int(s[k:k+64],16) for k in range(0,len(s),64)]

def build(limit=21):
    opening=words(OPENING['calls'][4]['response']['result']);r0,r1=opening[:2]
    target=LAYER/'output/uniswap_v2_weth_usdc_pool_second.parquet';tmp=target.with_suffix('.partial');writer=None;summary=[]
    try:
        for n in range(limit):
            guard();date=str(dt.date(2026,10,1)+dt.timedelta(days=n));events,m=collect_day(date)
            bf=EV/f'{date}-blocks-000.parquet'
            if not bf.exists():
                if OFFLINE:raise FileNotFoundError(bf)
                e=listing(f'v1.1/sonarx/base/blocks/date={date}/');assert len(e)==1
                projection(e[0],['BLOCK_NUMBER','TIMESTAMP','BLOCK_HASH','BLOCK_PARENT_HASH','TRANSACTION_COUNT','GAS_USED','GAS_LIMIT','SIZE','BASE_FEE_PER_GAS','BLOB_GAS_USED'],bf)
            blocks=pq.read_table(bf,columns=['BLOCK_NUMBER','TIMESTAMP','BLOCK_HASH']).to_pandas().sort_values('BLOCK_NUMBER')
            bm={int(a):int(b) for a,b in zip(blocks.BLOCK_NUMBER,blocks.TIMESTAMP)}
            start=int(dt.datetime.fromisoformat(date).replace(tzinfo=dt.timezone.utc).timestamp());day_end=int(blocks.BLOCK_NUMBER.iloc[-1])
            syncs={};swaps={};sync_count=swap_count=0
            for e in events:
                sec=e['TIMESTAMP']-start;assert 0<=sec<86400 and bm[e['BLOCK_NUMBER']]==e['TIMESTAMP']
                topic=e['TOPIC1'].lower()
                if topic==SYNC:
                    values=words(e['DATA']);assert len(values)==2 and all(0<=x<2**112 for x in values)
                    syncs[sec]=values;sync_count+=1
                elif topic==SWAP:
                    values=words(e['DATA']);assert len(values)==4
                    swaps.setdefault(sec,[]).append(values);swap_count+=1
            reserve0=[];reserve1=[];trade_count=np.zeros(86400,dtype='int32');vol0=np.zeros(86400);vol1=np.zeros(86400);fee0=np.zeros(86400);fee1=np.zeros(86400)
            exchange_count=np.zeros(86400,dtype='int32');exchange_vol0=np.zeros(86400);exchange_vol1=np.zeros(86400)
            for sec in range(86400):
                if sec in syncs:r0,r1=syncs[sec]
                reserve0.append(r0);reserve1.append(r1)
                for a0i,a1i,a0o,a1o in swaps.get(sec,[]):
                    trade_count[sec]+=1;vol0[sec]+=(a0i+a0o)/1e18;vol1[sec]+=(a1i+a1o)/1e6
                    fee0[sec]+=a0i/1e18*0.003;fee1[sec]+=a1i/1e6*0.003
                    if (a0i>0 and a1o>0 and a1i==0 and a0o==0) or (a1i>0 and a0o>0 and a0i==0 and a1o==0):
                        exchange_count[sec]+=1;exchange_vol0[sec]+=(a0i+a0o)/1e18;exchange_vol1[sec]+=(a1i+a1o)/1e6
            if OFFLINE:
                previous=json.loads((EV/f'{date}-pool-validation.json').read_text());check=previous['rpc'];end=check['response']['result']
                assert check['request']['params']==[{'to':POOL,'data':'0x0902f1ac'},hex(day_end)]
            else:end,check=rpc('eth_call',[{'to':POOL,'data':'0x0902f1ac'},hex(day_end)])
            assert words(end)[:2]==[r0,r1],(date,'AWS Sync replay does not match official historical closing reserves')
            prices=pq.ParquetFile(LAYER/'output/eth_usdc_market_second.parquet').read_row_group(n,columns=['interval_start_utc','available_at_utc','close']).to_pandas()
            assert len(prices)==86400
            state0=np.array(reserve0,dtype='float64')/1e18;state1=np.array(reserve1,dtype='float64')/1e6
            d=pd.DataFrame({'interval_start_utc':prices.interval_start_utc,'interval_end_utc':prices.available_at_utc,'reserve_weth':state0,'reserve_usdc':state1,'eth_price_usdc':prices.close,'liquidity_usdc':state0*prices.close+state1,'swap_count':trade_count,'swap_volume_weth':vol0,'swap_volume_usdc':vol1,'swap_input_fee_weth':fee0,'swap_input_fee_usdc':fee1,'swap_input_fee_value_usdc':fee0*prices.close+fee1,'has_reserve_update':[sec in syncs for sec in range(86400)]})
            d['two_token_trade_count']=exchange_count;d['other_swap_count']=trade_count-exchange_count
            d['two_token_trade_volume_weth']=exchange_vol0;d['two_token_trade_volume_usdc']=exchange_vol1
            t=pa.Table.from_pandas(d,preserve_index=False)
            t=t.append_column('reserve0_raw',pa.array(reserve0,type=pa.decimal128(38,0))).append_column('reserve1_raw',pa.array(reserve1,type=pa.decimal128(38,0)))
            t=t.replace_schema_metadata({b'pool':POOL.encode(),b'protocol':b'Uniswap V2 on Base',b'valuation':b'WETH reserves * Binance ETH/USDC second close + USDC reserves; USDC, not USD',b'fees':b'0.3% of gross token inputs per canonical V2 Swap; not protocol revenue',b'scope':b'one pool; not chain TVL or chain DEX volume'})
            if writer is None:writer=pq.ParquetWriter(tmp,t.schema,compression='zstd')
            writer.write_table(t,row_group_size=86400)
            validation={'date':date,'sync_events':sync_count,'swap_events':swap_count,'closing_block':day_end,'closing_reserves_match_rpc':True,'rpc':check,'http_bytes':m['http_bytes'],'raw_reserve0_end':str(r0),'raw_reserve1_end':str(r1),'swap_volume_usdc':float(vol1.sum()),'events_sha256':m['events_sha256']}
            validation['two_token_trade_events']=int(exchange_count.sum());validation['other_swap_events']=int((trade_count-exchange_count).sum())
            (EV/f'{date}-pool-validation.json').write_text(json.dumps(validation,indent=2)+'\n');summary.append(validation)
            del prices,t,d,blocks;gc.collect();pa.default_memory_pool().release_unused()
            print(json.dumps({'date':date,'pool_day_verified':True,'swaps':swap_count,'syncs':sync_count}),flush=True)
        writer.close();writer=None
        if limit==21:tmp.replace(target)
    finally:
        if writer:writer.close()
    if limit==21:
        result={'pool':POOL,'rows':limit*86400,'output_bytes':target.stat().st_size,'output_sha256':sha(target),'days':summary,'opening_evidence':'aws-pool-opening-probe.json','source_scope':'AWS full target-day log listings plus Base historical getReserves boundary checks','publication':'local research only; AWS dataset reuse unresolved; Binance derivatives retain CC BY-NC-SA conditions'}
        (LAYER/'evidence/aws-pool-validation.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--days',type=int,default=21);a.add_argument('--offline',action='store_true');args=a.parse_args();OFFLINE=args.offline;build(args.days)
