"""Synthetic fixtures validate decoding boundaries; never part of demo data."""
from pathlib import Path
import copy
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from claire_demo.common import save_raw, write_json, file_hashes
from claire_demo.normalize import run, integer, amount, VOTE_PROGRAM
from claire_demo.schemas import SCHEMAS


def setup(root, chain, block, receipts=None, boundaries=None):
    height = 10
    chains = {key: {"resolved": True, "main_blocks": [], "boundary_blocks": [], "expected_blocks": 0}
              for key in ("solana", "bsc", "base")}
    chains[chain].update(main_blocks=[height], expected_blocks=1, boundary_blocks=list(boundaries or {}))
    write_json(root / "reports/window.json", dict(start_ts=100, end_ts=400, start_utc="", end_utc="", chains=chains))
    save_raw(root / "raw" / chain / "blocks/10.json.gz", {"jsonrpc": "2.0", "id": 1, "result": block})
    if receipts is not None:
        save_raw(root / "raw" / chain / "receipts/10.json.gz", {"result": receipts})
    for number, boundary in (boundaries or {}).items():
        save_raw(root / "raw" / chain / "blocks" / f"{number}.json.gz", {"result": boundary})


def records(root, name):
    files = sorted((root / "tables/base" / name).glob("*.parquet"))
    return [row for f in files for row in pq.read_table(f).to_pylist()]


def evm_fixture():
    txs = [{"hash": "0xaaa", "transactionIndex": "0x0", "from": "0xA", "to": "0xB", "type": "0x2",
            "value": hex(2 ** 255 + 123), "nonce": "0x1", "input": "0x00", "gas": "0x5208"},
           {"hash": "0xbbb", "transactionIndex": "0x1", "from": "0xC", "to": None,
            "type": "0x7e", "value": "0x0", "nonce": "0x0", "input": "0x", "gas": "0x9"}]
    block = {"number": "0xa", "hash": "0xblock", "parentHash": "0xprev", "timestamp": "0x64", "transactions": txs}
    receipts = [{"transactionHash": t["hash"], "blockHash": "0xblock", "blockNumber": "0xa", "status": hex(1 - i),
                 "gasUsed": "0x7", "effectiveGasPrice": "0x3", "l1Fee": "0x5", "contractAddress": None,
                 "logs": ([{"address": "0xB", "logIndex": "0x0", "topics": ["0xtopic"], "data": "0x01",
                            "removed": False}] if i == 0 else [])} for i, t in enumerate(txs)]
    return block, receipts


def solana_fixture():
    message = {"header": {"numRequiredSignatures": 1, "numReadonlySignedAccounts": 0,
                          "numReadonlyUnsignedAccounts": 1},
               "accountKeys": ["payer", VOTE_PROGRAM], "addressTableLookups": [{"accountKey": "lookup"}],
               "instructions": [{"programIdIndex": 1, "accounts": [0, 2, 3], "data": "abc"}]}
    meta = {"err": None, "fee": 5000, "loadedAddresses": {"writable": ["writable"], "readonly": ["readonly"]},
            "preBalances": [10000, 1, 10, 20], "postBalances": [5000, 1, 11, 19],
            "preTokenBalances": [{"accountIndex": 2, "mint": "mint", "owner": "owner",
                                  "programId": "token", "uiTokenAmount": {"amount": "10000000000000000001", "decimals": 9}}],
            "postTokenBalances": [{"accountIndex": 2, "mint": "mint", "owner": "owner",
                                   "programId": "token", "uiTokenAmount": {"amount": "10000000000000000000", "decimals": 9}}],
            "innerInstructions": [{"index": 0, "instructions": [{"programIdIndex": 3, "accounts": [2],
                                                                  "data": "def", "stackHeight": 2}]}]}
    return {"blockHeight": 8, "blockTime": 100, "blockhash": "block", "previousBlockhash": "prev", "parentSlot": 9,
            "transactions": [{"transaction": {"signatures": ["sig"], "message": message}, "version": 0, "meta": meta}]}


def test_evm_precision_failure_and_source_pointers(tmp_path):
    block, receipts = evm_fixture()
    setup(tmp_path, "bsc", block, receipts)
    before = file_hashes(tmp_path, prefixes=("raw",))
    report = run(tmp_path)
    assert report["complete"]
    assert report["counts"]["transactions"]["bsc"] == 2
    assert file_hashes(tmp_path, prefixes=("raw",)) == before
    txs = records(tmp_path, "transactions")
    assert [t["execution_status"] for t in txs] == ["success", "failed"]
    assert txs[0]["fee_raw"] == "21"
    details = records(tmp_path, "evm_transaction_details")
    assert details[0]["value_raw"] == str(2 ** 255 + 123)
    assert details[0]["from_account"] == "eip155:56:0xA"
    logs = records(tmp_path, "evm_logs")
    assert json.loads(logs[0]["topics"]) == ["0xtopic"]
    assert logs[0]["raw_ref"] == "raw/bsc/receipts/10.json.gz#/result/0/logs/0"
    assert records(tmp_path, "balance_observations") == []
    for table, schema in SCHEMAS.items():
        for path in (tmp_path / "tables/base" / table).glob("*.parquet"):
            assert pq.read_schema(path) == schema


def test_base_fee_total_and_system_type(tmp_path):
    block, receipts = evm_fixture()
    setup(tmp_path, "base", block, receipts)
    assert run(tmp_path)["complete"]
    txs = records(tmp_path, "transactions")
    assert txs[0]["fee_raw"] == "26"
    assert txs[1]["is_system"] is False  # A user deposit is not a system transaction.


def test_base_l1_attributes_pair_is_identified_as_system(tmp_path):
    block,receipts=evm_fixture()
    block["transactions"][1].update({"from":"0xdeaddeaddeaddeaddeaddeaddeaddeaddead0001",
                                      "to":"0x4200000000000000000000000000000000000015"})
    setup(tmp_path,"base",block,receipts)
    run(tmp_path)
    assert records(tmp_path,"transactions")[1]["is_system"] is True


def test_sol_loaded_order_precision_and_ownership(tmp_path):
    setup(tmp_path, "solana", solana_fixture())
    report = run(tmp_path)
    assert report["complete"], report["errors"]
    accounts = records(tmp_path, "transaction_accounts")
    assert [r["account_id"] for r in accounts] == [f"solana:mainnet:{a}" for a in ["payer", VOTE_PROGRAM, "writable", "readonly"]]
    assert [r["is_writable"] for r in accounts] == [True, False, True, False]
    assert [r["is_signer"] for r in accounts] == [True, False, False, False]
    inst = records(tmp_path, "solana_instructions")
    assert len(inst) == 2
    assert inst[1]["program_id"] == "readonly"
    assert inst[1]["inner_index"] == 0
    assert json.loads(inst[0]["account_ids"])[1] == "solana:mainnet:writable"
    balances = records(tmp_path, "balance_observations")
    token = [b for b in balances if b["asset_id"] == "solana:mainnet:mint"][0]
    assert token["pre_amount_raw"] == "10000000000000000001"
    assert token["owner_address"] == "owner"
    txs = records(tmp_path, "transactions")
    assert txs[0]["is_vote"] is True
    assert any(r["predicate"] == "token_account_owner" for r in records(tmp_path, "object_relations"))


def test_new_version_preserves_failing_transaction(tmp_path):
    block = solana_fixture()
    block["transactions"][0]["version"] = 1
    block["transactions"][0]["transaction"]["message"]["transactionConfig"] = {"future": 123}
    block["transactions"][0]["meta"]["err"] = {"InstructionError": [0, "InvalidArgument"]}
    setup(tmp_path, "solana", block)
    before = file_hashes(tmp_path, ("raw",))
    report = run(tmp_path)
    assert report["complete"]
    assert report["warnings"][0]["code"] == "unrecognized_transaction_version"
    tx = records(tmp_path, "transactions")[0]
    assert tx["decode_status"] == "parsed_unknown_version"
    assert tx["execution_status"] == "failed"
    assert json.loads(tx["error_raw"])["InstructionError"][0] == 0
    assert file_hashes(tmp_path, ("raw",)) == before


def test_unknown_message_and_missing_meta_are_not_dropped(tmp_path):
    block = solana_fixture()
    block["transactions"][0]["transaction"]["message"] = {"futureVersionStructure": []}
    block["transactions"][0]["meta"] = None
    setup(tmp_path, "solana", block)
    report = run(tmp_path)
    assert not report["complete"]
    tx = records(tmp_path, "transactions")[0]
    assert tx["execution_status"] == "unknown"
    assert tx["decode_status"] == "unrecognized_message"
    assert tx["fee_raw"] is None
    assert tx["is_vote"] is None


def test_jsonparsed_keys_not_double_expanded(tmp_path):
    block = solana_fixture()
    msg = block["transactions"][0]["transaction"]["message"]
    msg["accountKeys"] = [{"pubkey": a, "signer": i == 0, "writable": i in (0, 2),
                           "source": "transaction" if i < 2 else "lookupTable"}
                          for i, a in enumerate(["payer", VOTE_PROGRAM, "writable", "readonly"])]
    setup(tmp_path, "solana", block)
    assert run(tmp_path)["complete"]
    assert len(records(tmp_path, "transaction_accounts")) == 4


def test_missing_receipt_does_not_fabricate_success(tmp_path):
    block, receipts = evm_fixture()
    setup(tmp_path, "bsc", block, receipts[:1])
    report = run(tmp_path)
    assert not report["complete"]
    assert records(tmp_path, "transactions")[1]["execution_status"] == "unknown"
    assert any(e["code"] == "missing_receipt" for e in report["errors"])


def test_receipt_other_fork_is_not_trusted(tmp_path):
    block, receipts = evm_fixture()
    receipts[0]["blockHash"] = "0xother"
    setup(tmp_path, "bsc", block, receipts)
    assert not run(tmp_path)["complete"]
    assert records(tmp_path, "transactions")[0]["execution_status"] == "unknown"
    assert len(records(tmp_path, "evm_logs")) == 1


def test_boundary_transactions_never_enter_main(tmp_path):
    block, receipts = evm_fixture()
    boundary = copy.deepcopy(block)
    boundary.update(number="0x9", timestamp="0x63", hash="0xprior")
    setup(tmp_path, "bsc", block, receipts, {9: boundary})
    report = run(tmp_path)
    assert report["complete"]
    assert len(records(tmp_path, "blocks")) == 2
    assert len(records(tmp_path, "transactions")) == 2
    assert sorted(b["window_membership"] for b in records(tmp_path, "blocks")) == ["boundary", "main"]


def test_missing_token_pre_balance_stays_null(tmp_path):
    block = solana_fixture()
    block["transactions"][0]["meta"]["preTokenBalances"] = []
    setup(tmp_path, "solana", block)
    assert run(tmp_path)["complete"]
    token = [b for b in records(tmp_path, "balance_observations") if b["asset_id"] == "solana:mainnet:mint"][0]
    assert token["pre_amount_raw"] is None


def test_replay_is_identical_and_input_not_changed(tmp_path):
    block, receipts = evm_fixture()
    setup(tmp_path, "bsc", block, receipts)
    run(tmp_path)
    before = file_hashes(tmp_path)
    run(tmp_path)
    assert file_hashes(tmp_path) == before


def test_amount_does_not_round_float():
    assert amount(2 ** 255) == str(2 ** 255)
    assert amount(float(2 ** 255)) is None
    assert amount(None) is None
    assert integer("0xff") == 255


def two_evm_blocks(root, first_time=100, second_time=300, order=(10, 11), unique_unknown=False):
    block, receipts = evm_fixture()
    block["timestamp"] = hex(first_time) if first_time is not None else None
    setup(root, "bsc", block, receipts)
    later, later_receipts = copy.deepcopy(block), copy.deepcopy(receipts)
    later.update(number="0xb", timestamp=hex(second_time) if second_time is not None else None,
                 hash="0xblock2", parentHash="0xblock")
    for tx, receipt in zip(later["transactions"], later_receipts):
        tx["hash"] += "later"
        receipt.update(transactionHash=tx["hash"], blockHash="0xblock2", blockNumber="0xb")
    if unique_unknown:
        later["transactions"][1]["from"] = "0xOnlyUnknownTime"
    save_raw(root / "raw/bsc/blocks/11.json.gz", {"result": later})
    save_raw(root / "raw/bsc/receipts/11.json.gz", {"result": later_receipts})
    from claire_demo.common import load_json
    window = load_json(root / "reports/window.json")
    window["chains"]["bsc"].update(main_blocks=list(order), expected_blocks=2)
    write_json(root / "reports/window.json", window)


@pytest.mark.parametrize("order", [(10, 11), (11, 10)])
@pytest.mark.parametrize("times", [(100, 300), (300, 100)])
def test_object_observation_evidence_and_global_minimum_are_distinct(tmp_path, order, times):
    two_evm_blocks(tmp_path, *times, order=order)
    raw_before = file_hashes(tmp_path, ("raw",))
    report = run(tmp_path)
    assert report["complete"], report["errors"]
    observations = [r for r in records(tmp_path, "objects") if r["object_id"] == "eip155:56:0xA"]
    assert len(observations) == 2
    assert {r["observed_at"] for r in observations} == {100, 300}
    assert {r["first_seen_in_window"] for r in observations} == {100}
    assert len({r["raw_ref"] for r in observations}) == 2
    assert {r["parser_version"] for r in observations} == {"claire-base/1.2.0"}
    assert file_hashes(tmp_path, ("raw",)) == raw_before
    assert report["object_first_seen"]["observation_rows"] == len(records(tmp_path, "objects"))


def test_unknown_observation_time_remains_unknown_and_blocks_complete_acceptance(tmp_path):
    two_evm_blocks(tmp_path, 100, None, order=(11, 10), unique_unknown=True)
    report = run(tmp_path)
    assert not report["complete"]
    objects = records(tmp_path, "objects")
    shared = [r for r in objects if r["object_id"] == "eip155:56:0xA"]
    assert {r["observed_at"] for r in shared} == {100, None}
    assert {r["first_seen_in_window"] for r in shared} == {100}
    only_unknown = [r for r in objects if r["object_id"] == "eip155:56:0xOnlyUnknownTime"]
    assert len(only_unknown) == 1
    assert only_unknown[0]["observed_at"] is None and only_unknown[0]["first_seen_in_window"] is None
    assert report["object_first_seen"]["objects_with_only_unknown_times"] >= 1


def test_saved_real_solana_blocks_keep_all_instruction_context():
    """Optional local audit reads retained RPC, never turns it into a fixture."""
    from claire_demo.common import load_json
    from claire_demo.normalize import BlockRows, _solana
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "raw/solana/blocks").glob("*.json.gz"))
    if not files:
        pytest.skip("No real local Solana raw blocks; synthetic unit coverage still runs")
    # Test actual resolved probe blocks only; full coverage belongs to validate.
    for path in (files[0], files[len(files) // 2], files[-1]):
        block = load_json(path)["result"]
        rows = BlockRows("solana", block["blockTime"])
        _solana(rows, block, int(path.name.split(".")[0]), str(path.relative_to(root)))
        assert not [issue for issue in rows.issues if issue["severity"] == "error"]
        assert len(rows.tables["transactions"]) == len(block["transactions"])
        for name, values in rows.tables.items():
            pa.Table.from_pylist(values, schema=SCHEMAS[name])
