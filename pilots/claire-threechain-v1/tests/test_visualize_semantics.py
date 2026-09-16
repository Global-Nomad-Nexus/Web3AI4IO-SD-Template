"""SYNTHETIC table fixtures for graph and figure fact semantics; no rendering."""
from pathlib import Path
import json

import pyarrow as pa
import pyarrow.parquet as pq

from claire_demo.common import CHAINS, write_json, file_hashes
from claire_demo.decode import SCHEMAS as DECODED
from claire_demo.events import SCHEMA as EVENT_SCHEMA
from claire_demo.schemas import SCHEMAS as BASE
from claire_demo.visualize import (_coverage, _transaction_summaries,
                                  _event_summaries, _graph_tables,
                                  _platform_summaries)


def put(root, layer, table, schema, rows, name="test.parquet"):
    path = root / "tables" / layer / table / name
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    return path


def test_partial_chain_unobserved_30_second_bins_are_unknown(tmp_path):
    put(tmp_path, "base", "transactions", BASE["transactions"], [dict(chain="bsc", chain_id=CHAINS["bsc"], block_time=1, execution_status="success", is_vote=False, is_system=False)], "bsc-1.parquet")
    rows, _ = _transaction_summaries(tmp_path, 0, 60, dict.fromkeys(CHAINS, False))
    bins = {r["bin_index"]: r for r in rows if r["chain"] == "bsc"}
    assert bins[0]["observed_transactions"] == 1
    assert bins[1]["observed_transactions"] is None
    assert bins[1]["excluding_identified_vote_system"] is None


def test_complete_chain_has_actual_zero_bins_and_correct_half_open_boundaries(tmp_path):
    rows = [dict(chain="bsc", chain_id=CHAINS["bsc"], block_time=ts, execution_status="success", is_vote=False, is_system=False) for ts in (-1, 0, 29, 30, 59, 60)]
    put(tmp_path, "base", "transactions", BASE["transactions"], rows, "bsc-1.parquet")
    bins, _ = _transaction_summaries(tmp_path, 0, 90, dict.fromkeys(CHAINS, True))
    assert [r["observed_transactions"] for r in bins if r["chain"] == "bsc"] == [2, 2, 1]
    assert all(r["observed_transactions"] == 0 for r in bins if r["chain"] == "base")
    bins, _ = _transaction_summaries(tmp_path, 0, 60, dict.fromkeys(CHAINS, True))
    assert [r["observed_transactions"] for r in bins if r["chain"] == "bsc"] == [2, 2]


def test_file_counts_do_not_override_failed_normalization(tmp_path):
    raw = tmp_path / "raw/bsc/blocks/1.json.gz"
    raw.parent.mkdir(parents=True); raw.write_bytes(b"synthetic existence check")
    put(tmp_path, "base", "blocks", BASE["blocks"], [], "bsc-1.parquet")
    write_json(tmp_path / "reports/collection.json", {"chains": {"bsc": {"complete": True}}})
    write_json(tmp_path / "reports/normalization.json", {"complete": False, "errors": [{"chain": "bsc", "code": "missing_receipt"}]})
    write_json(tmp_path / "reports/validation.json", {"passed": True})
    window = {"chains": {"bsc": {"resolved": True, "expected_blocks": 1, "main_blocks": [1]}}}
    row = next(r for r in _coverage(tmp_path, window) if r["chain"] == "bsc")
    assert row["core_coverage"] != "complete"


def event_fixture(root, thresholds=(1, 3), native_event=True, same_second=False):
    rows = []
    if native_event:
        rows.append(dict(chain_id=CHAINS["bsc"], subject_id="bsc-token", event_type="creation", definition_id="native.creation", threshold=None, block_time=0))
    for n in thresholds:
        rows.append(dict(chain_id=CHAINS["bsc"], subject_id="bsc-token", event_type="window_activity_threshold", definition_id=f"window_activity.{n}", threshold=n, block_time=1 if same_second else n, event_id=str(n), event_time=f"time-{n}"))
    path = root / "tables/events/events.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=EVENT_SCHEMA), path)
    write_json(root / "reports/events.json", dict(status="completed", thresholds=list(thresholds), chains={cid: {"tokens_with_verified_trades": int(chain == "bsc")} for chain, cid in CHAINS.items()}))


def test_nullable_thresholds_are_not_stringified_as_float_keys(tmp_path):
    # Native lifecycle rows force pandas nullable int64 -> float64 (1.0 / 3.0).
    event_fixture(tmp_path)
    rows, deltas, available = _event_summaries(tmp_path, dict.fromkeys(CHAINS, True))
    assert [r["event_count"] for r in rows if r["chain"] == "bsc"] == [1, 1]
    assert deltas[0]["delta_seconds"] == 2 and available


def test_unevaluated_definition_is_unknown_not_zero(tmp_path):
    event_fixture(tmp_path, (1,), native_event=False)
    rows, _, available = _event_summaries(tmp_path, dict.fromkeys(CHAINS, True))
    assert next(r for r in rows if r["chain"] == "bsc" and r["threshold"] == 3)["event_count"] is None
    assert available is False


def test_partial_inputs_do_not_make_empty_chain_event_count_a_verified_zero(tmp_path):
    event_fixture(tmp_path)
    rows, _, _ = _event_summaries(tmp_path, dict.fromkeys(CHAINS, False))
    assert all(r["event_count"] is None for r in rows if r["chain"] == "base")
    assert [r["event_count"] for r in rows if r["chain"] == "bsc"] == [1, 1]


def test_attainments_in_one_block_second_have_legitimate_zero_delay(tmp_path):
    event_fixture(tmp_path, same_second=True)
    _, deltas, _ = _event_summaries(tmp_path, dict.fromkeys(CHAINS, True))
    assert deltas[0]["delta_seconds"] == 0


def test_graph_selection_effects_infrastructure_and_jaccard_keep_chain_ids(tmp_path):
    cid, bid = CHAINS["bsc"], CHAINS["base"]
    token_a, token_b, other_chain_token = cid + ":tokenA", cid + ":tokenB", bid + ":tokenA"
    a, b, infrastructure = cid + ":a", cid + ":b", cid + ":router"
    platforms = [dict(chain_id=c, platform_id="synthetic", object_id=t, block_time=1, decode_status="decoded", execution_effect="committed") for c, t in [(cid, token_a), (cid, token_b), (bid, other_chain_token)]]
    put(tmp_path, "decoded", "platform_records", DECODED["platform_records"], platforms)
    moves = []
    for token, source, target, effect, standard in [(token_a, a, infrastructure, "committed", "platform_fungible_token"), (token_a, infrastructure, a, "committed", "platform_fungible_token"), (token_b, b, infrastructure, "committed", "platform_fungible_token"), (token_a, cid + ":failed", a, "not_committed", "platform_fungible_token"), (token_a, cid + ":candidate", a, "committed", "fungible_transfer_candidate"), (other_chain_token, bid + ":a", bid + ":router", "committed", "platform_fungible_token")]:
        moves.append(dict(chain_id=bid if token == other_chain_token else cid, asset_id=token, from_account=source, to_account=target, execution_effect=effect, standard_status=standard, movement_type="transfer", amount_raw="1", block_time=1))
    put(tmp_path, "decoded", "asset_movements", DECODED["asset_movements"], moves)
    put(tmp_path, "decoded", "platform_registry", DECODED["platform_registry"], [dict(chain_id=cid, program_or_contract="router", source_revision="synthetic")])
    before = file_hashes(tmp_path, ("tables",))
    selected, edges, gog, roles, available = _graph_tables(tmp_path, 0, 10)
    assert next(r for r in selected if r["asset_id"] == token_a)["local_graph"] is True
    assert next(r for r in selected if r["asset_id"] == token_b)["local_graph"] is False
    assert len(gog) == 1 and gog[0]["chain"] == "bsc"
    assert gog[0]["shared_addresses"] == 1 and gog[0]["union_addresses"] == 3
    assert abs(gog[0]["jaccard"] - 1 / 3) < 1e-12
    assert next(r for r in roles if r["account_id"] == infrastructure)["roles"] == "platform_contract"
    assert all("failed" not in e["from_account"] and "candidate" not in e["from_account"] for e in edges)
    assert before == file_hashes(tmp_path, ("tables",)) and available


def test_platform_failure_remains_separate_from_committed_records(tmp_path):
    put(tmp_path, "decoded", "platform_records", DECODED["platform_records"], [dict(chain_id=CHAINS["bsc"], platform_id="four.meme", source_record_id=str(i), tx_id=str(i), operation_type="trade", execution_effect=effect, decode_status="decoded", block_time=1) for i, effect in enumerate(("committed", "not_committed"))], "bsc-1.parquet")
    rows = _platform_summaries(tmp_path, 0, 60, dict.fromkeys(CHAINS, False))
    trade = [r for r in rows if r["chain"] == "bsc" and r["operation"] == "trade"]
    assert len(trade) == 2
    assert {r["execution_effect"] for r in trade} == {"committed", "not_committed"}
    assert all(r["record_count"] == 1 for r in trade)
