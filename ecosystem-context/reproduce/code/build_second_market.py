#!/usr/bin/env python3
"""Checksum-verified 1-second Binance context, bounded to one UTC day in memory."""
import argparse, datetime as dt, hashlib, io, json, pathlib, time, urllib.request, zipfile
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import psutil

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPECS=[('solana','SOLUSDT',24,'sol_usdt'),('base','ETHUSDC',21,'eth_usdc'),('BSC','BNBUSDC',21,'bnb_usdc')]
COLS=['open_us','open','high','low','close','volume_base','close_us','volume_quote','trade_count','taker_buy_volume_base','taker_buy_volume_quote','ignore']

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def guard():
    if psutil.Process().memory_info().rss>2*1024**3 or psutil.virtual_memory().available<1024**3:
        raise MemoryError('STOP: ask user before continuing; memory budget reached')
def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=60) as r:return r.read()
        except Exception:
            if attempt==2:raise
            time.sleep(2**attempt)

def build(chain,pair,ndays,stem,offline=False):
    layer=ROOT/chain/'layer2'; raw=layer/'evidence/binance_vision';raw.mkdir(exist_ok=True)
    target=layer/'output'/f'{stem}_market_second.parquet'
    tmp=target.with_suffix('.parquet.partial')
    hourly=pd.read_csv(layer/'output'/f'{stem}_binance_hourly.csv')
    writer=None;tail=pd.Series(dtype=float);previous=None;receipts=[];vol_checks=[]
    total=empty=0;peak=0
    try:
        for n in range(ndays):
            guard();day=dt.date(2026,10,1)+dt.timedelta(days=n);name=f'{pair}-1s-{day}.zip'
            url=f'https://data.binance.vision/data/spot/daily/klines/{pair}/1s/{name}'
            arc=raw/name;check=raw/(name+'.CHECKSUM')
            for p,u in [(arc,url),(check,url+'.CHECKSUM')]:
                if not p.exists():
                    if offline:raise FileNotFoundError(p)
                    b=get(u);p.write_bytes(b)
            checksum,filename=check.read_text().split()
            assert checksum==sha(arc) and filename.lstrip('*')==name
            with zipfile.ZipFile(arc) as z:
                assert z.namelist()==[name[:-4]+'.csv']
                with z.open(z.namelist()[0]) as f:d=pd.read_csv(f,header=None,names=COLS)
            start=int(dt.datetime.combine(day,dt.time(),dt.timezone.utc).timestamp())
            assert len(d)==86400 and np.array_equal(d.open_us.to_numpy(),np.arange(start,start+86400,dtype='int64')*1000000)
            assert (d.close_us==d.open_us+999999).all()
            assert ((d.low>0)&(d.low<=d[['open','close']].min(axis=1))&(d.high>=d[['open','close']].max(axis=1))).all()
            assert (d[['volume_base','volume_quote','trade_count','taker_buy_volume_base','taker_buy_volume_quote']]>=0).all().all()
            close=d.close.to_numpy();prev=np.concatenate(([np.nan if previous is None else previous],close[:-1]))
            ret=pd.Series(np.log(close/prev));simple=close/prev-1
            combined=pd.concat([tail,ret],ignore_index=True)
            vol=combined.rolling(86400,min_periods=86400).std(ddof=1).iloc[-86400:].to_numpy()
            rv=np.sqrt(combined.pow(2).rolling(86400,min_periods=86400).sum().iloc[-86400:].to_numpy())
            # Independent checks across daily boundaries and at the first valid window.
            for j in [0,1,43200,86399]:
                k=len(tail)+j;window=combined.iloc[max(0,k-86399):k+1].to_numpy()
                if len(window)==86400 and np.isfinite(window).all():
                    np.testing.assert_allclose(vol[j],np.std(window,ddof=1),rtol=1e-10,atol=2e-15)
                    np.testing.assert_allclose(rv[j],np.sqrt(np.sum(window**2)),rtol=1e-10,atol=2e-15)
            tail=combined.iloc[-86399:].copy();previous=close[-1]
            # All source hourly candles are independent aggregate controls.
            for h in range(24):
                x=d.iloc[h*3600:(h+1)*3600];traded=x[x.trade_count>0];r=hourly.iloc[n*24+h]
                q='usdt' if pair.endswith('USDT') else 'usdc'
                assert len(traded)>0
                vals=[traded.open.iloc[0],traded.high.max(),traded.low.min(),traded.close.iloc[-1]]
                np.testing.assert_allclose(vals,[r[f'{c}_{q}'] for c in ['open','high','low','close']],rtol=0,atol=1e-9)
                vb='volume_sol' if chain=='solana' else 'volume_base_asset';vq='volume_usdt' if chain=='solana' else 'quote_volume_usdc'
                np.testing.assert_allclose([x.volume_base.sum(),x.volume_quote.sum()],[r[vb],r[vq]],rtol=1e-10,atol=1e-7)
                assert int(x.trade_count.sum())==int(r.trade_count)
            out=d.drop(columns=['open_us','close_us','ignore']).copy()
            out.insert(0,'interval_start_utc',pd.to_datetime(d.open_us,unit='us',utc=True))
            out.insert(1,'available_at_utc',out.interval_start_utc+pd.Timedelta(seconds=1))
            out['has_trade']=out.trade_count>0;out['simple_return_1s']=simple;out['log_return_1s']=ret
            out['rolling_24h_return_std']=vol;out['realized_volatility_24h']=rv
            out['return_observations_24h']=np.where(np.isfinite(vol),86400,0).astype('int32')
            table=pa.Table.from_pandas(out,preserve_index=False)
            metadata={b'pair':pair.encode(),b'quote_asset':q.upper().encode(),b'source':b'Binance Vision',b'license':b'CC BY-NC-SA 4.0; Binance Vision dataset terms',b'transformation':b'1s candles; close log/simple returns; trailing 86400-return sample std and sqrt(sum(r^2)); not annualized'}
            table=table.replace_schema_metadata(metadata)
            if writer is None:writer=pq.ParquetWriter(tmp,table.schema,compression='zstd')
            writer.write_table(table,row_group_size=86400)
            total+=len(d);empty+=int((d.trade_count==0).sum());peak=max(peak,psutil.Process().memory_info().rss)
            receipts.append({'date':str(day),'url':url,'sha256':checksum,'zip_bytes':arc.stat().st_size,'rows':len(d),'zero_trade_seconds':int((d.trade_count==0).sum())})
            print(json.dumps({'chain':chain,'day':str(day),'rows':total,'rss_mb':round(peak/1e6)}),flush=True)
        writer.close();writer=None;tmp.replace(target)
    finally:
        if writer:writer.close()
    result={'status':'Verified','pair':pair,'rows':total,'nonmissing_returns':total-1,'nonmissing_24h_volatility':total-86400,'zero_trade_seconds':empty,'output':str(target.relative_to(layer)),'output_bytes':target.stat().st_size,'sha256':sha(target),'source_archives':receipts,'hourly_controls_checked':ndays*24,'independent_volatility_checks':'NumPy sample std and sum of squared returns at four offsets per complete day','max_observed_rss_bytes':peak,'definitions':{'return':'ln(close[t]/close[t-1]); also simple close ratio minus one','volatility':'sample std(ddof=1) of trailing 86400 1s log returns; no annualization','realized_volatility':'sqrt(sum of squared trailing 86400 1s log returns)); no annualization','empty_candles':'source close retained; has_trade=false; not new executions','timing':'available_at_utc is candle completion, not actual archive publication time','initial_missing':'no pre-window input; first return and first 86400 volatility rows null'},'source_terms':'https://data.binance.vision/Binance_Vision-Terms_of_Use.pdf'}
    (layer/'evidence/market-second-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--offline',action='store_true');p.add_argument('--chain');a=p.parse_args()
    for s in SPECS:
        if a.chain is None or a.chain==s[0]:build(*s,offline=a.offline)
