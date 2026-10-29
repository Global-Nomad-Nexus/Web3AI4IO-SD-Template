"""Six bounded parser/parameter probes; no formal range collection or freeze."""
from core import *
from collectors import check_pump_idl,validate_stream
from markets import normalize_price
from urllib.parse import urlencode

def run(root,cfg):
    cfg={**cfg,'budgets':{**cfg['budgets'],'timeout_seconds':10,'max_attempts_per_request':1}}
    c=Client(root,cfg,True,request_cap=6);results=[]
    def record(name,fn):
        try:result=fn();results.append({'probe':name,'status':'passed','detail':result})
        except Exception as e:results.append({'probe':name,'status':'unavailable_or_incompatible','error':str(e)})
        save(Path(root)/'reports/adapter_smoke.json',{'results':results,'requests':c.calls,'formal_P3_started':False,'tested_at_utc':now()})
    def anchor():
        end=1792022400
        d,m=c.rpc(cfg['sources']['vibe'],'getTransactionsForAddress',[AUTHORITY,{'transactionDetails':'full','sortOrder':'asc','limit':1,'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':1,'filters':{'blockTime':{'gte':end}}}],'adapter_post_window_anchor')
        rows=d.get('data',[])
        if len(rows)!=1 or rows[0]['blockTime']<end or not isinstance(rows[0]['transactionIndex'],int):raise Halt('Post-window anchor/filter/order schema incompatible')
        return {'slot':rows[0]['slot'],'block_time':iso(rows[0]['blockTime']),'raw_ref':m['raw_ref']}
    record('Vibe_post_window_anchor',anchor)
    def price():
        asset=next(r['asset_id_raw'] for r in read_csv(PARENT/'processed/pm_outcomes.csv') if r['outcome_label']=='Yes')
        a,b=1791414000,1791417600;d,m=c.json(cfg['sources']['history']+'?'+urlencode({'token_id':asset,'start':a,'end':b,'limit':1}),label='adapter_one_price_history_point')
        points=d.get('data',[])
        if not points:raise Halt('No historical point in one-hour smoke interval')
        p=normalize_price(points[0],'smoke_outcome','smoke_snapshot',m,a,b)
        return {'source_timestamp':p['source_timestamp_utc'],'resolution_seconds':p['resolution_seconds'],'raw_ref':m['raw_ref']}
    record('Polymarket_history_schema',price)
    def idl():
        params={'path':'idl/pump.json','until':'2026-10-15T00:00:00Z','per_page':1}
        d,m=c.json('https://api.github.com/repos/pump-fun/pump-public-docs/commits?'+urlencode(params),label='adapter_historical_IDL_commit')
        if not isinstance(d,list) or not d:raise Halt('No historical IDL revision')
        revision=d[0]['sha'];doc,dm=c.json('https://raw.githubusercontent.com/pump-fun/pump-public-docs/'+revision+'/idl/pump.json',label='adapter_historical_IDL_prefix')
        check_pump_idl(doc);return {'revision':revision,'raw_ref':dm['raw_ref']}
    record('Pump_historical_IDL_lookup_and_prefix',idl)
    for endpoint in ['stream','finalized-stream']:
        def sqd(endpoint=endpoint):
            n=126344214;q={'type':'evm','fromBlock':n,'toBlock':n,'fields':{'block':{'number':True,'hash':True,'timestamp':True}},'includeAllBlocks':True}
            body,m=c.request('https://portal.sqd.dev/datasets/binance-mainnet/'+endpoint,q,'adapter_one_BSC_block_'+endpoint)
            data=[json.loads(x) for x in body.splitlines() if x.strip()];validate_stream(data,n,n);return {'block_rows':len(data),'raw_ref':m['raw_ref']}
        record('SQD_'+endpoint,sqd)
    return {'status':'passed' if all(r['status']=='passed' for r in results) else 'partial_live_capability','results':results,'requests':c.calls,'formal_P3_started':False}

if __name__=='__main__':
    import argparse
    from pipeline import guard_output
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(guard_output(a.output),load(ROOT/'configs/protocol.json')),ensure_ascii=False,indent=2))
