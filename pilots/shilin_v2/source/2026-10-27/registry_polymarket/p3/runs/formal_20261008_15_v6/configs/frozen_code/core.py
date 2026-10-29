"""P3 evidence, budgets and immutable run configuration. Import has no I/O."""
from __future__ import annotations
import contextlib, csv, gzip, hashlib, json, math, os, re, shutil, time
import urllib.error, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
P2 = PARENT / 'p2'
PROJECT = PARENT.parents[1]
LEGACY = PROJECT / '1021/scientific-data-essential/data/7day-72h-20261008-release'
CHAINS = ['solana:mainnet', 'eip155:8453', 'eip155:56']
PLATFORMS = dict(zip(CHAINS, ['pump.fun', 'clanker', 'four.meme']))
AUTHORITY = 'TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
PROGRAM = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def epoch(value):
    if not isinstance(value,str) or not value.endswith(('Z','+00:00')): raise ValueError('UTC timezone required')
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def iso(value): return datetime.fromtimestamp(value,timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def sid(*values):
    # Preserve P2 event identifiers, whose positional arguments use ordered JSON.
    return hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()[:32]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def load(path,default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default
def atomic(path,body):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
    try:
        with tmp.open('wb') as f: f.write(body);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()
def save(path,value): atomic(path,(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode())
def read_csv(path):
    if not Path(path).exists():return []
    with Path(path).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def iter_csv(path):
    with Path(path).open(newline='',encoding='utf-8') as f:yield from csv.DictReader(f)
def write_csv(path,rows,fields=None):
    rows=list(rows);fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    if not fields:raise ValueError('Empty tables require explicit columns')
    import io
    f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    atomic(path,f.getvalue().encode())
def stream_csv(path,rows,fields):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
    try:
        with tmp.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
def append_json(path,row):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(canonical(row)+'\n');f.flush()
def read_body(path):
    p=Path(path);body=p.read_bytes();return gzip.decompress(body) if p.suffix=='.gz' else body
def ref(path,root):return os.path.relpath(Path(path).resolve(),Path(root).resolve())
def resolve(root,value):
    # Only the path prefix is a file reference; fragments identify source rows.
    return (Path(root)/value.split('#',1)[0]).resolve()
def token_id(chain,address):
    if chain.startswith('eip155:'):
        if not re.fullmatch(r'0x[0-9a-fA-F]{40}',address):raise ValueError('Invalid EVM address')
        address=address.lower()
    elif chain=='solana:mainnet':
        if not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}',address):raise ValueError('Invalid Solana address')
    else:raise ValueError('Unknown chain')
    return chain+':token:'+address
def utc_days(start,end):
    a,b=epoch(start),epoch(end)
    if not a<b or a%86400 or b%86400:raise ValueError('Require nonempty whole UTC days')
    return [iso(t)[:10] for t in range(int(a),int(b),86400)]
def day_window(day):
    t=int(epoch(day+'T00:00:00Z'));return t,t+86400
def truth(value):return value is True or value=='True' or value=='true'

class Halt(RuntimeError):
    """A resumable budget, source, coverage or evidence stop, never success."""

@contextlib.contextmanager
def run_lock(root):
    path=Path(root)/'.run.lock';path.parent.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise Halt('Run is locked; inspect PID before explicitly clearing a stale lock: '+str(path))
    try:
        os.write(fd,canonical({'pid':os.getpid(),'started_at':now()}).encode());os.close(fd);yield
    finally:path.unlink(missing_ok=True)

def check_config(cfg):
    utc_days(cfg['candidate_start_utc'],cfg['candidate_end_utc'])
    if cfg['chains']!=CHAINS:raise ValueError('All three explicit chain namespaces required')
    if cfg['lifecycle_enabled'] or cfg['common_cutoff_utc'] is not None:raise ValueError('P3 lifecycle must remain disabled')
    if cfg['price']['primary_max_age_hours']!=24 or cfg['price']['sensitivity_hours']!=[12,48]:raise ValueError('Unexpected price policy; version the protocol first')
    for k,v in cfg['budgets'].items():
        if not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0:raise ValueError('Invalid positive budget '+k)
    return cfg

READ_RPC={'getBlockTime','getBlocks','getBlock','getSignaturesForAddress','getTransactionsForAddress','getTransaction','getSlot','eth_getLogs','eth_getBlockByNumber','eth_getTransactionReceipt','eth_blockNumber','eth_getCode'}
ALLOWED_HOSTS={'api.mainnet.solana.com','api.mainnet-beta.solana.com','base-rpc.publicnode.com','mainnet.base.org','bsc-dataseed.bnbchain.org','public.rpc.solanavibestation.com','crypto-clickhouse.clickhouse.com','portal.sqd.dev','gamma-api.polymarket.com','data-api.polymarket.com','raw.githubusercontent.com','api.github.com'}

class Client:
    """Bounded public read client. Every failed attempt retained; cache hash checked."""
    def __init__(self,root,cfg,online=False,request_cap=None,transport=None,sleeper=time.sleep):
        self.root=Path(root);self.cfg=cfg;self.online=online;self.transport=transport;self.sleep=sleeper
        self.calls=0;self.elements=0;self.cap=request_cap or cfg['budgets']['requests_per_invocation'];self.next_start=0.
        self.started=time.monotonic();self.stored=sum(p.stat().st_size for p in (self.root/'raw').glob('*.body.gz')) if (self.root/'raw').exists() else 0
    def _guard(self,url,payload):
        from urllib.parse import urlparse
        u=urlparse(url)
        if u.scheme!='https' or u.hostname not in ALLOWED_HOSTS or u.password:raise Halt('Unapproved public source URL')
        if isinstance(payload,(dict,list)):
            for q in payload if isinstance(payload,list) else [payload]:
                if 'method' in q and q['method'] not in READ_RPC:raise Halt('Only allowlisted read RPC methods permitted')
    def request(self,url,payload=None,label='',raw_sql=None):
        self._guard(url,payload);key=digest([url,payload,raw_sql]);mp=self.root/'raw'/(key+'.meta.json')
        m=load(mp)
        if m and m.get('ok'):
            p=resolve(self.root,m['raw_ref'])
            if sha(p)!=m['sha256']:raise Halt('Cached raw hash mismatch: '+str(p))
            return read_body(p),m
        if not self.online:raise Halt('Offline cache miss: '+label)
        budget=self.cfg['budgets'];rate=self.cfg['rates'];last=None
        for attempt in range(int(budget['max_attempts_per_request'])):
            if self.calls>=self.cap:raise Halt('Request budget reached; resume from saved checkpoint')
            units=len(payload) if isinstance(payload,list) else 1
            if self.elements+units>budget['rpc_elements_per_invocation']:raise Halt('RPC element budget reached')
            if time.monotonic()-self.started>budget['wall_seconds_per_invocation']:raise Halt('Invocation wall-time budget reached')
            self.sleep(max(0,self.next_start-time.monotonic()));started=now();clock=time.monotonic()
            self.calls+=1;self.elements+=units;body=b'';status=None;headers={};error=''
            try:
                if self.transport:status,headers,body=self.transport(url,payload,raw_sql)
                else:
                    data=raw_sql.encode() if raw_sql is not None else (None if payload is None else canonical(payload).encode())
                    req=urllib.request.Request(url,data=data,headers={'User-Agent':'Shilin-P3-Research/1.0','Accept':'application/json,application/x-ndjson','Accept-Encoding':'gzip','Content-Type':'text/plain' if raw_sql is not None else 'application/json'})
                    with urllib.request.urlopen(req,timeout=budget['timeout_seconds']) as response:
                        status=response.status;headers=dict(response.headers);body=response.read(int(budget['max_response_bytes'])+1)
                if len(body)>budget['max_response_bytes']:raise Halt('Response cap exceeded; split query')
                if next((v for k,v in headers.items() if k.lower()=='content-encoding'),'').lower()=='gzip':
                    import io
                    with gzip.GzipFile(fileobj=io.BytesIO(body)) as f:body=f.read(int(budget['max_response_bytes'])+1)
                if len(body)>budget['max_response_bytes']:raise Halt('Decoded response cap exceeded')
            except urllib.error.HTTPError as e:status=e.code;headers=dict(e.headers);body=e.read(1000000);error=str(e)
            except Halt:raise
            except Exception as e:error=type(e).__name__+': '+str(e)
            if status!=200:error=error or 'HTTP '+str(status)
            try:
                data=json.loads(body)
                for item in data if isinstance(data,list) else [data]:
                    if isinstance(item,dict) and item.get('error'):error=error or canonical(item['error'])
            except (ValueError,UnicodeDecodeError):pass
            stored=gzip.compress(body,mtime=0)
            if self.stored+len(stored)>budget['max_raw_bytes']:raise Halt('Raw storage budget reached')
            path=self.root/'raw'/(key+'-'+str(time.time_ns())+'.body.gz');atomic(path,stored);self.stored+=len(stored)
            m={'request_id':key,'url':url,'payload':payload,'sql':raw_sql,'label':label,'attempt':attempt+1,'started_at_utc':started,'retrieved_at_utc':now(),'elapsed_seconds':round(time.monotonic()-clock,4),'http_status':status,'ok':status==200 and not error,'error':error,'raw_ref':ref(path,self.root),'sha256':sha(path),'decoded_sha256':hashlib.sha256(body).hexdigest(),'saved_bytes':len(body),'stored_bytes':len(stored),'response_headers':headers,'rpc_elements':units,'access':'public_no_private_credentials','raw_redistribution_status':'not_reviewed_local_only'}
            save(mp,m);append_json(self.root/'provenance/requests.jsonl',m);last=(body,m)
            gap=max(rate['min_seconds_between_requests'],units*rate['min_seconds_per_rpc_element'])
            self.next_start=time.monotonic()+gap
            if m['ok']:return body,m
            # Long Retry-After is saved; stop now instead of ignoring the server.
            retry=next((v for k,v in headers.items() if k.lower()=='retry-after'),None)
            try:delay=float(retry) if retry is not None else min(2**(attempt+1),20)
            except ValueError:
                from email.utils import parsedate_to_datetime
                delay=max(0,parsedate_to_datetime(retry).timestamp()-time.time())
            if status not in [None,429,502,503,504,529] or delay>budget['max_inline_backoff_seconds']:break
            self.next_start=max(self.next_start,time.monotonic()+delay)
        raise Halt('Source request failed; evidence saved: '+(last[1]['error'] if last else label))
    def json(self,url,payload=None,label=''):
        b,m=self.request(url,payload,label)
        try:return json.loads(b),m
        except (ValueError,UnicodeDecodeError):raise Halt('Invalid JSON response: '+label)
    def rpc(self,url,method,params,label=''):
        d,m=self.json(url,{'jsonrpc':'2.0','id':1,'method':method,'params':params},label or method)
        if not isinstance(d,dict) or 'result' not in d or d['result'] is None:raise Halt('Missing RPC result: '+method)
        return d['result'],m

def default_config():
    return {'protocol_version':'registry_pm_p3_v1','status':'prepared_waiting_for_user_start','candidate_start_utc':'2026-10-08T00:00:00Z','candidate_end_utc':'2026-10-15T00:00:00Z','formal_window_frozen':False,'chains':CHAINS,'lifecycle_enabled':False,'common_cutoff_utc':None,'legacy_cohort':'legacy_7day_20261008','reuse_validated_P2_day':True,'random_seed':20261027,
      'scope':'named Pump create/create_v2; six pinned Clanker factories; Four.meme V2 only; no whole-chain census',
      'price':{'primary_max_age_hours':24,'sensitivity_hours':[12,48],'strict_before':True,'include_zero_resolution':False,'scalar_definition':'unconfirmed_API_scalar','feature_readiness':'retrospective_demonstration_only'},
      'budgets':{'requests_per_invocation':6000,'rpc_elements_per_invocation':30000,'wall_seconds_per_invocation':21600,'max_response_bytes':64000000,'max_raw_bytes':16000000000,'timeout_seconds':30,'max_attempts_per_request':3,'max_inline_backoff_seconds':30,'max_index_pages_per_day':200,'max_vibe_pages_per_day':2000,'max_history_pages_per_outcome':16,'max_search_pages_per_term_state':3,'max_markets_per_category':12,'max_history_outcomes':120,'history_chunk_days':3,'disk_reserve_bytes':2000000000},
      'rates':{'min_seconds_between_requests':0.5,'min_seconds_per_rpc_element':0.3},
      'sources':{'solana_rpc':'https://api.mainnet.solana.com','vibe':'https://public.rpc.solanavibestation.com/historical','base_rpc':'https://base-rpc.publicnode.com','bsc_rpc':'https://bsc-dataseed.bnbchain.org','bsc_archive':'https://portal.sqd.dev/datasets/binance-mainnet/stream','solana_archive':'https://portal.sqd.dev/datasets/solana-mainnet/finalized-stream','headers_sql':'https://crypto-clickhouse.clickhouse.com/?user=crypto','gamma':'https://gamma-api.polymarket.com','history':'https://data-api.polymarket.com/v2/prices-history'},
      'categories':{'macro':['Fed October 2026','CPI October 2026','inflation October 2026'],'solana':['Solana October 2026'],'bnb':['BNB October 2026'],'pump_listing':['pump.fun listing','pumpfun CEX'],'pump_sale':['pump.fun public sale','pump.fun raise'],'pump_revenue':['pump.fun revenue','pump.fun fees'],'base_token':['Base token']}}
