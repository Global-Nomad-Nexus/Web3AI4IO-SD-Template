"""Small, credential-free P0/P1 evidence utilities (Python standard library)."""
import csv
import hashlib
import json
import time
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
LEGACY = PROJECT / '1021/scientific-data-essential'
RELEASE = LEGACY / 'data/7day-72h-20261008-release'
PILOT = PROJECT / '2026-09-17/Web3AI4IO-SD-Template/pilots/claire-threechain-v1'

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
def iso(t): return datetime.fromtimestamp(float(t), timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
def epoch(s): return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sid(*items): return hashlib.sha256(json.dumps(items, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:32]
def token_id(chain, address):
    if chain.startswith('eip155:'):
        if not re.fullmatch(r'0x[0-9a-fA-F]{40}',address):raise ValueError('Invalid EVM token address')
        address=address.lower()
    elif chain=='solana:mainnet':
        if not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}',address):raise ValueError('Invalid Solana base58 token address shape')
    else:raise ValueError('Unsupported chain namespace')
    return chain+':token:'+address
def read_csv(p):
    with Path(p).open(newline='', encoding='utf-8') as f: return list(csv.DictReader(f))
def write_csv(p, rows, columns=None):
    p=Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    columns=columns or list(dict.fromkeys(k for r in rows for k in r))
    with p.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=columns); w.writeheader(); w.writerows(rows)
def write_json(p, value):
    p=Path(p);p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')

class EvidenceClient:
    """Cache exact public responses; append every attempt, including failures.

    POST is used only for JSON-RPC read methods. No transactions/signing/auth.
    Replays cached successful responses by default; --refresh is a new observation.
    """
    def __init__(self, refresh=False, budget=220, timeout=12):
        self.refresh=refresh;self.budget=budget;self.timeout=timeout;self.calls=0
    def request(self, url, payload=None, group='polymarket', label=''):
        key=sid(url,payload);directory=ROOT/'raw'/group;directory.mkdir(parents=True,exist_ok=True)
        meta_path=directory/(key+'.meta.json')
        if meta_path.exists() and not self.refresh:
            meta=json.loads(meta_path.read_text())
            if meta.get('ok'):
                body=(ROOT/meta['raw_ref']).read_bytes()
                try:return json.loads(body),meta
                except (ValueError,UnicodeDecodeError):return body.decode(errors='replace'),meta
        if self.calls>=self.budget: raise RuntimeError('Configured request budget reached')
        self.calls+=1; started=now(); clock=time.monotonic()
        body=b'';headers={};status=None;error=''
        req=urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode(),
            headers={'User-Agent':'Shilin-Registry-Research/0.1','Accept':'application/json',**({'Content-Type':'application/json'} if payload is not None else {})})
        try:
            with urllib.request.urlopen(req,timeout=self.timeout) as r:
                status=r.status;headers=dict(r.headers);body=r.read(12_000_001)
            if len(body)>12_000_000:raise ValueError('Per-response budget exceeded')
        except urllib.error.HTTPError as e:
            status=e.code;headers=dict(e.headers);body=e.read(1_000_000);error=str(e)
        except Exception as e:error=type(e).__name__+': '+str(e)
        try: data=json.loads(body)
        except (ValueError,UnicodeDecodeError):data=None
        if isinstance(data,dict) and data.get('error'):error=error or json.dumps(data['error'],ensure_ascii=False)
        raw=directory/(key+'-'+started.replace(':','')+'.body')
        if sum(p.stat().st_size for p in (ROOT/'raw').rglob('*.body'))+len(body)>100_000_000:
            raise RuntimeError('Configured 100 MB raw storage budget reached')
        raw.write_bytes(body)
        meta={'request_id':key,'label':label,'url':url,'request_payload':payload,'started_at_utc':started,
          'retrieved_at_utc':now(),'http_status':status,'ok':status==200 and not error,'error':error,
          'elapsed_seconds':round(time.monotonic()-clock,4),'saved_bytes':len(body),'response_headers':headers,
          'raw_ref':str(raw.relative_to(ROOT)),'sha256':sha(raw),'authentication':'none',
          'redistribution_status':'not_reviewed_local_evidence_only'}
        write_json(meta_path,meta)
        log=ROOT/'provenance/requests.jsonl';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('a') as f:f.write(json.dumps(meta,ensure_ascii=False)+'\n')
        time.sleep(.15)
        return (data if data is not None else body.decode(errors='replace')),meta
    def rpc(self,url,method,params,label=''):
        return self.request(url,{'jsonrpc':'2.0','id':1,'method':method,'params':params},'chain',label)
