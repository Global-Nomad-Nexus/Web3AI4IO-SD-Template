"""Research event definitions over fixed decoded facts. No network code."""
from pathlib import Path
from collections import defaultdict, Counter
import hashlib
import json

import pyarrow as pa
import pyarrow.parquet as pq

from .common import file_hashes, write_json, load_json, START, END

VERSION = "claire-events/1.0.0"
S, I = pa.string(), pa.int64()
SCHEMA = pa.schema([(k, S) for k in ["event_id", "event_type", "definition_id", "definition_version", "chain_id", "subject_id", "event_time", "evidence_record_ids", "parameters", "observation_window", "coverage_status", "tx_id", "platform_id"]] + [("event_order", I), ("block_time", I), ("block_number_or_slot", I), ("threshold", I)])
CHAINS = ("solana:mainnet", "eip155:56", "eip155:8453")
LIFECYCLE = ("creation", "curve_complete", "migration", "pool_initialization", "liquidity_add", "liquidity_remove")


def make_event(row, kind, definition, threshold=None, evidence=None):
    source = row["source_record_id"]
    key = ":".join((definition, row["chain_id"], row["object_id"], source))
    timestamp = row.get("block_time")
    if timestamp is not None:
        from datetime import datetime, timezone
        timestamp_iso = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    else:
        timestamp_iso = None
    return dict(event_id=hashlib.sha256(key.encode()).hexdigest(), event_type=kind, definition_id=definition, definition_version=VERSION, chain_id=row["chain_id"], subject_id=row["object_id"], event_time=timestamp_iso, event_order=row.get("event_order"), evidence_record_ids=json.dumps(evidence or [source]), parameters=json.dumps({"distinct_successful_transactions": threshold} if threshold else {"native_operation": row["operation_type"]}, sort_keys=True), observation_window=json.dumps({"start": START, "end_exclusive": END}), coverage_status="observed_in_window;not_lifecycle_complete", tx_id=row["tx_id"], platform_id=row["platform_id"], block_time=timestamp, block_number_or_slot=row.get("block_number_or_slot"), threshold=threshold)


def ledger_order(row):
    return (row["block_time"], row.get("block_number_or_slot") or 0, row.get("tx_index") or 0, row.get("event_order") or 0, row["source_record_id"])


def derive(rows, thresholds=(1, 3)):
    """Deduplicate repeated trade logs/instructions by token and transaction.

    A trade record in a failed execution, a decoder error, an unknown token
    identity, or a missing block time cannot satisfy a research threshold.
    """
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in thresholds):
        raise ValueError("thresholds must be positive integers")
    groups, output, excluded = defaultdict(dict), [], Counter()
    for row in rows:
        if row.get("execution_effect") != "committed" or row.get("decode_status") != "decoded":
            excluded["not_committed_or_not_decoded"] += 1
            continue
        if not row.get("object_id") or row.get("block_time") is None:
            excluded["unknown_subject_or_time"] += 1
            continue
        op = row["operation_type"]
        if op in LIFECYCLE:
            output.append(make_event(row, op, "native." + op))
        elif op == "trade":
            key = (row["chain_id"], row["object_id"])
            prev = groups[key].get(row["tx_id"])
            if prev is None or ledger_order(row) < ledger_order(prev):
                groups[key][row["tx_id"]] = row
    for records in groups.values():
        trades = sorted(records.values(), key=ledger_order)
        for threshold in thresholds:
            if not isinstance(threshold, int) or threshold < 1:
                raise ValueError("thresholds must be positive integers")
            if len(trades) >= threshold:
                output.append(make_event(trades[threshold - 1], "window_activity_threshold", f"window_activity.{threshold}", threshold, [r["source_record_id"] for r in trades[:threshold]]))
    output.sort(key=lambda x: (x["chain_id"], x["block_time"], x["block_number_or_slot"] or 0, x["event_order"] or 0, x["event_id"]))
    summary = {cid: {"tokens_with_verified_trades": sum(k[0] == cid for k in groups), "qualifying_tokens": {str(n): sum(k[0] == cid and len(v) >= n for k, v in groups.items()) for n in thresholds}} for cid in CHAINS}
    return output, {"chains": summary, "excluded_records": dict(excluded), "thresholds": list(thresholds)}


def run(root, thresholds=(1, 3)):
    root = Path(root)
    before = file_hashes(root, ("raw", "tables/base"))
    files = sorted((root / "tables/decoded/platform_records").glob("*.parquet"))
    def rows():
        for p in files:
            for batch in pq.ParquetFile(p).iter_batches(batch_size=4096):
                yield from batch.to_pylist()
    output, report = derive(rows(), thresholds)
    window_path = root / "reports/window.json"
    scope = load_json(window_path) if window_path.exists() else {}
    if scope.get("validation_subset"):
        for row in output:
            row["coverage_status"] = "validation_subset;non_contiguous;not_full_window"
        report["scope"] = "validation_subset_only"
    path = root / "tables/events/events.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(output, schema=SCHEMA), path, compression="zstd")
    after = file_hashes(root, ("raw", "tables/base"))
    if before != after:
        raise RuntimeError("Event derivation altered raw/base inputs")
    report.update(status="completed" if files else "no_input", event_version=VERSION, events=len(output), input_shards=len(files), raw_base_unchanged=True, input_hashes=before, input_digest=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(), semantics="first threshold attainment within observed window, not first lifetime trade or token success")
    write_json(root / "reports/events.json", report)
    return report
