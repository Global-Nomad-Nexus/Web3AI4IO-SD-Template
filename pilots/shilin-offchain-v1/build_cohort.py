"""Derive the bounded token-launch queue from Claire's immutable pilot tables.

Usage: python build_cohort.py --claire-root PATH --output PATH
The input directory must contain tables/decoded/{platform_records,decoded_records}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq


WINDOW_START = 1789387200  # 2026-09-14T12:00:00Z
WINDOW_END = 1789387500    # 2026-09-14T12:05:00Z
PLATFORMS = {"pump.fun", "four.meme", "clanker"}
HF_REVISION = "8b29598a6565b67a8a943962dbf77f3d6b2559de"


def scan_rows(path: Path, columns: list[str]):
    for batch in ds.dataset(path, format="parquet").scanner(columns=columns, batch_size=65536).to_batches():
        yield from batch.to_pylist()


def iso(value):
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def stable_id(*parts):
    return hashlib.sha256("\x1f".join(str(x) for x in parts).encode()).hexdigest()[:24]


def build(claire_root: Path, output: Path):
    platform_cols = [
        "chain_id", "platform_id", "source_record_id", "tx_id", "object_id",
        "operation_type", "decoder_version", "execution_effect", "decode_status",
        "raw_ref", "block_time", "block_number_or_slot", "tx_index", "event_order",
    ]
    funnel = Counter()
    selected = []
    for row in scan_rows(claire_root / "tables/decoded/platform_records", platform_cols):
        funnel["platform_records_all"] += 1
        if row["platform_id"] not in PLATFORMS:
            continue
        funnel["target_platform"] += 1
        if row["operation_type"] != "creation":
            continue
        funnel["creation"] += 1
        if row["execution_effect"] != "committed":
            continue
        funnel["committed"] += 1
        if row["decode_status"] != "decoded":
            continue
        funnel["decoded"] += 1
        if not row["object_id"]:
            continue
        funnel["nonempty_object_id"] += 1
        if row["block_time"] is None or not WINDOW_START <= row["block_time"] < WINDOW_END:
            continue
        funnel["in_window"] += 1
        selected.append(row)

    keys = {(r["chain_id"], r["source_record_id"], r["tx_id"]) for r in selected}
    decoded_cols = [
        "chain_id", "source_record_id", "equivalent_source_record_id", "tx_id",
        "record_type", "decoded_arguments", "decode_status", "raw_ref",
    ]
    decoded = defaultdict(list)
    for row in scan_rows(claire_root / "tables/decoded/decoded_records", decoded_cols):
        key = (row["chain_id"], row["source_record_id"], row["tx_id"])
        if key in keys:
            decoded[key].append(row)

    events = []
    ambiguity = []
    for row in selected:
        key = (row["chain_id"], row["source_record_id"], row["tx_id"])
        matches = [r for r in decoded.get(key, []) if r["decode_status"] == "decoded"]
        if len(matches) != 1:
            ambiguity.append({"source_record_id": row["source_record_id"], "decoded_matches": len(matches)})
        match = matches[0] if len(matches) == 1 else None
        args_raw = match["decoded_arguments"] if match else None
        try:
            args = json.loads(args_raw) if args_raw else {}
        except json.JSONDecodeError:
            args = {}
            ambiguity.append({"source_record_id": row["source_record_id"], "issue": "invalid_decoded_arguments"})
        uri = args.get("uri") if row["platform_id"] == "pump.fun" else None
        object_id = row["object_id"]
        events.append({
            "launch_record_id": "launch:" + stable_id(*key),
            "chain_id": row["chain_id"],
            "platform_id": row["platform_id"],
            "object_id": object_id,
            "address_or_mint": object_id.rsplit(":", 1)[-1],
            "creation_tx_id": row["tx_id"],
            "creation_source_record_id": row["source_record_id"],
            "chain_event_time_unix": row["block_time"],
            "chain_event_time_utc": iso(row["block_time"]),
            "creation_raw_ref": row["raw_ref"],
            "decoded_raw_ref": match["raw_ref"] if match else None,
            "record_type": match["record_type"] if match else None,
            "decoded_arguments_raw": args_raw,
            "metadata_uri_declared": uri if isinstance(uri, str) and uri.strip() else None,
            "name_declared": args.get("name"),
            "symbol_declared": args.get("symbol"),
            "request_id_declared": str(args.get("requestId")) if args.get("requestId") is not None else None,
            "block_number_or_slot": row["block_number_or_slot"],
            "tx_index": row["tx_index"],
            "event_order": row["event_order"],
            "decoder_version": row["decoder_version"],
            "claire_hf_revision": HF_REVISION,
            "cohort_rule_version": "shilin-launch-cohort/1.0.0",
        })

    events.sort(key=lambda r: (r["chain_id"], r["chain_event_time_unix"], r["creation_tx_id"], r["creation_source_record_id"]))
    if len({r["launch_record_id"] for r in events}) != len(events):
        raise ValueError("Duplicate launch_record_id")
    output.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(events), output / "onchain_launch_cohort.parquet", compression="zstd")
    unique_objects = {(r["chain_id"], r["object_id"]) for r in events}
    report = {
        "claire_hf_revision": HF_REVISION,
        "window": {"start_inclusive": iso(WINDOW_START), "end_exclusive": iso(WINDOW_END)},
        "funnel": dict(funnel),
        "creation_events_by_platform": dict(Counter(r["platform_id"] for r in events)),
        "unique_tokens_by_platform": {p: len({(r["chain_id"], r["object_id"]) for r in events if r["platform_id"] == p}) for p in sorted(PLATFORMS)},
        "unique_objects_all": len(unique_objects),
        "pump_nonempty_uri": sum(bool(r["metadata_uri_declared"]) for r in events if r["platform_id"] == "pump.fun"),
        "decode_join_issues": ambiguity,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output / "cohort_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--claire-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.claire_root, args.output), indent=2))
