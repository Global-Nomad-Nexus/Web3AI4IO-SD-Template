import json
from pathlib import Path
import pytest
from claire_demo.common import load_json, save_raw, write_json
from claire_demo.acquire import RPC, RPCError, collect, sol_block

class Response:
    status_code=200
    headers={}
    def __init__(self,body): self.body=body
    def raise_for_status(self): pass
    def json(self): return self.body

def test_preserves_unknown_fields_and_precise_integer_and_resume(tmp_path):
    rpc=RPC(tmp_path,"base","https://provider.example/private-key?key=secret",interval=0)
    body={"jsonrpc":"2.0","id":1,"result":{"value":2**200,"future":{"x":[True,None]}}}
    calls=[]
    rpc.session.post=lambda *a,**kw: (calls.append(kw),Response(body))[1]
    p=tmp_path/"raw/base/blocks/1.json.gz"
    assert rpc.call("eth_getBlockByNumber",["0x1",True],p)==body["result"]
    assert rpc.call("eth_getBlockByNumber",["0x1",True],p)==body["result"]
    assert len(calls)==1
    assert load_json(p)==body
    log=(tmp_path/"provenance/request_log.jsonl").read_text()
    assert "secret" not in log and "private-key" not in log
    assert json.loads(log)["raw_sha256"]

def test_raw_file_cannot_be_silently_replaced(tmp_path):
    p=tmp_path/"raw.json.gz"
    save_raw(p,{"result":1})
    with pytest.raises(RuntimeError,match="immutable"):
        save_raw(p,{"result":2})
    assert load_json(p)=={"result":1}

def test_unknown_solana_version_retries_without_losing_block():
    class NewVersion:
        def __init__(self): self.versions=[]
        def call(self,method,params,path=None):
            self.versions.append(params[1]["maxSupportedTransactionVersion"])
            if self.versions[-1]<2: raise RPCError("Requires version2",-32015)
            return {"transactions":[{"version":2,"unknown_payload":True}]}
    rpc=NewVersion()
    assert sol_block(rpc,10)["transactions"][0]["version"]==2
    assert rpc.versions==[1,2]

def test_unresolved_three_chain_window_pauses_before_any_download(tmp_path):
    write_json(tmp_path/"reports/window.json",{"resolved":False,"chains":{"solana":{"resolved":True},"bsc":{"resolved":True},"base":{"resolved":False}}})
    with pytest.raises(RPCError,match="paused"):
        collect(tmp_path)
    assert not (tmp_path/"raw").exists()

def test_rpc_errors_and_null_results_not_saved_as_canonical_blocks(tmp_path):
    rpc=RPC(tmp_path,"solana","https://provider.example",interval=0,retries=1)
    p=tmp_path/"raw/solana/blocks/7.json.gz"
    rpc.session.post=lambda *a,**kw:Response({"jsonrpc":"2.0","id":1,"error":{"code":-32007,"message":"slot skipped"}})
    with pytest.raises(RPCError) as error: rpc.call("getBlock",[7],p)
    assert error.value.code==-32007
    assert not p.exists()
    assert len(list((tmp_path/"raw/requests/solana").glob("*.gz")))==1
    rpc.session.post=lambda *a,**kw:Response({"jsonrpc":"2.0","id":1,"result":None})
    assert rpc.call("getBlock",[7],p) is None
    assert not p.exists()

def test_semantically_wrong_response_stays_in_evidence_not_canonical(tmp_path):
    rpc=RPC(tmp_path,"base","https://provider.example",interval=0,retries=1)
    rpc.session.post=lambda *a,**kw:Response({"jsonrpc":"2.0","id":1,"result":[{"transactionHash":"wrong"}]})
    p=tmp_path/"raw/base/receipts/1.json.gz"
    with pytest.raises(RPCError):
        rpc.call("eth_getBlockReceipts",["0x1"],p,validator=lambda value:value==[])
    assert not p.exists()
    assert len(list((tmp_path/"raw/requests/base").glob("*.gz")))==1

def test_changed_json_cache_rejected_against_original_receipt(tmp_path):
    import gzip
    rpc=RPC(tmp_path,"base","https://provider.example",interval=0,retries=1)
    rpc.session.post=lambda *a,**kw:Response({"jsonrpc":"2.0","id":1,"result":{"value":1}})
    p=tmp_path/"raw/base/blocks/1.json.gz"
    rpc.call("eth_getBlockByNumber",["0x1",True],p)
    p.write_bytes(gzip.compress(json.dumps({"jsonrpc":"2.0","id":1,"result":{"value":2}}).encode()))
    with pytest.raises(RPCError,match="checksum"):
        RPC(tmp_path,"base","https://provider.example").call("eth_getBlockByNumber",["0x1",True],p)

def test_http429_rpc_error_respects_retry_after_and_resumes(tmp_path,monkeypatch):
    import claire_demo.acquire as acquire
    sleeps=[]
    monkeypatch.setattr(acquire.time,"sleep",lambda value:sleeps.append(value))
    limited=Response({"jsonrpc":"2.0","id":1,"error":{"code":-32029,"message":"rate limit"}})
    limited.status_code=429;limited.headers={"Retry-After":"42"};limited.text=json.dumps(limited.body)
    success=Response({"jsonrpc":"2.0","id":1,"result":{"ok":True}})
    sequence=iter([limited,success])
    rpc=RPC(tmp_path,"base","https://provider.example",interval=0,retries=2)
    rpc.session.post=lambda *a,**kw:next(sequence)
    assert rpc.call("eth_getBlockByNumber",["0x1",True])=={"ok":True}
    assert 42 in sleeps
    logs=[json.loads(s) for s in (tmp_path/"provenance/request_log.jsonl").read_text().splitlines()]
    assert logs[0]["http_status"]==429 and logs[1]["retry_count"]==1

def test_target_receipt_probe_uses_candidate_network_even_with_cache(tmp_path):
    from claire_demo.acquire import get_receipts
    block={"hash":"block", "number":"0x1", "transactions":[{"hash":"tx"}]}
    result=[{"transactionHash":"tx","blockHash":"block","blockNumber":"0x1","logs":[]}]
    canonical=tmp_path/"raw/base/receipts/1.json.gz"
    save_raw(canonical,{"result":result})
    calls=[]
    rpc=RPC(tmp_path,"base","https://candidate.example",interval=0,retries=1)
    rpc.session.post=lambda *a,**kw:(calls.append(kw),Response({"result":result}))[1]
    assert get_receipts(tmp_path,"base",rpc,1,block,probe=True)==result
    assert len(calls)==1
    assert load_json(canonical)=={"result":result}
    receipt=json.loads((tmp_path/"provenance/request_log.jsonl").read_text())
    assert receipt["raw_path"].startswith("raw/requests/")
