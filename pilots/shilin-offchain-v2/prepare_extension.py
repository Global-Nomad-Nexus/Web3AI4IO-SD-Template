"""Audit all v1 metadata bodies and prepare the prespecified image queue.

Reads locally retained third-party bytes; writes only factual field states and
declared URL pointers to the new extension working directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import pyarrow as pa
import pyarrow.parquet as pq


FIELDS = (
    "name", "symbol", "description", "image", "createdOn", "showName",
    "website", "twitter", "telegram", "external_url", "discord", "github",
    "coin_community", "video",
)
PUBLIC_URL_FIELDS = frozenset((
    "image", "website", "twitter", "telegram", "external_url", "discord",
    "github", "coin_community",
))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def field_state(document: dict, field: str):
    if field not in document:
        return "absent", None
    value = document[field]
    if value is None:
        return "null", value
    if isinstance(value, str):
        return ("nonempty" if value.strip() else "empty"), value
    return "other_type", value


def safe_declared_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value


def prepare(v1_release: Path, v1_local_log: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    snapshots = pq.read_table(v1_release / "offchain_snapshots.parquet").to_pylist()
    cohort = pq.read_table(v1_release / "onchain_launch_cohort.parquet").to_pylist()
    local_requests = {x["request_id"]: x for x in map(json.loads, v1_local_log.read_text().splitlines())}
    public_requests = {x["request_id"]: x for x in map(json.loads, (v1_release / "offchain_requests.jsonl").read_text().splitlines())}
    if len(snapshots) != 57 or len(cohort) != 116:
        raise ValueError("Pinned v1 denominator changed")

    audit, documents, image_sources = [], {}, {}
    for snapshot in snapshots:
        rid = snapshot["request_id"]
        local = local_requests[rid]
        published = public_requests[rid]
        body = Path(local["raw_local_path"]).read_bytes()
        if sha(body) != snapshot["raw_sha256"] or sha(body) != published["raw_sha256"]:
            raise ValueError("v1 response digest mismatch: " + rid)
        document = json.loads(body.decode("utf-8-sig"))
        if not isinstance(document, dict):
            raise ValueError("v1 parseable JSON is no longer an object: " + rid)
        uri = snapshot["original_uri"]
        documents[uri] = document
        for field in FIELDS:
            state, value = field_state(document, field)
            url = safe_declared_url(value) if field in PUBLIC_URL_FIELDS else None
            audit.append({
                "snapshot_id": snapshot["snapshot_id"],
                "original_uri": uri,
                "field_name": field,
                "json_pointer": "/" + field,
                "field_state": state,
                "value_type": type(value).__name__ if state != "absent" else None,
                "value_sha256": sha(value.encode()) if isinstance(value, str) else None,
                "declared_url": url,
                "url_syntax_valid": url is not None if field in PUBLIC_URL_FIELDS and state == "nonempty" else None,
            })
        image = safe_declared_url(document.get("image"))
        if image:
            image_sources.setdefault(image, []).append(snapshot["snapshot_id"])

    comparisons = []
    for event in cohort:
        if event["platform_id"] != "pump.fun":
            continue
        uri = event["metadata_uri_declared"]
        if uri not in documents:
            raise ValueError("Missing Pump metadata URI from v1 snapshots: " + str(uri))
        document = documents[uri]
        name = document.get("name")
        symbol = document.get("symbol")
        comparisons.append({
            "launch_record_id": event["launch_record_id"],
            "object_id": event["object_id"],
            "original_uri": uri,
            "name_field_state": field_state(document, "name")[0],
            "symbol_field_state": field_state(document, "symbol")[0],
            "name_exact_match": name == event["name_declared"] if isinstance(name, str) else None,
            "symbol_exact_match": symbol == event["symbol_declared"] if isinstance(symbol, str) else None,
        })
    if len(audit) != 57 * len(FIELDS) or len(comparisons) != 61:
        raise ValueError("Field or event denominator mismatch")

    queue = [
        {"image_uri": image, "source_snapshot_ids": sorted(ids)}
        for image, ids in sorted(image_sources.items())
    ]
    pq.write_table(pa.Table.from_pylist(audit), output / "metadata_field_audit.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pylist(comparisons), output / "event_metadata_checks.parquet", compression="zstd")
    (output / "image_queue.json").write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n")
    result = {
        "v1_snapshots": len(snapshots), "field_audit_rows": len(audit),
        "pump_event_checks": len(comparisons), "distinct_image_uris": len(queue),
        "field_states": {field: dict(Counter(r["field_state"] for r in audit if r["field_name"] == field)) for field in FIELDS},
        "name_exact_match": dict(Counter(str(x["name_exact_match"]) for x in comparisons)),
        "symbol_exact_match": dict(Counter(str(x["symbol_exact_match"]) for x in comparisons)),
    }
    (output / "prepare_report.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-release", type=Path, required=True)
    parser.add_argument("--v1-local-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.v1_release, args.v1_local_log, args.output), indent=2))
