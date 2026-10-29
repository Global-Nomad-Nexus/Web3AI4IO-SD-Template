"""P2 scoped evidence I/O. Public reads only; cached responses support replay."""
import sys,json,time,urllib.request,urllib.error,hashlib,csv,gzip
try:
    from compression import zstd
except ImportError:zstd=None
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'code'))
from common import now,iso,epoch,sid,sha,read_csv,write_csv,write_json,token_id,PILOT
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT.parent
# Parent helpers are imported above; subsequent stage-local imports must resolve
# P2 modules before identically named P0/P1 scripts.
sys.path.insert(0,str(ROOT/'code'))
for name in ['raw','reports','configs','processed','provenance','tests','figures/data']:(ROOT/name).mkdir(parents=True,exist_ok=True)

def read_body(path):
    path=Path(path);data=path.read_bytes()
    return gzip.decompress(data) if path.suffix=='.gz' else data

class Client:
    def __init__(self,budget=500,offline=False):self.calls=0;self.budget=budget;self.offline=offline
    def request(self,url,payload=None,label=''):
        for attempt in range(8):
            body,m=self.once(url,payload,label)
            if m['ok'] or m['http_status'] not in [None,429,502,503,504,529]:return body,m
            if attempt==7:return body,m
            response_headers={k.lower():v for k,v in m['response_headers'].items()}
            delay=max(min(2**(attempt+1),20),float(response_headers.get('retry-after','0')))
            if delay>45:return body,m
            print('TRANSIENT_BACKOFF',m['http_status'],delay,url,flush=True)
            time.sleep(delay)
    def once(self,url,payload=None,label=''):
        key=sid(url,payload);mp=ROOT/'raw'/(key+'.meta.json')
        if mp.exists():
            m=json.loads(mp.read_text())
            if m['ok']:return read_body(ROOT/m['raw_ref']),m
        if self.offline:raise RuntimeError('Offline cache miss: '+url)
        if self.calls>=self.budget:raise RuntimeError('P2 request budget reached')
        self.calls+=1;start=now();clock=time.monotonic();body=b'';status=None;headers={};error=''
        accepted_encoding='zstd' if url.startswith('https://public.rpc.solanavibestation.com') and zstd is not None else 'gzip'
        req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers={'User-Agent':'Shilin-Registry-P2/0.2','Accept':'application/json,application/x-ndjson,text/plain','Content-Type':'application/json','Accept-Encoding':accepted_encoding})
        try:
            with urllib.request.urlopen(req,timeout=45) as r:status=r.status;headers=dict(r.headers);body=r.read(64_000_001)
            encoding=next((v for k,v in headers.items() if k.lower()=='content-encoding'),'').lower()
            if encoding=='gzip':body=gzip.decompress(body)
            elif encoding=='zstd':body=zstd.decompress(body)
            if len(body)>64_000_000:raise RuntimeError('P2 response >64 MB; split query')
        except urllib.error.HTTPError as e:status=e.code;body=e.read(1000000);headers=dict(e.headers);error=str(e)
        except Exception as e:error=type(e).__name__+': '+str(e)
        cfg_path=ROOT/'configs/pilot_protocol.json'
        storage_cap=json.loads(cfg_path.read_text()).get('max_total_raw_bytes',512_000_000) if cfg_path.exists() else 512_000_000
        stored=gzip.compress(body,mtime=0) if label=='public_Vibe_full_history_page_capability' and status==200 else body
        suffix='.body.gz' if stored is not body else '.body'
        if sum(p.stat().st_size for p in (ROOT/'raw').glob('*.body*'))+len(stored)>storage_cap:raise RuntimeError('P2 configured raw storage limit reached')
        path=ROOT/'raw'/(key+'-'+str(time.time_ns())+suffix);path.write_bytes(stored)
        try:
            d=json.loads(body)
            if isinstance(d,dict) and d.get('error'):error=error or json.dumps(d['error'])
        except (ValueError,UnicodeDecodeError):pass
        m={'request_id':key,'url':url,'payload':payload,'label':label,'started_at_utc':start,'retrieved_at_utc':now(),'elapsed_seconds':round(time.monotonic()-clock,4),'http_status':status,'error':error,'ok':status==200 and not error,'saved_bytes':len(body),'stored_bytes':len(stored),'storage_encoding':'gzip' if suffix.endswith('.gz') else 'identity','decompressed_sha256':hashlib.sha256(body).hexdigest(),'raw_ref':str(path.relative_to(ROOT)),'sha256':sha(path),'response_headers':headers,'access':'public_no_auth','redistribution':'not_reviewed_local_only'}
        write_json(mp,m)
        with (ROOT/'provenance/requests.jsonl').open('a') as f:f.write(json.dumps(m,ensure_ascii=False)+'\n')
        time.sleep(.5)
        return body,m
    def json(self,url,payload=None,label=''):
        b,m=self.request(url,payload,label)
        try:return json.loads(b),m
        except ValueError:return None,m
    def rpc(self,url,method,params,label=''):
        d,m=self.json(url,{'jsonrpc':'2.0','id':1,'method':method,'params':params},label)
        return d.get('result') if isinstance(d,dict) else None,m

def blocks(body):return [json.loads(line) for line in body.splitlines() if line.strip()]
