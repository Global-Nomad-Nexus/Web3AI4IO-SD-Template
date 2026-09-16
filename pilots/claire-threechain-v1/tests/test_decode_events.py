"""SYNTHETIC fixtures only. These tests are not observations from the study window."""
import base64
import json
import struct
from pathlib import Path

import base58
from eth_abi import encode
import pytest

from claire_demo.decode import (TRANSFER, TOKEN, SYSTEM, BorshReader,
                               decode_transfer, decode_evm_event, decode_anchor,
                               execution_frames, decode_solana_movement)
from claire_demo.events import derive
from claire_demo.registry import load


def transfer_log(amount=2**240 + 713):
    return dict(chain_id="eip155:56", emitter="0x" + "12" * 20, tx_id="synthetic-tx", log_id="synthetic-log", topics=json.dumps([TRANSFER, "0x" + "00" * 12 + "34" * 20, "0x" + "00" * 12 + "56" * 20]), data_hex="0x" + amount.to_bytes(32, "big").hex(), raw_ref="synthetic-only", block_time=100)


def test_uint256_precision_and_candidate_standard():
    row = decode_transfer(transfer_log(), {"execution_status": "success"})
    assert row["amount_raw"] == str(2**240 + 713)
    assert row["standard_status"] == "fungible_transfer_candidate"
    assert row["execution_effect"] == "committed"


def test_erc721_not_coerced_to_fungible_transfer():
    log = transfer_log()
    log["topics"] = json.loads(log["topics"]) + [log["data_hex"]]
    log["data_hex"] = "0x"
    assert decode_transfer(log, {"execution_status": "success"}) is None


@pytest.mark.parametrize("status,effect", [("failed", "not_committed"), ("unknown", "unknown")])
def test_failure_and_unknown_never_committed(status, effect):
    assert decode_transfer(transfer_log(), {"execution_status": status})["execution_effect"] == effect


def test_evm_dynamic_abi_indexed_address_and_precise_amount():
    event = {"inputs": [{"name": "token", "type": "address", "indexed": True}, {"name": "name", "type": "string", "indexed": False}, {"name": "amount", "type": "uint256", "indexed": False}]}
    result = decode_evm_event(event, [TRANSFER, "0x" + "00" * 12 + "34" * 20], "0x" + encode(["string", "uint256"], ["synthetic", 2**190]).hex())
    assert result["token"] == "0x" + "34" * 20
    assert result["amount"] == str(2**190)
    with pytest.raises(ValueError):
        decode_evm_event(event, [TRANSFER], "0x")
    with pytest.raises(ValueError, match="exact canonical"):
        decode_evm_event(event, [TRANSFER, "0x" + "00" * 12 + "34" * 20], "0x" + encode(["string", "uint256"], ["synthetic", 2**190]).hex() + "00" * 32)


def test_solana_caught_failure_and_ancestor_rollback():
    frames, _ = execution_frames(["Program A invoke [1]", "Program B invoke [2]", "Program C invoke [3]", "Program C success", "Program B failed: custom program error", "Program A success"], "success")
    assert [f["effect"] for f in frames] == ["committed", "not_committed", "not_committed"]
    frames, _ = execution_frames(["Program A invoke [1]", "Program A success"], "failed")
    assert frames[0]["effect"] == "not_committed"


def test_truncated_solana_logs_are_unknown():
    frames, events = execution_frames(["Program A invoke [1]", "Program data: YWJj", "Log truncated"], "success")
    assert frames[0]["effect"] == "unknown"
    assert len(events) == 1


def test_checked_token_transfer_keeps_amount_mint_and_effect():
    data = bytes([12]) + (2**63 + 123).to_bytes(8, "little") + bytes([9])
    ix = dict(chain_id="solana:mainnet", instruction_id="synthetic-ix", tx_id="synthetic-tx", program_id=TOKEN, account_ids=json.dumps(["solana:mainnet:src", "solana:mainnet:mint", "solana:mainnet:dst", "solana:mainnet:owner"]), data_raw=base58.b58encode(data).decode())
    row = decode_solana_movement(ix, "not_committed", {})
    assert row["amount_raw"] == str(2**63 + 123)
    assert row["asset_id"] == "solana:mainnet:mint"
    assert row["execution_effect"] == "not_committed"
    assert row["decimals"] == 9


def test_unchecked_token_transfer_unknown_mint_is_not_invented():
    ix = dict(chain_id="solana:mainnet", instruction_id="synthetic-ix", tx_id="synthetic-tx", program_id=TOKEN, account_ids=json.dumps(["s", "d", "o"]), data_raw=base58.b58encode(bytes([3]) + (12).to_bytes(8, "little")).decode())
    assert decode_solana_movement(ix, "committed", {})["asset_id"] is None


def test_anchor_exact_layout_and_unknown_version_trailing_bytes():
    item = {"name": "synthetic", "discriminator": list(range(8)), "args": [{"name": "amount", "type": "u64"}]}
    payload = bytes(range(8)) + (2**60).to_bytes(8, "little")
    assert decode_anchor(payload, item, {}) == {"amount": str(2**60)}
    with pytest.raises(ValueError, match="trailing"):
        decode_anchor(payload + b"\x00", item, {})
    with pytest.raises(ValueError, match="short"):
        decode_anchor(payload[:-1], item, {})
    with pytest.raises(ValueError, match="bool"):
        BorshReader(b"\x02", {}).value("bool")


def test_anchor_tuple_struct_option_bool_has_no_named_fields():
    defs = {"OptionBool": {"kind": "struct", "fields": ["bool"]}}
    assert BorshReader(b"\x01", defs).value({"defined": {"name": "OptionBool"}}) == [True]
    assert BorshReader(b"\x00", defs).value({"defined": {"name": "OptionBool"}}) == [False]


def platform_row(tx, n, **changes):
    row = dict(chain_id="eip155:56", platform_id="synthetic-platform", source_record_id=f"synthetic-log-{n}", tx_id=tx, object_id="eip155:56:synthetic-token", operation_type="trade", execution_effect="committed", decode_status="decoded", block_time=100 + n, tx_index=n, event_order=n)
    row.update(changes)
    return row


def test_event_threshold_counts_distinct_successful_transactions():
    rows = [platform_row("tx1", 1), platform_row("tx1", 2), platform_row("tx2", 3), platform_row("bad", 4, execution_effect="not_committed"), platform_row("unknown", 5, decode_status="decode_error")]
    events, summary = derive(rows)
    assert [x["threshold"] for x in events] == [1]
    assert summary["chains"]["eip155:56"]["qualifying_tokens"] == {"1": 1, "3": 0}
    rows.append(platform_row("tx3", 6))
    events, summary = derive(rows)
    by_threshold = {x["threshold"]: x for x in events}
    assert by_threshold[3]["block_time"] == 106
    assert len(json.loads(by_threshold[3]["evidence_record_ids"])) == 3
    assert all("not_lifecycle_complete" in x["coverage_status"] for x in events)


def test_no_trades_returns_real_zero_only_for_observed_inputs():
    events, summary = derive([])
    assert events == []
    assert all(x["tokens_with_verified_trades"] == 0 for x in summary["chains"].values())


def test_same_second_different_blocks_follow_ledger_not_tx_index():
    rows = [platform_row("later-block", 1, block_time=100, block_number_or_slot=11, tx_index=0), platform_row("earlier-block", 2, block_time=100, block_number_or_slot=10, tx_index=500)]
    events, _ = derive(rows, (1, 2))
    by_threshold = {x["threshold"]: x for x in events}
    assert by_threshold[1]["tx_id"] == "earlier-block"
    assert by_threshold[2]["tx_id"] == "later-block"


def test_registry_hash_mismatch_fails_closed(tmp_path):
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources/source").write_bytes(b"modified")
    (tmp_path / "sources/manifest.json").write_text(json.dumps([{"path": "sources/source", "sha256": "wrong"}]))
    with pytest.raises(ValueError, match="hash mismatch"):
        load(tmp_path)


def test_streamed_run_clanker_pool_attribution_and_event_input_immutability(tmp_path):
    """SYNTHETIC ABI and records; tests attribution, not deployed bytecode."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from claire_demo.decode import run, event_topics
    from claire_demo.events import run as events_run
    from claire_demo.common import file_hashes
    from claire_demo.schemas import SCHEMAS
    root = tmp_path
    (root / "config").mkdir()
    (root / "sources").mkdir()
    creation = {"name": "TokenCreated", "type": "event", "inputs": [{"name": "poolId", "type": "bytes32"}, {"name": "tokenAddress", "type": "address"}]}
    swap = {"name": "Swap", "type": "event", "inputs": [{"name": "id", "type": "bytes32", "indexed": True}, {"name": "amount0", "type": "int128"}]}
    (root / "sources/factory.json").write_text(json.dumps([creation]))
    (root / "sources/pool.json").write_text(json.dumps([swap]))
    factory, manager, token = ["0x" + byte * 20 for byte in ("11", "22", "33")]
    entries = [dict(platform_id=p, chain_id="eip155:8453", program_or_contract=a, version="synthetic-test-only", layout_path="sources/" + f + ".json", source_revision="synthetic", verification_status="synthetic") for p, a, f in [("clanker", factory, "factory"), ("uniswap.v4", manager, "pool")]]
    (root / "config/platform_registry.json").write_text(json.dumps(entries))
    txid = "eip155:8453:tx:synthetic"
    tx = dict(chain="base", chain_id="eip155:8453", tx_id=txid, tx_index=0, block_time=100, execution_status="success")
    pid = bytes.fromhex("44" * 32)
    logs = [dict(chain="base", chain_id="eip155:8453", tx_id=txid, block_time=100, log_id=txid + ":log:1", log_index=1, emitter=manager, topics=json.dumps([next(iter(event_topics([swap]))), "0x" + pid.hex()]), data_hex="0x" + encode(["int128"], [-7]).hex()), dict(chain="base", chain_id="eip155:8453", tx_id=txid, block_time=100, log_id=txid + ":log:2", log_index=2, emitter=factory, topics=json.dumps([next(iter(event_topics([creation])))]), data_hex="0x" + encode(["bytes32", "address"], [pid, token]).hex())]
    for name, rows in [("transactions", [tx]), ("evm_logs", logs)]:
        folder = root / "tables/base" / name
        folder.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMAS[name]), folder / "base-10.parquet")
    before = file_hashes(root)
    report = run(root)
    assert report["clanker_v4_pools_evidenced_in_snapshot"] == 1
    platforms = pq.read_table(root / "tables/decoded/platform_records/base-10.parquet").to_pylist()
    assert {x["operation_type"] for x in platforms} == {"creation", "trade"}
    assert all(x["object_id"] == "eip155:8453:" + token for x in platforms)
    report = events_run(root)
    assert report["chains"]["eip155:8453"]["qualifying_tokens"] == {"1": 1, "3": 0}
    events_run(root, (2, 4))
    assert before == file_hashes(root)


def test_empty_transaction_block_gets_typed_decoded_shards(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from claire_demo.decode import run, SCHEMAS
    from claire_demo.schemas import SCHEMAS as BASE
    path = tmp_path / "tables/base/transactions"
    path.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist([], schema=BASE["transactions"]), path / "base-10.parquet")
    report = run(tmp_path)
    assert report["status"] == "completed"
    for name in ("decoded_records", "asset_movements", "platform_records"):
        table = pq.read_table(tmp_path / "tables/decoded" / name / "base-10.parquet")
        assert table.num_rows == 0
        assert table.schema == SCHEMAS[name]


def test_anchor_log_and_emit_cpi_paired_without_collapsing_repeated_events(tmp_path):
    """SYNTHETIC: two identical events, each observed through two channels."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from claire_demo.decode import run, ANCHOR_EVENT_CPI
    from claire_demo.common import save_raw
    from claire_demo.schemas import SCHEMAS
    root = tmp_path
    (root / "config").mkdir(); (root / "sources").mkdir()
    program, mint = base58.b58encode(b"P" * 32).decode(), base58.b58encode(b"M" * 32).decode()
    event_discriminator, buy_discriminator = bytes(range(8)), bytes(range(8, 16))
    payload = event_discriminator + b"M" * 32 + (7).to_bytes(8, "little")
    idl = {"instructions": [{"name": "buy", "discriminator": list(buy_discriminator), "args": []}], "events": [{"name": "TradeEvent", "discriminator": list(event_discriminator)}], "types": [{"name": "TradeEvent", "type": {"kind": "struct", "fields": [{"name": "mint", "type": "pubkey"}, {"name": "amount", "type": "u64"}]}}]}
    (root / "sources/idl.json").write_text(json.dumps(idl))
    (root / "config/platform_registry.json").write_text(json.dumps([dict(platform_id="synthetic-pump", chain_id="solana:mainnet", program_or_contract=program, version="synthetic-test-only", layout_path="sources/idl.json", source_revision="synthetic")]))
    logs = [f"Program {program} invoke [1]"]
    for _ in range(2):
        logs.extend(["Program data: " + base64.b64encode(payload).decode(), f"Program {program} invoke [2]", f"Program {program} success"])
    logs.append(f"Program {program} success")
    save_raw(root / "raw/solana/blocks/10.json.gz", {"result": {"transactions": [{"transaction": {"signatures": ["synthetic-signature"]}, "meta": {"logMessages": logs}}]}})
    txid = "solana:mainnet:tx:synthetic-signature"
    tx = dict(chain="solana", chain_id="solana:mainnet", tx_id=txid, tx_index=0, block_time=100, execution_status="success")
    instructions = [dict(chain="solana", chain_id="solana:mainnet", tx_id=txid, instruction_id=f"{txid}:ix:0:{idx}", outer_index=0, inner_index=None if idx == "outer" else idx, program_id=program, account_ids="[]", data_raw=base58.b58encode(data).decode()) for idx, data in [("outer", buy_discriminator), (0, ANCHOR_EVENT_CPI + payload), (1, ANCHOR_EVENT_CPI + payload)]]
    for name, rows in [("transactions", [tx]), ("solana_instructions", instructions)]:
        folder = root / "tables/base" / name
        folder.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMAS[name]), folder / "solana-10.parquet")
    run(root)
    platforms = pq.read_table(root / "tables/decoded/platform_records/solana-10.parquet").to_pylist()
    decoded = pq.read_table(root / "tables/decoded/decoded_records/solana-10.parquet").to_pylist()
    assert len(platforms) == 2  # Four observations represent two operations.
    assert sum(r["equivalent_source_record_id"] is not None for r in decoded) == 2
    assert all(x["object_id"] == "solana:mainnet:" + mint for x in platforms)
    assert [x["event_order"] for x in platforms] == [1, 4]


def test_same_address_evidence_selection_uses_row_observation_not_global_first_seen():
    from claire_demo.decode import keep_address_observation, same_address_link
    address = "0x" + "55" * 20
    late = dict(object_id="eip155:56:" + address, first_seen_in_window=10, observed_at=30, raw_ref="raw/bsc/later-role")
    early = dict(object_id=late["object_id"], first_seen_in_window=10, observed_at=20, raw_ref="raw/bsc/earlier-address")
    unknown = dict(object_id=late["object_id"], first_seen_in_window=1, observed_at=None, raw_ref="raw/bsc/unknown-time")
    addresses = {}
    for row in (late, unknown, early):
        keep_address_observation(addresses, address, row)
    assert addresses[address]["raw_ref"] == "raw/bsc/earlier-address"
    other = dict(object_id="eip155:8453:" + address, first_seen_in_window=5, observed_at=25, raw_ref="raw/base/actual-observation")
    link = same_address_link(address, addresses[address], other)
    assert link["observed_at"] == 25
    assert json.loads(link["evidence_ref"]) == ["raw/bsc/earlier-address", "raw/base/actual-observation"]
    assert link["relation_type"] == "same_address_bytes"


def test_same_address_missing_observation_time_is_null_never_first_seen_or_epoch():
    from claire_demo.decode import same_address_link
    left = dict(object_id="eip155:56:address", first_seen_in_window=10, observed_at=None, raw_ref="raw/bsc/source")
    right = dict(object_id="eip155:8453:address", first_seen_in_window=15, observed_at=20, raw_ref="raw/base/source")
    link = same_address_link("address", left, right)
    assert link["observed_at"] is None
    assert "timestamps are unknown" in link["uncertainty_reason"]
    left["observed_at"] = 0
    right["observed_at"] = 0
    assert same_address_link("address", left, right)["observed_at"] == 0
