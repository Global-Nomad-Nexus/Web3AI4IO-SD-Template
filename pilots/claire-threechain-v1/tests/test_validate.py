"""Adversarial synthetic snapshots. No fixture represents research observations."""
from pathlib import Path
import gzip
import json
from unittest.mock import patch
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from claire_demo import normalize, decode, events, validate, provenance
from claire_demo.common import START, END, timestamp, save_raw, write_json, load_json, sha256


def ledger(root):
    path=root/"provenance/request_log.jsonl";path.parent.mkdir(exist_ok=True)
    path.write_text("".join(json.dumps({"raw_path":str(p.relative_to(root)),"raw_sha256":sha256(p),"response_status":"ok"})+"\n"
                            for p in sorted((root/"raw").rglob("*.gz"))))


def overwrite(path, value):
    path.write_bytes(gzip.compress(json.dumps(value).encode(),mtime=0))


def pipeline(root):
    normalize.run(root)
    with patch("claire_demo.registry.load",return_value=[]): decode.run(root)
    events.run(root)
    provenance.run(root)


@pytest.fixture
def snapshot(tmp_path):
    start=timestamp(START);end=timestamp(END)
    chains={c:{"resolved":True,"main_blocks":[10],"boundary_blocks":[9,11],"expected_blocks":1,"skipped_slots":[],"uncertain_slots":[]} for c in ("solana","bsc","base")}
    write_json(tmp_path/"reports/window.json",dict(start_utc=START,end_utc=END,start_ts=start,end_ts=end,resolved=True,chains=chains))
    for chain in chains:
        for height,bt in ((9,start-1),(10,start),(11,end)):
            if chain=="solana":
                tx={"version":"legacy","transaction":{"signatures":[f"sig-{height}"],"message":{
                    "header":{"numRequiredSignatures":1,"numReadonlySignedAccounts":0,"numReadonlyUnsignedAccounts":0},
                    "accountKeys":["payer"],"instructions":[]}},
                    "meta":{"err":None,"fee":5000,"preBalances":[9000],"postBalances":[4000],
                            "preTokenBalances":[],"postTokenBalances":[],"loadedAddresses":{"writable":[],"readonly":[]},
                            "innerInstructions":[],"logMessages":[]}}
                block={"blockHeight":height,"blockTime":bt,"blockhash":f"hash-{height}","previousBlockhash":f"hash-{height-1}","parentSlot":height-1,"transactions":[tx]}
            else:
                tx={"hash":f"0xtx{height}","from":"0x"+"01"*20,"to":"0x"+"02"*20,
                    "transactionIndex":"0x0","type":"0x2","value":hex(2**240+7),"gas":"0x5208","nonce":"0x1","input":"0x"}
                block={"number":hex(height),"hash":f"hash-{height}","parentHash":f"hash-{height-1}","timestamp":hex(bt),"transactions":[tx]}
                receipt={"transactionHash":tx["hash"],"blockHash":block["hash"],"blockNumber":hex(height),
                         "status":"0x1","logs":[],"gasUsed":"0x5208","effectiveGasPrice":"0x1","l1Fee":"0x2"}
                save_raw(tmp_path/"raw"/chain/"receipts"/f"{height}.json.gz",{"result":[receipt]})
            save_raw(tmp_path/"raw"/chain/"blocks"/f"{height}.json.gz",{"result":block})
    ledger(tmp_path);pipeline(tmp_path)
    return tmp_path


def result(root,name):
    report=validate.run(root)
    return report,next(c for c in report["checks"] if c["check"]==name)


def test_complete_synthetic_snapshot_passes(snapshot):
    report=validate.run(snapshot)
    assert report["passed"],report["checks"]
    assert report["snapshot_replay"]=="not_tested_by_this_command"
    assert "provenance/requests.parquet" in load_json(snapshot/"manifest.json")["semantic_tables"]


def test_missing_meta_is_failure_even_when_signature_is_preserved(snapshot):
    p=snapshot/"raw/solana/blocks/10.json.gz";raw=load_json(p)
    raw["result"]["transactions"][0]["meta"]=None
    overwrite(p,raw);ledger(snapshot);pipeline(snapshot)
    report,check=result(snapshot,"solana_core_integrity")
    assert not report["passed"] and not check["passed"]
    assert any("missing meta" in d for d in check["details"])


def test_missing_logs_is_not_complete_zero(snapshot):
    p=snapshot/"raw/bsc/receipts/10.json.gz";raw=load_json(p)
    del raw["result"][0]["logs"]
    overwrite(p,raw);ledger(snapshot);pipeline(snapshot)
    report,check=result(snapshot,"bsc_core_integrity")
    assert not report["passed"] and not check["passed"]
    cells=load_json(snapshot/"reports/coverage.json")
    assert next(c for c in cells if c["chain"]=="bsc" and c["minute_index"]==0 and c["data_type"]=="native_logs_instructions")["status"]!="complete"


def test_explicit_null_after_failed_execution_is_preserved_not_imputed(snapshot):
    p=snapshot/"raw/solana/blocks/10.json.gz";raw=load_json(p)
    meta=raw["result"]["transactions"][0]["meta"]
    meta.update(err="MaxLoadedAccountsDataSizeExceeded",computeUnitsConsumed=0,
                innerInstructions=None,logMessages=None)
    overwrite(p,raw);ledger(snapshot);pipeline(snapshot)
    report=validate.run(snapshot)
    assert report["passed"],report["checks"]
    tx=list(validate.rows(snapshot/"tables/base/transactions/solana-10.parquet"))[0]
    assert tx["execution_meta_status"]=="provided"
    assert tx["inner_instructions_status"]=="explicit_null"
    assert tx["log_messages_status"]=="explicit_null"
    cells=load_json(snapshot/"reports/coverage.json")
    cell=next(c for c in cells if c["chain"]=="solana" and c["minute_index"]==0 and c["data_type"]=="native_logs_instructions")
    assert cell["expected"] is None and cell["status"]=="unknown"


@pytest.mark.parametrize("mode",["missing","invalid"])
def test_missing_or_invalid_inner_array_still_fails(snapshot,mode):
    p=snapshot/"raw/solana/blocks/10.json.gz";raw=load_json(p)
    meta=raw["result"]["transactions"][0]["meta"]
    if mode=="missing": del meta["innerInstructions"]
    else: meta["innerInstructions"]="invalid-array"
    overwrite(p,raw);ledger(snapshot);pipeline(snapshot)
    report,check=result(snapshot,"solana_core_integrity")
    assert not report["passed"] and not check["passed"]


def test_wrong_but_resolvable_raw_reference_fails(snapshot):
    p=snapshot/"tables/base/transactions/bsc-10.parquet";table=pq.read_table(p);values=table.to_pylist()
    values[0]["raw_ref"]="raw/bsc/blocks/10.json.gz#/result/hash"
    pq.write_table(pa.Table.from_pylist(values,schema=table.schema),p)
    report,check=result(snapshot,"bsc_core_integrity")
    assert not report["passed"] and not check["passed"]


def test_deleting_empty_base_table_still_fails(snapshot):
    (snapshot/"tables/base/evm_logs/bsc-10.parquet").unlink()
    report,check=result(snapshot,"all_base_tables_typed_and_source_counts_match")
    assert not report["passed"] and not check["passed"]


def test_same_count_but_wrong_uint256_value_fails(snapshot):
    p=snapshot/"tables/base/evm_transaction_details/base-10.parquet";table=pq.read_table(p);values=table.to_pylist()
    values[0]["value_raw"]=str(2**240)
    pq.write_table(pa.Table.from_pylist(values,schema=table.schema),p)
    report,check=result(snapshot,"all_base_tables_typed_and_source_counts_match")
    assert not report["passed"] and not check["passed"]
    assert any("raw EVM value differs" in d for d in check["details"])


def test_raw_tamper_is_detected_against_original_receipt(snapshot):
    p=snapshot/"raw/base/blocks/10.json.gz";raw=load_json(p);raw["result"]["extra"]=123
    overwrite(p,raw)
    report,check=result(snapshot,"acquisition_hashes_and_assembly_lineage")
    assert not report["passed"] and not check["passed"]
    assert any("hash mismatch" in d for d in check["details"])


def test_missing_decoded_table_is_not_zero_observations(snapshot):
    (snapshot/"tables/decoded/platform_records/base-10.parquet").unlink()
    report,check=result(snapshot,"decoded_and_event_outputs_present_and_current")
    assert not report["passed"] and not check["passed"]


def test_assembled_receipts_check_actual_input_contents(snapshot):
    p=snapshot/"raw/base/receipts/10.json.gz";raw=load_json(p)
    child=snapshot/"raw/base/transaction_receipts/0xtx10.json.gz"
    save_raw(child,{"result":raw["result"][0]})
    relative=str(child.relative_to(snapshot))
    raw.update(_assembled_from="transaction_receipts",_input_files={relative:sha256(child)})
    overwrite(p,raw)
    ledger(snapshot)
    # Generated aggregate must rely on lineage, not pretend to be a network response.
    lp=snapshot/"provenance/request_log.jsonl"
    lp.write_text("\n".join(line for line in lp.read_text().splitlines() if json.loads(line)["raw_path"]!=str(p.relative_to(snapshot)))+"\n")
    assert validate.provenance_errors(snapshot,validate.file_hashes(snapshot,("raw",)))==[]
    raw["result"][0]["gasUsed"]="0x1"
    overwrite(p,raw)
    problems=validate.provenance_errors(snapshot,validate.file_hashes(snapshot,("raw",)))
    assert any("assembly differs" in p for p in problems)


def test_typed_provenance_old_valid_prefix_is_not_complete(snapshot):
    before=load_json(snapshot/"reports/provenance_summary.json")
    assert before["passed"] is True
    with (snapshot/"provenance/request_log.jsonl").open("a") as fh:
        fh.write(json.dumps({"rpc_method":"eth_blockNumber","request_params":[],"response_status":"transport_error"})+"\n")
    report,check=result(snapshot,"typed_provenance_covers_complete_current_ledger")
    assert not report["passed"] and not check["passed"]
    assert any("stale/incomplete" in e for e in check["details"])


def test_missing_typed_provenance_rejected(snapshot):
    (snapshot/"provenance/requests.parquet").unlink()
    report,check=result(snapshot,"typed_provenance_covers_complete_current_ledger")
    assert not report["passed"] and not check["passed"]
    assert any("missing table shard" in e for e in check["details"])


def test_typed_provenance_raw_hash_must_match_original_even_if_summary_rehashed(snapshot):
    path=snapshot/"provenance/requests.parquet";table=pq.read_table(path);values=table.to_pylist()
    values[0]["raw_sha256"]="0"*64
    pq.write_table(pa.Table.from_pylist(values,schema=table.schema),path)
    summary=load_json(snapshot/"reports/provenance_summary.json");summary["output_sha256"]=sha256(path)
    write_json(snapshot/"reports/provenance_summary.json",summary)
    report,check=result(snapshot,"typed_provenance_covers_complete_current_ledger")
    assert not report["passed"] and not check["passed"]
    assert any("raw integrity differs" in e for e in check["details"])


def test_first_seen_global_minimum_audit_is_not_replaced_by_input_hashes(snapshot):
    path=snapshot/"tables/base/objects/bsc-10.parquet";table=pq.read_table(path);values=table.to_pylist()
    values[0]["first_seen_in_window"]+=100
    pq.write_table(pa.Table.from_pylist(values,schema=table.schema),path)
    report,check=result(snapshot,"object_observation_times_and_global_first_seen")
    assert not report["passed"] and not check["passed"]
    assert any("global MIN" in message for message in check["details"]["errors"])


def test_object_observed_at_must_match_its_own_evidence_block(snapshot):
    path=snapshot/"tables/base/objects/bsc-10.parquet";table=pq.read_table(path);values=table.to_pylist()
    values[0]["observed_at"]+=1
    pq.write_table(pa.Table.from_pylist(values,schema=table.schema),path)
    report,check=result(snapshot,"object_observation_times_and_global_first_seen")
    assert not report["passed"] and not check["passed"]
    assert any("differs from source block" in message for message in check["details"]["errors"])


def test_receipt_supported_objects_use_the_receipts_block_time(snapshot):
    block_path=snapshot/"raw/bsc/blocks/10.json.gz";block=load_json(block_path)
    block["result"]["transactions"][0]["to"]=None
    overwrite(block_path,block)
    receipt_path=snapshot/"raw/bsc/receipts/10.json.gz";receipt=load_json(receipt_path)
    receipt["result"][0]["contractAddress"]="0x"+"03"*20
    receipt["result"][0]["logs"]=[{"logIndex":"0x0","address":"0x"+"04"*20,"topics":[],"data":"0x","removed":False}]
    overwrite(receipt_path,receipt);ledger(snapshot);pipeline(snapshot)
    report=validate.run(snapshot)
    assert report["passed"],report["checks"]
    supported=[r for r in validate.rows(snapshot/"tables/base/objects/bsc-10.parquet") if r["raw_ref"].startswith("raw/bsc/receipts/")]
    assert {r["type_evidence"] for r in supported}=={"receipt_contractAddress","log_emitter"}
    assert all(r["observed_at"]==r["first_seen_in_window"]==timestamp(START) for r in supported)


def test_global_min_audit_accepts_reverse_order_and_null_without_inventing_zero():
    sources={"raw/later.json.gz":300,"raw/earlier.json.gz":100,"raw/unknown.json.gz":None}
    with validate.ObjectTimeAudit(sources) as audit:
        audit.add({"object_id":"x","observed_at":300,"first_seen_in_window":100,"raw_ref":"raw/later.json.gz#/result"})
        audit.add({"object_id":"x","observed_at":None,"first_seen_in_window":100,"raw_ref":"raw/unknown.json.gz#/result"})
        audit.add({"object_id":"x","observed_at":100,"first_seen_in_window":100,"raw_ref":"raw/earlier.json.gz#/result"})
        audit.add({"object_id":"unknown-only","observed_at":None,"first_seen_in_window":None,"raw_ref":"raw/unknown.json.gz#/result"})
        assert audit.finish()["passed"]
    with validate.ObjectTimeAudit(sources) as audit:
        audit.add({"object_id":"x","observed_at":300,"first_seen_in_window":300,"raw_ref":"raw/later.json.gz#/result"})
        audit.add({"object_id":"x","observed_at":100,"first_seen_in_window":100,"raw_ref":"raw/earlier.json.gz#/result"})
        result=audit.finish()
        assert not result["passed"] and result["error_count"]==1
