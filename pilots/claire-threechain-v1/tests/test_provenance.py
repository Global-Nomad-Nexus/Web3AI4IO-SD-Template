"""SYNTHETIC provenance fixtures; no research data or network requests."""
import json
import hashlib
import pyarrow.parquet as pq
import pytest

from claire_demo.provenance import infer_context, parse_record, run
from claire_demo.common import save_raw, sha256

HASH = "0x" + "12" * 32
TXHASH = "0x" + "34" * 32


def record(method, params):
    return dict(source_id="synthetic", endpoint="https://user:secret@rpc.example:443/key-value?apiKey=private", rpc_method=method, request_params=params, requested_at="2026-09-14T12:00:00Z", retrieved_at="2026-09-14T12:00:01Z", chain_id="eip155:8453", response_status="ok", retry_count=0)


def test_evm_block_response_and_request_conflict():
    assert infer_context("eth_getBlockByNumber", ["0x20", True], {"result": {"number": "0x20", "hash": HASH}}) == (32, HASH, "evm_block_response", "resolved")
    assert infer_context("eth_getBlockByNumber", ["0x20", True], {"result": {"number": "0x21", "hash": HASH}})[3] == "conflict"


def test_transaction_receipt_uses_block_not_transaction_hash():
    row = parse_record(record("eth_getTransactionReceipt", [TXHASH]), {"result": {"transactionHash": TXHASH, "blockNumber": "0x10", "blockHash": HASH}}, 3)
    assert row["block_number_or_slot"] == 16
    assert row["block_hash"] == HASH
    assert row["endpoint"] == "https://rpc.example:443"
    null = parse_record(record("eth_getTransactionReceipt", [TXHASH]), {"result": None}, 4)
    assert null["block_number_or_slot"] is None and null["block_hash"] is None


def test_receipt_array_requires_consistent_single_block():
    receipts = [{"blockNumber": "0x10", "blockHash": HASH}, {"blockNumber": "0x10", "blockHash": HASH}]
    assert infer_context("eth_getBlockReceipts", ["latest"], {"result": receipts}) == (16, HASH, "uniform_receipt_array", "resolved")
    receipts[1]["blockNumber"] = "0x11"
    result = infer_context("eth_getBlockReceipts", ["0x10"], {"result": receipts})
    assert result[:2] == (None, None) and result[3] == "conflict"
    assert infer_context("eth_getBlockReceipts", ["0x10"], {"result": []}) == (16, None, "explicit_request_reference", "requested_only")


def test_solana_slot_is_not_blockheight_or_commitment_dictionary():
    assert infer_context("getBlock", [100, {"commitment": "finalized"}], {"result": {"blockHeight": 90, "blockhash": "SolanaBlockHash"}})[:2] == (100, "SolanaBlockHash")
    assert infer_context("getSlot", [{"commitment": "finalized"}], {"result": 123})[:2] == (123, None)
    assert infer_context("getSlot", [{"commitment": "finalized"}], {"result": None})[:2] == (None, None)
    assert infer_context("getTransaction", ["signature"], {"result": {"slot": 456, "transaction": {"message": {"recentBlockhash": "NotTheContainingBlockHash"}}}})[:2] == (456, None)


def test_listing_does_not_claim_a_single_block_and_none_stays_unknown():
    assert infer_context("getBlocks", [1, 4], {"result": [1, 2, 4]})[:2] == (None, None)
    assert infer_context("getBlocks", [1, 4], {"result": [2]})[:2] == (None, None)
    assert infer_context("getBlocks", [1, 4], {"result": None})[:2] == (None, None)
    assert infer_context("eth_chainId", [], {"result": "0x2105"})[:2] == (None, None)
    assert infer_context("eth_getCode", ["0x" + "11" * 20, "latest"], {"result": "0xdeadbeef"})[:2] == (None, None)
    assert infer_context("eth_getLogs", [{"fromBlock": "0x1", "toBlock": "0x2"}], {"result": [{"blockNumber": "0x1", "blockHash": HASH}, {"blockNumber": "0x2", "blockHash": TXHASH}]})[3] == "unknown"


def test_failed_http_wrapper_preserves_both_statuses_without_credentials():
    item = record("getSlot", [{"commitment": "finalized", "api_key": "private", "callback": "https://foo:key@site.example/path/credential?x=secret"}])
    item.update(response_status="transport_error", http_status=429, retry_count=2)
    row = parse_record(item, {"http_status": 429, "body": json.dumps({"error": {"code": -32005, "message": "provider failure"}})}, 5)
    assert row["response_status"] == "transport_error"
    assert row["raw_response_status"] == "http_rpc_error"
    assert row["error_code"] == "-32005" and row["http_status"] == 429
    assert row["block_number_or_slot"] is None
    assert "private" not in row["request_params"] and "credential" not in row["request_params"]
    assert row["request_params_redacted"] is True


def test_run_preserves_ledger_and_captures_each_line(tmp_path):
    raw = tmp_path / "raw/requests/test.json.gz"
    save_raw(raw, {"result": {"number": "0x10", "hash": HASH}})
    item = record("eth_getBlockByNumber", ["0x10", True])
    item.update(raw_path="raw/requests/test.json.gz", raw_sha256=sha256(raw))
    ledger = tmp_path / "provenance/request_log.jsonl"
    ledger.parent.mkdir()
    ledger.write_text(json.dumps(item) + "\n" + json.dumps(record("getSlot", [{"commitment": "finalized"}])) + "\n")
    before = ledger.read_bytes()
    report = run(tmp_path)
    rows = pq.read_table(tmp_path / "provenance/requests.parquet").to_pylist()
    assert report["passed"] and report["rows"] == 2
    assert [r["ledger_line"] for r in rows] == [1, 2]
    assert rows[0]["raw_integrity"] == "matched" and rows[0]["block_number_or_slot"] == 16
    assert rows[1]["block_number_or_slot"] is None
    assert ledger.read_bytes() == before


def test_checksum_mismatch_is_reported_without_using_untrusted_response(tmp_path):
    raw = tmp_path / "raw/requests/test.json.gz"
    save_raw(raw, {"result": {"transactionHash": TXHASH, "blockNumber": "0x10", "blockHash": HASH}})
    item = record("eth_getTransactionReceipt", [TXHASH])
    item.update(raw_path="raw/requests/test.json.gz", raw_sha256="wrong")
    ledger = tmp_path / "provenance/request_log.jsonl"
    ledger.parent.mkdir(); ledger.write_text(json.dumps(item) + "\n")
    report = run(tmp_path)
    row = pq.read_table(tmp_path / "provenance/requests.parquet").to_pylist()[0]
    assert report["passed"] is False
    assert row["raw_integrity"] == "mismatch" and row["block_number_or_slot"] is None


def test_incomplete_appended_line_is_not_silently_parsed(tmp_path):
    ledger = tmp_path / "provenance/request_log.jsonl"
    ledger.parent.mkdir(); ledger.write_bytes((json.dumps(record("getSlot", [])) + "\n").encode() + b'{"pending":')
    before = ledger.read_bytes()
    report = run(tmp_path)
    assert report["rows"] == 1 and report["unparsed_trailing_bytes"] == len(b'{"pending":')
    assert before == ledger.read_bytes()
