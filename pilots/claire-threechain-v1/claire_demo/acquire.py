"""Free RPC acquisition. This is the only module that opens network sockets."""
from pathlib import Path
import hashlib
import json
import os
import platform
import re
import time
from urllib.parse import urlsplit
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import requests
from .common import CHAINS, START, END, timestamp, utcnow, load_json, write_json, save_raw, sha256, append_jsonl

class RPCError(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code

class RPC:
    def __init__(self, root, chain, endpoint, retries=8, interval=0.65):
        self.root, self.chain, self.endpoint = Path(root), chain, endpoint
        self.retries, self.interval, self.last = retries, interval, 0
        self.session = requests.Session()
        self.source_id = hashlib.sha256(endpoint.encode()).hexdigest()[:16]
        # Provider paths/query strings can contain keys, so credentials never enter logs.
        self.public_endpoint = urlsplit(endpoint).scheme + "://" + urlsplit(endpoint).hostname
        self.saved_hashes={}
        ledger=self.root/"provenance/request_log.jsonl"
        if ledger.exists():
            with ledger.open() as fh:
                for line in fh:
                    item=json.loads(line)
                    if item.get("raw_path") and item.get("raw_sha256"):
                        self.saved_hashes[item["raw_path"]]=item["raw_sha256"]

    def call(self, method, params, raw_path=None, validator=None):
        if raw_path and Path(raw_path).exists():
            relative=str(Path(raw_path).relative_to(self.root))
            existing=load_json(raw_path)
            expected=self.saved_hashes.get(relative)
            if expected is None and existing.get("_assembled_from"):
                lineage=existing.get("_input_files",{})
                if not lineage or any(sha256(self.root/p)!=digest for p,digest in lineage.items()):
                    raise RPCError(f"Assembled receipt lineage invalid: {relative}")
                if existing.get("result")!=[load_json(self.root/p).get("result") for p in lineage]:
                    raise RPCError(f"Assembled receipt content differs from original inputs: {relative}")
            elif expected is None or sha256(raw_path)!=expected:
                raise RPCError(f"Cached raw checksum differs from acquisition receipt: {relative}")
            result=existing["result"]
            if validator is not None and not validator(result):
                raise RPCError(f"Cached response fails semantic checks: {relative}")
            return result
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        last_error = None
        for attempt in range(self.retries):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
            receipt = dict(source_id=self.source_id, endpoint=self.public_endpoint,
                           rpc_method=method, request_params=params, requested_at=utcnow(),
                           chain_id=CHAINS[self.chain], retry_count=attempt,
                           block_number_or_slot=params[0] if params else None,
                           raw_path=None, raw_sha256=None, response_status=None, error_code=None)
            response = None
            try:
                response = self.session.post(self.endpoint, json=payload, timeout=(15, 90))
                self.last = time.monotonic()
                receipt["http_status"] = response.status_code
                if response.status_code >= 400:
                    target = self.root/"raw/requests"/self.chain/(hashlib.sha256((self.source_id+receipt["requested_at"]).encode()).hexdigest()+".json.gz")
                    save_raw(target,{"http_status":response.status_code,"body":response.text,"retry_after":response.headers.get("Retry-After")})
                    receipt.update(raw_path=str(target.relative_to(self.root)),raw_sha256=sha256(target))
                    try: remote_error=response.json().get("error")
                    except (ValueError,AttributeError): remote_error=None
                    if isinstance(remote_error,dict):
                        receipt.update(response_status="rpc_error",error_code=remote_error.get("code"))
                        raise RPCError("HTTP response contains JSON-RPC error",remote_error.get("code"))
                response.raise_for_status()
                body = response.json()
                semantic_ok=validator is None or ("error" not in body and validator(body.get("result")))
                # Save errors and probe responses too; full transaction successes use canonical shards.
                target = Path(raw_path) if raw_path and semantic_ok and "error" not in body and body.get("result") is not None else self.root / "raw" / "requests" / self.chain / (hashlib.sha256((json.dumps(payload,sort_keys=True)+self.source_id+receipt["requested_at"]).encode()).hexdigest()+".json.gz")
                save_raw(target, body)
                receipt.update(raw_path=str(target.relative_to(self.root)), raw_sha256=sha256(target))
                self.saved_hashes[receipt["raw_path"]]=receipt["raw_sha256"]
                if "error" in body:
                    err = body["error"]
                    receipt.update(response_status="rpc_error", error_code=err.get("code"))
                    raise RPCError(str(err), err.get("code"))
                if "result" not in body:
                    raise RPCError("Malformed JSON-RPC response: no result")
                if not semantic_ok:
                    receipt["response_status"]="semantic_error"
                    raise RPCError("RPC response failed semantic validation")
                result = body["result"]
                receipt["response_status"] = "ok" if result is not None else "null_result"
                if isinstance(result, dict):
                    receipt["block_hash"] = result.get("hash", result.get("blockhash"))
                return result
            except (requests.RequestException, ValueError, RPCError) as exc:
                last_error = exc
                receipt["response_status"] = receipt["response_status"] or "transport_error"
                receipt["error_type"] = type(exc).__name__
                # Avoid exception strings that may expose a credential-bearing URL.
                receipt["error_code"] = getattr(exc, "code", None)
                retry_http=response is not None and (response.status_code==429 or response.status_code>=500)
                permanent = isinstance(exc, RPCError) and exc.code not in (-32005, -32004, -32009,429,-32029) and not retry_http
                permanent |= response is not None and response.status_code in (400,401,403,404)
                if permanent or attempt + 1 == self.retries:
                    raise RPCError(f"{self.chain} {method} failed; inspect provenance/request_log.jsonl", getattr(exc,"code",None)) from None
                delay = min(60, 2 ** (attempt + 1))
                if response is not None:
                    try: delay = max(delay, float(response.headers.get("Retry-After", 0)))
                    except ValueError:
                        try: delay=max(delay,(parsedate_to_datetime(response.headers["Retry-After"])-datetime.now(timezone.utc)).total_seconds())
                        except (ValueError,KeyError,TypeError): pass
                time.sleep(delay)
            finally:
                receipt["retrieved_at"] = utcnow()
                append_jsonl(self.root / "provenance/request_log.jsonl", receipt)
        raise RPCError(str(last_error))

def endpoints(root, chain):
    configured = load_json(Path(root) / "config/rpc.json")[chain]
    override = os.environ.get("CLAIRE_" + chain.upper() + "_RPC")
    return ([override] if override else []) + configured

def client(root, chain):
    selected = load_json(Path(root) / "reports/preflight.json")["chains"][chain]["selected_source_id"]
    for endpoint in endpoints(root, chain):
        rpc = RPC(root, chain, endpoint)
        if rpc.source_id == selected:
            return rpc
    raise RPCError(f"Configured source for {chain} absent. Supply the same environment endpoint or rerun preflight.")

def sol_block(rpc, slot, full=True, path=None):
    version = 1
    while True:
        try:
            params=[slot, {"encoding":"json", "commitment":"finalized", "transactionDetails":"full" if full else "none", "rewards":True, "maxSupportedTransactionVersion":version}]
            if path is None: return rpc.call("getBlock",params)
            return rpc.call("getBlock",params,path,validator=lambda b:isinstance(b,dict) and isinstance(b.get("blockhash"),str) and (not full or isinstance(b.get("transactions"),list)))
        except RPCError as exc:
            # Do not discard a whole block if the node requests a newer version.
            if exc.code == -32015 and version < 16:
                version += 1
                continue
            raise

def evm_block(rpc,height,path=None):
    return rpc.call("eth_getBlockByNumber",[hex(height),True],path,validator=lambda b:isinstance(b,dict) and b.get("number")==hex(height) and isinstance(b.get("hash"),str) and isinstance(b.get("transactions"),list) and all(isinstance(t,dict) and t.get("hash") for t in b["transactions"]))

def preflight(root):
    root = Path(root)
    report = {"started_at":utcnow(), "environment":"google_colab" if "COLAB_RELEASE_TAG" in os.environ else "local", "python":platform.python_version(), "chains":{}}
    for chain in CHAINS:
        checks, selected = [], None
        for endpoint in endpoints(root, chain):
            rpc = RPC(root, chain, endpoint, retries=1)
            check = {"source_id":rpc.source_id,"endpoint":rpc.public_endpoint,"core_access":False}
            try:
                if chain == "solana":
                    check["genesis_hash"] = rpc.call("getGenesisHash",[])
                    if check["genesis_hash"] != "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d":
                        raise RPCError("Wrong Solana network")
                    slot = rpc.call("getSlot",[{"commitment":"finalized"}])
                    block = sol_block(rpc, slot)
                    if not block or not isinstance(block.get("transactions"),list):
                        raise RPCError("Missing complete transaction list")
                    check.update(height=slot,transaction_count=len(block["transactions"]),versions=sorted({str(t.get("version")) for t in block["transactions"]}),trace="not_applicable",historical_state="not_collected")
                else:
                    got = rpc.call("eth_chainId",[])
                    if int(got,16) != int(CHAINS[chain].split(":")[1]): raise RPCError("Wrong EVM chain")
                    block = rpc.call("eth_getBlockByNumber",["finalized",True])
                    if not block or any(not isinstance(t,dict) for t in block["transactions"]): raise RPCError("No complete finalized block")
                    try:
                        receipts = rpc.call("eth_getBlockReceipts",[block["number"]])
                        check["receipt_method"] = "eth_getBlockReceipts"
                        if len(receipts) != len(block["transactions"]): raise RPCError("Receipt count mismatch")
                    except RPCError:
                        for tx in block["transactions"]:
                            if not rpc.call("eth_getTransactionReceipt",[tx["hash"]]): raise RPCError("Missing individual receipt")
                        check["receipt_method"] = "eth_getTransactionReceipt"
                    check.update(height=int(block["number"],16),transaction_count=len(block["transactions"]),historical_state="not_collected")
                    try:
                        trace = rpc.call("debug_traceBlockByNumber",[block["number"],{"tracer":"callTracer","timeout":"20s"}])
                        check["trace"] = "available" if trace is not None else "unknown"
                    except RPCError: check["trace"] = "unavailable"
                check["core_access"] = True
                if selected is None or (chain != "solana" and check.get("receipt_method")=="eth_getBlockReceipts" and next((c.get("receipt_method") for c in checks if c["source_id"]==selected),None)!="eth_getBlockReceipts"):
                    selected = rpc.source_id
            except Exception as exc:
                check["error"] = str(exc)
            checks.append(check)
            print(chain, rpc.public_endpoint, check["core_access"], flush=True)
        report["chains"][chain] = {"selected_source_id":selected,"checks":checks,"core_access":selected is not None}
        write_json(root / "reports/preflight.json",report)
    report.update(completed_at=utcnow(),core_access=all(c["core_access"] for c in report["chains"].values()))
    write_json(root / "reports/preflight.json",report)
    return report

def resolve_window(root):
    root = Path(root)
    start,end=timestamp(START),timestamp(END)
    report={"start_utc":START,"end_utc":END,"start_ts":start,"end_ts":end,"chains":{}}
    pf=load_json(root/"reports/preflight.json")
    for chain in CHAINS:
        record={"main_blocks":[],"boundary_blocks":[],"expected_blocks":None,"skipped_slots":[],"uncertain_slots":[],"resolved":False}
        report["chains"][chain]=record
        if not pf["chains"][chain]["core_access"]:
            record["error"]="Core preflight failed"
            continue
        rpc=client(root,chain)
        cache={}
        # Reuse prior finalized header observations after interrupted boundary searches.
        ledger=root/"provenance/request_log.jsonl"
        if ledger.exists():
            for line in ledger.read_text().splitlines():
                item=json.loads(line)
                if item.get("chain_id")!=CHAINS[chain] or item.get("response_status")!="ok": continue
                params=item.get("request_params",[])
                if not params or not item.get("raw_path"): continue
                if chain=="solana" and item["rpc_method"]=="getBlock" and isinstance(params[0],int):
                    value=load_json(root/item["raw_path"]).get("result")
                    if value is not None: cache[params[0]]={k:value.get(k) for k in ("blockTime","blockhash","parentSlot","previousBlockhash")}
                elif chain!="solana" and item["rpc_method"]=="eth_getBlockByNumber" and str(params[0]).startswith("0x"):
                    value=load_json(root/item["raw_path"]).get("result")
                    if value is not None: cache[int(params[0],16)]={k:value.get(k) for k in ("timestamp","hash","number","parentHash")}
        try:
            if chain != "solana":
                latest=rpc.call("eth_getBlockByNumber",["finalized",False])
                high=int(latest["number"],16)
                def header(height):
                    if height not in cache: cache[height]=rpc.call("eth_getBlockByNumber",[hex(height),False])
                    if not cache[height]: raise RPCError(f"Missing header {height}")
                    return cache[height]
                def lower(target):
                    low,hi=0,high
                    if int(latest["timestamp"],16) < target: raise RPCError("Window not finalized yet")
                    while low < hi:
                        mid=(low+hi)//2
                        if int(header(mid)["timestamp"],16) < target: low=mid+1
                        else: hi=mid
                    return low
                first,stop=lower(start),lower(end)
                main=list(range(first,stop)); guards=[first-1,stop]
            else:
                high=rpc.call("getSlot",[{"commitment":"finalized"}])
                first_available=rpc.call("getFirstAvailableBlock",[])
                def produced(slot):
                    slots=rpc.call("getBlocks",[slot,min(slot+128,high),{"commitment":"finalized"}])
                    if not slots: raise RPCError(f"No produced slot near {slot}")
                    return slots[0]
                def header(slot):
                    if slot not in cache: cache[slot]=sol_block(rpc,slot,False)
                    if cache[slot] is None or cache[slot].get("blockTime") is None:
                        record["uncertain_slots"].append(slot)
                        raise RPCError(f"Cannot place slot {slot} in UTC window")
                    return cache[slot]
                def lower(target):
                    low,hi=first_available,high
                    if header(produced(high))["blockTime"] < target: raise RPCError("Window not finalized yet")
                    while hi-low > 128:
                        mid=produced((low+hi)//2)
                        if header(mid)["blockTime"] < target: low=mid+1
                        else: hi=mid
                    candidates=rpc.call("getBlocks",[max(first_available,low-128),min(high,hi+128),{"commitment":"finalized"}])
                    left,right=0,len(candidates)
                    while left<right:
                        middle=(left+right)//2
                        if header(candidates[middle])["blockTime"]<target: left=middle+1
                        else: right=middle
                    if left==len(candidates): raise RPCError("Boundary not found")
                    return candidates[left]
                first,stop=lower(start),lower(end)
                around=rpc.call("getBlocks",[max(0,first-128),stop+128,{"commitment":"finalized"}])
                main=[s for s in around if first<=s<stop]
                guards=[max(s for s in around if s<first),stop]
                record["skipped_slots"]=[s for s in range(guards[0]+1,stop) if s not in set(around)]
                record["slot_listing_evidence"]="getBlocks finalized; skipped label verified again against parentSlot during validation"
            # Real target first/middle/last full-block probes, plus adjacent boundaries.
            for h in sorted(set(guards+[main[i] for i in {0,len(main)//2,len(main)-1}] if main else guards)):
                path=root/"raw"/chain/"blocks"/f"{h}.json.gz"
                b=sol_block(rpc,h,path=path) if chain=="solana" else evm_block(rpc,h,path)
                if not b: raise RPCError(f"Missing target block {h}")
            record.update(main_blocks=main,boundary_blocks=guards,expected_blocks=len(main),resolved=True,boundary_hashes={str(h):(load_json(root/"raw"/chain/"blocks"/f"{h}.json.gz")["result"].get("blockhash") if chain=="solana" else load_json(root/"raw"/chain/"blocks"/f"{h}.json.gz")["result"]["hash"]) for h in guards})
        except Exception as exc: record["error"]=str(exc)
        write_json(root/"reports/window.json",report)
    report["resolved"]=all(c["resolved"] for c in report["chains"].values())
    write_json(root/"reports/window.json",report)
    return report

def get_receipts(root, chain, rpc, height, block, probe=False):
    from collections import Counter
    path=root/"raw"/chain/"receipts"/f"{height}.json.gz"
    def valid(receipts):
        return isinstance(receipts,list) and all(isinstance(r,dict) for r in receipts) and Counter(t["hash"] for t in block["transactions"])==Counter(r.get("transactionHash") for r in receipts) and all(r.get("blockHash")==block["hash"] and r.get("blockNumber")==block["number"] and isinstance(r.get("logs"),list) for r in receipts)
    try: receipts=rpc.call("eth_getBlockReceipts",[hex(height)],None if probe else path,validator=valid)
    except RPCError as exc:
        # Capability failure may use ordinary receipt calls; a transient server error
        # has already exhausted respectful retries and remains an explicit failure.
        if exc.code not in (-32601,-32002): raise
        receipts=[]; lineage={}
        for tx in block["transactions"]:
            individual=root/"raw"/chain/"transaction_receipts"/(tx["hash"]+".json.gz")
            receipt=rpc.call("eth_getTransactionReceipt",[tx["hash"]],None if probe else individual,validator=lambda r:isinstance(r,dict) and r.get("transactionHash")==tx["hash"] and r.get("blockHash")==block["hash"] and isinstance(r.get("logs"),list))
            if receipt is None: raise RPCError(f"Missing receipt {tx['hash']}")
            receipts.append(receipt)
            if not probe: lineage[str(individual.relative_to(root))]=sha256(individual)
        if not probe: save_raw(path,{"jsonrpc":"2.0","id":None,"result":receipts,"_assembled_from":"transaction_receipts","_input_files":lineage})
    if not valid(receipts):
        raise RPCError(f"Receipt IDs mismatch at {chain}:{height}")
    return receipts

def collect(root):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    root=Path(root); window=load_json(root/"reports/window.json")
    if not window.get("resolved"):
        raise RPCError("Three-chain window is unresolved. Collection paused; inspect reports/window.json.")
    report={"started_at":utcnow(),"chains":{},"complete":False}
    write_json(root/"reports/collection.json",report)
    target_checks={}
    for chain,scope in window["chains"].items():
        main=scope["main_blocks"]
        target_checks[chain]=[]
        pf=load_json(root/"reports/preflight.json")
        current=pf["chains"][chain]
        candidates=endpoints(root,chain)
        def priority(url):
            sid=hashlib.sha256(url.encode()).hexdigest()[:16]
            prior=next((c for c in current["checks"] if c["source_id"]==sid),{})
            return 0 if sid==current["selected_source_id"] else 2 if prior.get("receipt_method")=="eth_getTransactionReceipt" else 1
        chosen=None
        for endpoint in sorted(candidates,key=priority):
            rpc=RPC(root,chain,endpoint)
            candidate={"source_id":rpc.source_id,"endpoint":rpc.public_endpoint,"blocks":[],"core_access":False}
            try:
                if chain!="solana" and int(rpc.call("eth_chainId",[]),16)!=int(CHAINS[chain].split(":")[1]): raise RPCError("Wrong chain")
                for h in sorted({main[0],main[len(main)//2],main[-1]}):
                    path=root/"raw"/chain/"blocks"/f"{h}.json.gz"
                    # Check the candidate source itself, independently of cached bodies.
                    b=sol_block(rpc,h) if chain=="solana" else evm_block(rpc,h)
                    if b is None: raise RPCError(f"Target preflight missing {chain}:{h}")
                    cached=load_json(path)["result"]
                    if (b.get("blockhash") if chain=="solana" else b.get("hash"))!=(cached.get("blockhash") if chain=="solana" else cached.get("hash")):
                        raise RPCError(f"Conflicting finalized block hash {chain}:{h}")
                    if chain!="solana": get_receipts(root,chain,rpc,h,b,probe=True)
                    candidate["blocks"].append({"height":h,"full_transactions":len(b["transactions"]),"core_access":True})
                candidate["core_access"]=True
                chosen=rpc.source_id
                if not any(c["source_id"]==chosen for c in current["checks"]):
                    try:
                        rpc.call("debug_traceBlockByNumber",[hex(main[0]),{"tracer":"callTracer","timeout":"20s"}])
                        trace="available"
                    except RPCError: trace="unavailable"
                    current["checks"].append({"source_id":chosen,"endpoint":rpc.public_endpoint,"core_access":True,"receipt_method":"eth_getBlockReceipts","trace":trace,"historical_state":"not_collected","scope":"fixed_window_first_middle_last"})
                current["selected_source_id"]=chosen
                current["selection_reason"]="Passed fixed-window first/middle/last block and receipt checks"
                write_json(root/"reports/preflight.json",pf)
            except RPCError as exc: candidate["error"]=str(exc)
            target_checks[chain].append(candidate)
            write_json(root/"reports/target_preflight.json",target_checks)
            if chosen: break
        if not chosen: raise RPCError(f"{chain} fixed-window core access failed for every configured free source")
        write_json(root/"reports/target_preflight.json",target_checks)
    # At most one active request per chain. Separate chains can progress together.
    def collect_chain(chain,scope):
        rpc=client(root,chain); got=0
        capabilities=load_json(root/"reports/preflight.json")["chains"][chain]
        selected_check=next(c for c in capabilities["checks"] if c["source_id"]==capabilities["selected_source_id"])
        trace_available=selected_check.get("trace")=="available"
        trace_failures=[]
        heights=sorted(set(scope["main_blocks"]+scope["boundary_blocks"]))
        try:
            for h in heights:
                path=root/"raw"/chain/"blocks"/f"{h}.json.gz"
                b=sol_block(rpc,h,path=path) if chain=="solana" else evm_block(rpc,h,path)
                if b is None: raise RPCError(f"Missing block {h}")
                if chain!="solana":
                    get_receipts(root,chain,rpc,h,b)
                got+=1
                if got%25==0: print(chain,got,"/",len(heights),flush=True)
            # Core receipts finish before optional traces consume the free quota.
            if trace_available:
                for h in heights:
                    try: rpc.call("debug_traceBlockByNumber",[hex(h),{"tracer":"callTracer","timeout":"20s"}],root/"raw"/chain/"traces"/f"{h}.json.gz")
                    except RPCError: trace_failures.append(h)
            return {"complete":True,"blocks":got,"trace_capability":selected_check.get("trace"),"trace_failed_blocks":trace_failures}
        except Exception as exc:
            return {"complete":False,"blocks":got,"error":str(exc)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(collect_chain,chain,scope):chain for chain,scope in window["chains"].items()}
        for future in as_completed(futures):
            report["chains"][futures[future]]=future.result()
            write_json(root/"reports/collection.json",report)
    report.update(complete=all(c["complete"] for c in report["chains"].values()),completed_at=utcnow())
    write_json(root/"reports/collection.json",report)
    return report
