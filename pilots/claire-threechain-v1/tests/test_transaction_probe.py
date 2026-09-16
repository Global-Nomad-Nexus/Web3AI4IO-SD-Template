"""Offline synthetic RPC mocks. Never contact a chain in tests."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from claire_demo import transaction_probe
from claire_demo.acquire import RPCError
from claire_demo.common import START, END, timestamp, load_json, save_raw, write_json, sha256, append_jsonl


@pytest.fixture
def frame(tmp_path):
    start=timestamp(START)
    responses={}
    for slot in (10,11):
        transactions=[]
        for index in range(15):
            version=("legacy",0,1)[index%3]
            status=None if index%2==0 else "SyntheticExecutionFailure"
            sig=f"synthetic-{slot}-{index}"
            native={"version":version,"transaction":{"signatures":[sig],"message":{"futureConfig":{"bytes":[1,2,3]},"instructions":[],"accountKeys":[]}},
                    "meta":{"err":status,"fee":123456789012345678,"logMessages":None,"innerInstructions":None}}
            transactions.append(native)
            responses[sig]=dict(slot=slot,blockTime=start+slot-10,**copy.deepcopy(native))
        save_raw(tmp_path/f"raw/solana/blocks/{slot}.json.gz",{"result":{"blockhash":f"block-{slot}","blockTime":start+slot-10,"transactions":transactions}})
    write_json(tmp_path/"reports/window.json",{"resolved":True,"start_ts":start,"end_ts":timestamp(END),"chains":{"solana":{"resolved":True,"main_blocks":[10,11],"expected_blocks":2,"boundary_blocks":[9,12],"uncertain_slots":[]}}})
    write_json(tmp_path/"reports/collection.json",{"complete":True})
    return tmp_path,responses


class FakeRPC:
    source_id="synthetic-selected-source"
    public_endpoint="https://synthetic.example"
    def __init__(self,root,responses,first_error=None,record=True):
        self.root=root;self.responses=responses;self.calls=[];self.first_error=first_error;self.record=record
    def call(self,method,params,raw_path=None):
        assert method=="getTransaction"
        assert raw_path is None
        assert params[1]["encoding"]=="json" and params[1]["commitment"]=="finalized"
        self.calls.append((method,copy.deepcopy(params)))
        error=self.first_error if len(self.calls)==1 else None
        body={"error":{"code":error,"message":"synthetic error"}} if error is not None else {"result":copy.deepcopy(self.responses[params[0]])}
        if self.record:
            p=self.root/f"raw/requests/solana/synthetic-{len(self.calls)}.json.gz"
            # A second test invocation gets an independent evidence filename.
            while p.exists(): p=p.with_name("again-"+p.name)
            save_raw(p,body)
            append_jsonl(self.root/"provenance/request_log.jsonl",{"source_id":self.source_id,"rpc_method":method,"request_params":params,"response_status":"rpc_error" if error is not None else "ok", "raw_path":str(p.relative_to(self.root)),"raw_sha256":sha256(p),"error_code":error})
        if error is not None: raise RPCError("synthetic",error)
        return body["result"]


def probe(frame,**kwargs):
    root,responses=frame;rpc=FakeRPC(root,responses,**kwargs)
    with patch("claire_demo.transaction_probe.client",return_value=rpc): result=transaction_probe.run(root)
    return result,rpc


def test_seeded_sample_and_observed_version_status_representatives(frame):
    root,_=frame
    report,rpc=probe(frame)
    assert report["passed"],report
    assert report["population_transactions"]==30
    assert 20<=report["selected_transactions"]<=26
    assert sum("seeded_reservoir" in r["selection_reasons"] for r in report["checks"])==20
    assert {(r["version"],r["execution_status"]) for r in report["checks"]}=={(v,s) for v in ("legacy",0,1) for s in ("success","failed")}
    assert all(r["request_evidence"] and r["signature_matches"] for r in report["checks"])
    report2,_=probe(frame)
    assert [r["signature"] for r in report["checks"]]==[r["signature"] for r in report2["checks"]]
    assert "not independent-node verification" in report["comparison"]
    assert not (root/"raw/solana/transaction_receipts").exists()


@pytest.mark.parametrize("change,pointer",[("slot","/slot"),("blockTime","/blockTime"),("fee","/meta/fee"),("version","/version"),("message","/transaction/message/futureConfig/bytes/0"),("signature","/transaction/signatures/0")])
def test_explicit_field_difference_fails(frame,change,pointer):
    root,responses=frame
    # First transaction is retained as an observed version/status representative.
    response=responses["synthetic-10-0"]
    if change in ("slot","blockTime"): response[change]+=1
    elif change=="fee": response["meta"]["fee"]+=1
    elif change=="version": del response["version"]
    elif change=="signature": response["transaction"]["signatures"][0]="wrong"
    else: response["transaction"]["message"]["futureConfig"]["bytes"][0]=2
    report,_=probe(frame)
    assert not report["passed"]
    row=next(r for r in report["checks"] if r["signature"]=="synthetic-10-0")
    assert row["status"]=="mismatch"
    assert pointer in {d["pointer"] for d in row["differences"]}


def test_null_result_is_failure_not_empty_match(frame):
    frame[1]["synthetic-10-0"]=None
    report,_=probe(frame)
    assert not report["passed"]
    assert next(r for r in report["checks"] if r["signature"]=="synthetic-10-0")["status"]=="missing"


def test_version_negotiation_keeps_both_request_receipts(frame):
    report,rpc=probe(frame,first_error=-32015)
    assert report["passed"]
    assert rpc.calls[0][1][1]["maxSupportedTransactionVersion"]==1
    assert rpc.calls[1][1][1]["maxSupportedTransactionVersion"]==2
    assert len(report["checks"][0]["request_evidence"])==2


def test_incomplete_collection_never_starts_requests(frame):
    root,_=frame
    write_json(root/"reports/collection.json",{"complete":False})
    report,rpc=probe(frame)
    assert not report["passed"] and not rpc.calls


def test_missing_raw_frame_never_starts_partial_sampling(frame):
    root,_=frame
    (root/"raw/solana/blocks/11.json.gz").unlink()
    report,rpc=probe(frame)
    assert not report["passed"] and not rpc.calls


def test_success_without_request_receipt_cannot_pass(frame):
    report,_=probe(frame,record=False)
    assert not report["passed"]
    assert all(r["status"]=="missing_provenance" for r in report["checks"])
