import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from claire_demo.common import write_json, save_raw, implementation_hashes


def test_failed_stage_stops_replay_and_records_failure(tmp_path, monkeypatch):
    import claire_demo.__main__ as cli
    called=[]
    monkeypatch.setattr(sys,"addaudithook",lambda hook:None)
    def module(name):
        stage=name.rsplit(".",1)[-1]
        def run(root):
            called.append(stage)
            return {"passed":False} if stage=="validate" else {"passed":True}
        return SimpleNamespace(run=(lambda root,thresholds:run(root)) if stage=="events" else run)
    monkeypatch.setattr(cli.importlib,"import_module",module)
    with pytest.raises(RuntimeError,match="validate did not pass"):
        cli.run_stage(tmp_path,"replay")
    assert "visualize" not in called
    receipts=[json.loads(s) for s in (tmp_path/"provenance/runs.jsonl").read_text().splitlines()]
    assert receipts[-1]["stage"]=="replay" and receipts[-1]["status"]=="failed"


def test_cross_source_conflict_is_not_hidden_by_later_match(tmp_path,monkeypatch):
    import claire_demo.crosscheck as cc
    urls=["https://one.example","https://two.example","https://three.example"]
    ids=[hashlib.sha256(u.encode()).hexdigest()[:16] for u in urls]
    monkeypatch.setattr(cc,"CHAINS",{"bsc":"eip155:56"})
    monkeypatch.setattr(cc,"endpoints",lambda root,chain:urls)
    monkeypatch.setattr(cc,"RPC",lambda root,chain,url,retries:SimpleNamespace(source_id=ids[urls.index(url)],public_endpoint=url))
    monkeypatch.setattr(cc,"evm_block",lambda rpc,h:{"hash":"conflict" if rpc.source_id==ids[1] else "canonical","transactions":[{"hash":"tx"}]})
    write_json(tmp_path/"reports/window.json",{"chains":{"bsc":{"main_blocks":[10],"boundary_blocks":[]}}})
    write_json(tmp_path/"reports/preflight.json",{"chains":{"bsc":{"selected_source_id":ids[0],"checks":[{"source_id":i,"core_access":True} for i in ids]}}})
    save_raw(tmp_path/"raw/bsc/blocks/10.json.gz",{"result":{"hash":"canonical","transactions":[{"hash":"tx"}]}})
    (tmp_path/"provenance").mkdir()
    (tmp_path/"provenance/request_log.jsonl").write_text(json.dumps({"response_status":"ok","source_id":ids[0],"raw_path":"raw/bsc/blocks/10.json.gz"})+"\n")
    report=cc.run(tmp_path)
    assert report["chains"]["bsc"]["status"]=="mismatch"
    assert report["passed"] is False


def test_bundle_rejects_code_changed_since_reproduction(tmp_path):
    from claire_demo.bundle import run
    for name in ("validation","notebook_execution"):
        write_json(tmp_path/f"reports/{name}.json",{"passed":True})
    write_json(tmp_path/"reports/reproduction.json",{"passed":True,"implementation_hashes":{},"raw_hashes":{},"semantic_tables":{}})
    (tmp_path/"claire_demo").mkdir()
    (tmp_path/"claire_demo/changed.py").write_text("# changed after acceptance\n")
    with pytest.raises(RuntimeError,match="implementation_hashes changed"):
        run(tmp_path)
