"""Freeze a rights-limited, hash-verified extension of Shilin's v1 pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shilin-offchain-v1"))
from process_linkage import cid_integrity  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def log_rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def check_local_body(rec: dict):
    path_value = rec.get("raw_local_path")
    if path_value:
        path = Path(path_value)
        if not path.exists() or sha(path) != rec.get("raw_sha256"):
            raise ValueError("Local response hash mismatch: " + rec["request_id"])


def media_magic(rec: dict):
    if rec.get("status") != "response_saved" or not rec.get("raw_local_path"):
        return None
    head = Path(rec["raw_local_path"]).read_bytes()[:512]
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp"
    if head[4:12] in (b"ftypavif", b"ftypavis"):
        return "avif"
    if b"<svg" in head[:256].lower():
        return "svg"
    return "unknown"


def metadata_parse_status(rec: dict):
    if rec.get("status") != "response_saved" or not rec.get("raw_local_path"):
        return None
    try:
        document = json.loads(Path(rec["raw_local_path"]).read_bytes().decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        return "parse_error"
    return "json_object" if isinstance(document, dict) else "json_non_object"


def public_receipt(rec: dict, key: str):
    return {
        "request_id": rec["request_id"],
        key: rec[key],
        "requested_at_utc": rec["requested_at_utc"],
        "retrieved_at_utc": rec["retrieved_at_utc"],
        "status": rec["status"],
        "status_code": rec["status_code"],
        "resolved_url": rec.get("resolved_url"),
        "redirects_json": json.dumps(rec.get("redirects", []), ensure_ascii=False),
        "content_type": rec.get("content_type"),
        "byte_count": rec.get("byte_count"),
        "raw_sha256": rec.get("raw_sha256"),
        "error": rec.get("error"),
        "collector_version": rec.get("collector_version"),
    }


def write(rows: list[dict], path: Path):
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")


def freeze(v1_release: Path, prepared: Path, refetch_log: Path,
           image_log: Path, output: Path, protocol_commit: str):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Release directory must be empty: " + str(output))
    output.mkdir(parents=True, exist_ok=True)
    old_snapshots = pq.read_table(v1_release / "offchain_snapshots.parquet").to_pylist()
    old_by_uri = {x["original_uri"]: x for x in old_snapshots}
    cohort = pq.read_table(v1_release / "onchain_launch_cohort.parquet").to_pylist()
    old_declarations = pq.read_table(v1_release / "offchain_declarations.parquet").to_pylist()
    old_coverage = {x["launch_record_id"]: x for x in pq.read_table(v1_release / "coverage_ledger.parquet").to_pylist()}
    fields = pq.read_table(prepared / "metadata_field_audit.parquet").to_pylist()
    checks = pq.read_table(prepared / "event_metadata_checks.parquet").to_pylist()
    images = json.loads((prepared / "image_queue.json").read_text())
    refetch_raw = log_rows(refetch_log)
    image_raw = log_rows(image_log)
    if len(old_snapshots) != 57 or len(cohort) != 116 or len(old_declarations) != 39 or len(fields) != 798 or len(checks) != 61 or len(images) != 56:
        raise ValueError("Pinned extension denominators changed")

    events_by_snapshot = {}
    event_by_id = {x["launch_record_id"]: x for x in cohort}
    for event in cohort:
        if event["platform_id"] == "pump.fun":
            snapshot_id = old_by_uri[event["metadata_uri_declared"]]["snapshot_id"]
            events_by_snapshot.setdefault(snapshot_id, []).append(event["launch_record_id"])
    objects_by_url = {}
    for declaration in old_declarations:
        objects_by_url.setdefault(declaration["normalized_value"], set()).update(
            event_by_id[eid]["object_id"] for eid in events_by_snapshot[declaration["snapshot_id"]]
        )
    semantic_rows = []
    for declaration in old_declarations:
        field = declaration["field_name"]
        target = declaration["target_class"]
        if field == "website":
            semantic_state = "expected_web_target" if target == "other_web_url" else "field_target_needs_review"
        elif field in ("twitter", "x"):
            semantic_state = "expected_social_profile" if target == "social_profile_or_path" else "post_not_account" if target == "social_post" else "target_needs_redirect_review"
        elif field == "telegram":
            semantic_state = "expected_telegram_path" if target == "telegram_path" else "field_target_needs_review"
        else:
            semantic_state = "target_needs_review"
        semantic_rows.append({
            "declaration_id": declaration["declaration_id"],
            "snapshot_id": declaration["snapshot_id"],
            "field_name": field,
            "declared_url": declaration["normalized_value"],
            "target_class": target,
            "semantic_state": semantic_state,
            "distinct_token_count_for_url": len(objects_by_url[declaration["normalized_value"]]),
        })

    refetch_by_uri = {}
    for rec in refetch_raw:
        uri = rec["original_uri"]
        if uri not in old_by_uri or uri in refetch_by_uri:
            raise ValueError("Unexpected or duplicate metadata refetch URI: " + uri)
        check_local_body(rec)
        refetch_by_uri[uri] = rec
    image_by_uri = {}
    image_uris = {x["image_uri"] for x in images}
    for rec in image_raw:
        uri = rec["image_uri"]
        if uri not in image_uris or uri in image_by_uri:
            raise ValueError("Unexpected or duplicate image URI: " + uri)
        check_local_body(rec)
        image_by_uri[uri] = rec

    refetch_rows = []
    for uri in sorted(old_by_uri):
        old = old_by_uri[uri]
        rec = refetch_by_uri.get(uri)
        if rec:
            row = public_receipt(rec, "original_uri")
            row["same_bytes_as_v1"] = rec["raw_sha256"] == old["raw_sha256"] if rec["status"] == "response_saved" else None
            row["second_parse_status"] = metadata_parse_status(rec)
        else:
            row = {key: None for key in ("request_id", "requested_at_utc", "retrieved_at_utc", "status_code", "resolved_url", "redirects_json", "content_type", "byte_count", "raw_sha256", "error", "collector_version")}
            row.update(original_uri=uri, status="not_attempted", same_bytes_as_v1=None, second_parse_status=None)
        row["v1_snapshot_id"] = old["snapshot_id"]
        row["v1_raw_sha256"] = old["raw_sha256"]
        refetch_rows.append(row)

    image_rows = []
    for item in images:
        uri = item["image_uri"]
        rec = image_by_uri.get(uri)
        if rec:
            row = public_receipt(rec, "image_uri")
        else:
            row = {key: None for key in ("request_id", "requested_at_utc", "retrieved_at_utc", "status_code", "resolved_url", "redirects_json", "content_type", "byte_count", "raw_sha256", "error", "collector_version")}
            row.update(image_uri=uri, status="not_attempted")
        row["source_snapshot_ids"] = item["source_snapshot_ids"]
        row["content_type_is_image"] = bool(rec and rec["status"] == "response_saved" and (rec.get("content_type") or "").split(";", 1)[0].lower().startswith("image/")) if rec and rec["status"] == "response_saved" else None
        row["media_magic"] = media_magic(rec) if rec else None
        row["cid_integrity_status"] = cid_integrity(uri, Path(rec["raw_local_path"]).read_bytes()) if rec and rec["status"] == "response_saved" else None
        if row["cid_integrity_status"] == "cid_digest_mismatch":
            raise ValueError("Image CIDv1 raw digest mismatch: " + uri)
        image_rows.append(row)

    field_image_by_snapshot = {x["snapshot_id"]: x["declared_url"] for x in fields if x["field_name"] == "image"}
    refetch_by_uri_public = {x["original_uri"]: x for x in refetch_rows}
    image_by_uri_public = {x["image_uri"]: x for x in image_rows}
    coverage_rows = []
    for event in cohort:
        uri = event["metadata_uri_declared"]
        old = old_coverage[event["launch_record_id"]]
        if event["platform_id"] == "pump.fun":
            old_snapshot = old_by_uri[uri]
            image_uri = field_image_by_snapshot[old_snapshot["snapshot_id"]]
            refetch_state = refetch_by_uri_public[uri]["status"]
            image_state = image_by_uri_public[image_uri]["status"] if image_uri else "no_image_field"
        else:
            image_uri = None
            refetch_state = "not_applicable_no_verified_source"
            image_state = "not_applicable_no_verified_source"
        coverage_rows.append({
            "launch_record_id": event["launch_record_id"],
            "object_id": event["object_id"],
            "platform_id": event["platform_id"],
            "v1_coverage_state": old["coverage_state"],
            "metadata_refetch_state": refetch_state,
            "image_acquisition_state": image_state,
            "image_uri_declared": image_uri,
        })

    # A deterministic audit queue supports later independent human annotation;
    # its creation is not itself a human review or a precision estimate.
    by_state = {}
    for row in coverage_rows:
        by_state.setdefault(row["v1_coverage_state"], []).append(row)
    review = []
    for state, take in (("declaration_observed", 10), ("no_declaration", 10), ("access_restricted_here", 3), ("not_attempted", 10)):
        for row in sorted(by_state.get(state, []), key=lambda x: x["launch_record_id"])[:take]:
            review.append({"launch_record_id": row["launch_record_id"], "object_id": row["object_id"],
                           "selection_stratum": state, "review_status": "pending_independent_human_review"})
    review_ids = {x["launch_record_id"] for x in review}
    flagged_snapshots = {x["snapshot_id"] for x in semantic_rows if x["semantic_state"] not in ("expected_web_target", "expected_social_profile", "expected_telegram_path")}
    for snapshot_id in sorted(flagged_snapshots):
        for event_id in sorted(events_by_snapshot[snapshot_id]):
            if event_id not in review_ids:
                event = event_by_id[event_id]
                review.append({"launch_record_id": event_id, "object_id": event["object_id"],
                               "selection_stratum": "field_target_needs_review", "review_status": "pending_independent_human_review"})
                review_ids.add(event_id)
    for row in checks:
        if (row["name_exact_match"] is False or row["symbol_exact_match"] is False) and row["launch_record_id"] not in review_ids:
            review.append({"launch_record_id": row["launch_record_id"], "object_id": row["object_id"],
                           "selection_stratum": "name_or_symbol_mismatch", "review_status": "pending_independent_human_review"})

    for filename in ("metadata_field_audit.parquet", "event_metadata_checks.parquet"):
        shutil.copy2(prepared / filename, output / filename)
    write(refetch_rows, output / "metadata_refetch.parquet")
    write(image_rows, output / "image_acquisition.parquet")
    write(semantic_rows, output / "url_semantic_checks.parquet")
    write(coverage_rows, output / "event_extension_coverage.parquet")
    write(review, output / "human_review_queue.parquet")
    hosts = Counter(urlparse(x["image_uri"]).hostname for x in image_rows)
    with (output / "image_source_rights.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("source_host", "declared_distinct_image_uris", "raw_binary_redistribution", "terms_status", "public_release_fields"), lineterminator="\n")
        writer.writeheader()
        for host, count in sorted(hosts.items()):
            writer.writerow({"source_host": host, "declared_distinct_image_uris": count,
                             "raw_binary_redistribution": "not_cleared", "terms_status": "source_specific_review_pending",
                             "public_release_fields": "declared URI; request receipt; HTTP status; response SHA-256; byte count; media type"})
    result = {
        "v1_creation_events": len(cohort),
        "v1_metadata_snapshots": len(old_snapshots),
        "metadata_field_audit_rows": len(fields),
        "pump_name_exact_matches": sum(x["name_exact_match"] is True for x in checks),
        "pump_symbol_exact_matches": sum(x["symbol_exact_match"] is True for x in checks),
        "coin_community_nonempty": sum(x["field_name"] == "coin_community" and x["field_state"] == "nonempty" for x in fields),
        "url_semantic_states": dict(Counter(x["semantic_state"] for x in semantic_rows)),
        "declared_distinct_image_uris": len(images),
        "metadata_refetch_statuses": dict(Counter(x["status"] for x in refetch_rows)),
        "metadata_refetch_parse_statuses": dict(Counter(str(x["second_parse_status"]) for x in refetch_rows)),
        "metadata_refetch_same_bytes": dict(Counter(str(x["same_bytes_as_v1"]) for x in refetch_rows)),
        "image_acquisition_statuses": dict(Counter(x["status"] for x in image_rows)),
        "image_response_media_type": dict(Counter(str(x["content_type_is_image"]) for x in image_rows)),
        "image_media_magic": dict(Counter(str(x["media_magic"]) for x in image_rows)),
        "image_cid_integrity": dict(Counter(str(x["cid_integrity_status"]) for x in image_rows)),
        "v1_coverage_states": dict(Counter(x["v1_coverage_state"] for x in coverage_rows)),
        "human_review_queue_rows": len(review),
        "human_review_completed": 0,
    }
    (output / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    source_files = sorted(p for p in output.iterdir() if p.is_file())
    manifest = {
        "release_id": "shilin-offchain-v2-bounded-extension",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_commit": protocol_commit,
        "claire_hf_revision": "8b29598a6565b67a8a943962dbf77f3d6b2559de",
        "v1_manifest_sha256": sha(v1_release / "release_manifest.json"),
        "raw_third_party_bodies_released": False,
        "files": {p.name: {"sha256": sha(p), "bytes": p.stat().st_size,
                           "rows": pq.read_metadata(p).num_rows if p.suffix == ".parquet" else None}
                  for p in source_files},
    }
    (output / "release_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-release", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--metadata-refetch-log", type=Path, required=True)
    parser.add_argument("--image-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.v1_release, args.prepared, args.metadata_refetch_log,
                            args.image_log, args.output, args.protocol_commit), indent=2))
