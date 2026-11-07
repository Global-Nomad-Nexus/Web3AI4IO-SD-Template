#!/usr/bin/env python3
"""Independent Decimal event totals and full-column checks on completed pool output."""
from pathlib import Path
from decimal import Decimal
import json,hashlib,math
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[1]/'base/layer2'
SYNC='0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1'
SWAP='0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
def decode(data):return [int(data[k:k+64],16) for k in range(2,len(data),64)]
p=ROOT/'output/uniswap_v2_weth_usdc_pool_second.parquet';f=pq.ParquetFile(p)
assert f.metadata.num_rows==1814400 and f.metadata.num_row_groups==21
opening=json.loads((ROOT/'evidence/aws-pool-opening-probe.json').read_text());state=decode(opening['calls'][4]['response']['result'])[:2]
daily=[]
for n in range(21):
 date=f'2026-10-{n+1:02d}';d=f.read_row_group(n).to_pandas();events=json.loads((ROOT/f'evidence/aws-selected/{date}-pool-events.json').read_text())
 start=pd.Timestamp(date,tz='UTC');assert d.interval_start_utc.iloc[0]==start and len(d)==86400
 assert (d.interval_end_utc==d.interval_start_utc+pd.Timedelta(seconds=1)).all()
 reserve_changes={};expected_count=np.zeros(86400,dtype=int);vol0=Decimal(0);vol1=Decimal(0);fee0=Decimal(0);fee1=Decimal(0)
 exchange_count=np.zeros(86400,dtype=int);exchange0=Decimal(0);exchange1=Decimal(0)
 for event in sorted(events,key=lambda x:(x['BLOCK_NUMBER'],x['LOG_INDEX'])):
  sec=event['TIMESTAMP']-int(start.timestamp());assert 0<=sec<86400
  if event['TOPIC1'].lower()==SYNC:reserve_changes[sec]=decode(event['DATA'])
  elif event['TOPIC1'].lower()==SWAP:
   a,b,c,e=map(Decimal,decode(event['DATA']));expected_count[sec]+=1
   vol0+=(a+c)/Decimal(10**18);vol1+=(b+e)/Decimal(10**6)
   fee0+=a/Decimal(10**18)*Decimal('0.003');fee1+=b/Decimal(10**6)*Decimal('0.003')
   if (a>0 and e>0 and b==0 and c==0) or (b>0 and c>0 and a==0 and e==0):
    exchange_count[sec]+=1;exchange0+=(a+c)/Decimal(10**18);exchange1+=(b+e)/Decimal(10**6)
 # Independently check every stored reserve using intervals between successive Sync events.
 last=0
 for sec,newstate in sorted(reserve_changes.items()):
  if sec>last:
   assert all(int(x)==state[0] for x in d.reserve0_raw.iloc[last:sec])
   assert all(int(x)==state[1] for x in d.reserve1_raw.iloc[last:sec])
  state=newstate;last=sec
 assert all(int(x)==state[0] for x in d.reserve0_raw.iloc[last:])
 assert all(int(x)==state[1] for x in d.reserve1_raw.iloc[last:])
 np.testing.assert_array_equal(d.swap_count.to_numpy(),expected_count)
 np.testing.assert_array_equal(d.two_token_trade_count.to_numpy(),exchange_count)
 np.testing.assert_array_equal(d.other_swap_count.to_numpy(),expected_count-exchange_count)
 assert math.isclose(math.fsum(d.two_token_trade_volume_weth),float(exchange0),rel_tol=2e-14,abs_tol=1e-10)
 assert math.isclose(math.fsum(d.two_token_trade_volume_usdc),float(exchange1),rel_tol=2e-14,abs_tol=1e-10)
 for col,expected in [('swap_volume_weth',vol0),('swap_volume_usdc',vol1),('swap_input_fee_weth',fee0),('swap_input_fee_usdc',fee1)]:
  assert math.isclose(math.fsum(d[col]),float(expected),rel_tol=2e-14,abs_tol=1e-10),(date,col)
 np.testing.assert_allclose(d.reserve_weth,d.reserve0_raw.map(float)/1e18,rtol=1e-15,atol=1e-12)
 np.testing.assert_allclose(d.reserve_usdc,d.reserve1_raw.map(float)/1e6,rtol=1e-15,atol=1e-10)
 np.testing.assert_allclose(d.liquidity_usdc,d.reserve_weth*d.eth_price_usdc+d.reserve_usdc,rtol=2e-15,atol=1e-9)
 np.testing.assert_allclose(d.swap_input_fee_value_usdc,d.swap_input_fee_weth*d.eth_price_usdc+d.swap_input_fee_usdc,rtol=2e-15,atol=1e-10)
 price=pq.ParquetFile(ROOT/'output/eth_usdc_market_second.parquet').read_row_group(n,columns=['interval_start_utc','close']).to_pandas()
 assert d.interval_start_utc.equals(price.interval_start_utc)
 np.testing.assert_array_equal(d.eth_price_usdc,price.close)
 prior=json.loads((ROOT/f'evidence/aws-selected/{date}-pool-validation.json').read_text());assert state==decode(prior['rpc']['response']['result'])[:2]
 daily.append({'date':date,'rows':len(d),'swap_events':int(expected_count.sum()),'volume_usdc':str(vol1),'closing_reserves_rpc_match':True})
receipt={'status':'Verified','scope':'All 1814400 rows; all reserve states; exact event-count reconciliation; Decimal daily volume/fee controls; all market price joins; 21 historical closing-state checks','output_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'daily':daily}
(ROOT/'evidence/aws-pool-independent-validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
print({k:v for k,v in receipt.items() if k!='daily'})
