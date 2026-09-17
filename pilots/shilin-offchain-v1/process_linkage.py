"""Turn locally retrieved metadata into typed, evidence-backed pilot tables."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pyarrow as pa
import pyarrow.parquet as pq


LINK_FIELDS = {
    "website": "declares_website_field_url",
    "external_url": "declares_external_url_field",
    "twitter": "declares_twitter_field_url",
    "x": "declares_x_field_url",
    "telegram": "declares_telegram_field_url",
    "discord": "declares_discord_field_url",
    "github": "declares_github_field_url",
}


def sid(*parts):
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:24]


def write_parquet(rows, path: Path):
    if rows:
        pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")
    else:
        path.with_suffix(".json").write_text("[]\n")


def cid_integrity(uri: str, body: bytes):
    """Verify single-block CIDv1 raw/sha2-256; do not misread CIDv0 DAG-PB."""
    path = urlparse(uri).path
    if "/ipfs/" not in path:
        return "not_applicable"
    cid = path.split("/ipfs/", 1)[1].split("/", 1)[0]
    if cid.startswith("Qm"):
        return "not_checked_cidv0_dagpb"
    if not cid.startswith("b"):
        return "unsupported_cid"
    try:
        value = cid[1:].upper()
        decoded = base64.b32decode(value + "=" * ((-len(value)) % 8))
    except (ValueError, base64.binascii.Error):
        return "invalid_cid"
    if len(decoded) == 36 and decoded[:4] == bytes((1, 0x55, 0x12, 0x20)):
        return "verified_cidv1_raw_sha256" if decoded[4:] == hashlib.sha256(body).digest() else "cid_digest_mismatch"
    return "unsupported_cid_codec_or_hash"


def target_class(value: str):
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    segments = [x for x in parsed.path.split("/") if x]
    if host in ("x.com", "twitter.com") and "status" in segments:
        return "social_post"
    if host in ("x.com", "twitter.com"):
        return "social_profile_or_path"
    if host == "t.me":
        return "telegram_path"
    if host in ("pump.fun", "www.pump.fun"):
        return "platform_page"
    return "other_web_url"


def process(cohort_path: Path, request_log: Path, output: Path, four_probe_path: Path | None = None):
    cohort = pq.read_table(cohort_path).to_pylist()
    requests = [json.loads(x) for x in request_log.read_text().splitlines() if x.strip()]
    request_by_uri = {}
    for rec in requests:
        uri = rec["original_uri"]
        if uri not in request_by_uri or rec["status"] == "response_saved":
            request_by_uri[uri] = rec
    output.mkdir(parents=True, exist_ok=True)
    four_probes = {}
    if four_probe_path:
        four_probes = {r["launch_record_id"]: r for r in json.loads(four_probe_path.read_text())}
    snapshots, declarations, candidates, evidence, assertions, coverage = [], [], [], [], [], []
    snapshot_by_uri = {}
    parse_by_uri = {}
    declarations_by_uri = {}
    for rec in request_by_uri.values():
        if rec["status"] != "response_saved":
            continue
        body_path = Path(rec["raw_local_path"])
        body = body_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != rec["raw_sha256"]:
            raise ValueError("Raw response hash mismatch: " + str(body_path))
        parsed, parse_status = None, "parse_error"
        try:
            parsed = json.loads(body.decode("utf-8-sig"))
            if isinstance(parsed, dict):
                parse_status = "json_object"
            else:
                parse_status = "json_non_object"
        except (UnicodeError, json.JSONDecodeError):
            pass
        cid_status = cid_integrity(rec["original_uri"], body)
        if cid_status == "cid_digest_mismatch":
            parse_status = "cid_mismatch"
        snapshot_id = "snap:" + sid(rec["request_id"], rec["raw_sha256"])
        snapshot_by_uri[rec["original_uri"]] = snapshot_id
        parse_by_uri[rec["original_uri"]] = parse_status
        snapshots.append({
            "snapshot_id": snapshot_id, "request_id": rec["request_id"],
            "original_uri": rec["original_uri"], "resolved_url": rec["resolved_url"],
            "retrieved_at_utc": rec["retrieved_at_utc"], "raw_sha256": rec["raw_sha256"],
            "byte_count": rec["byte_count"], "content_type": rec["content_type"],
            "parse_status": parse_status, "cid_integrity_status": cid_status,
            "raw_redistribution_status": "not_cleared",
        })
        found = []
        if parse_status == "json_object":
            for field, relation in LINK_FIELDS.items():
                value = parsed.get(field)
                if isinstance(value, str) and value.strip():
                    declaration_id = "dec:" + sid(snapshot_id, field, value)
                    item = {"declaration_id": declaration_id, "snapshot_id": snapshot_id,
                            "field_name": field, "json_pointer": "/" + field,
                            "raw_value": value, "normalized_value": value.strip(),
                            "relation_type": relation, "target_class": target_class(value),
                            "first_verified_at_utc": rec["retrieved_at_utc"]}
                    declarations.append(item)
                    found.append(item)
        declarations_by_uri[rec["original_uri"]] = found

    for event in cohort:
        uri = event["metadata_uri_declared"]
        request = request_by_uri.get(uri) if uri else None
        snapshot_id = snapshot_by_uri.get(uri) if uri else None
        if event["platform_id"] == "four.meme":
            probe = four_probes.get(event["launch_record_id"])
            state = probe["result"] if probe else "not_attempted"
        else:
            state = "no_uri" if not uri else "not_attempted" if not request else "request_failed" if request["status"] != "response_saved" else "parse_error" if parse_by_uri.get(uri) != "json_object" else "no_declaration" if not declarations_by_uri.get(uri) else "declaration_observed"
        coverage.append({
            "launch_record_id": event["launch_record_id"], "chain_id": event["chain_id"],
            "platform_id": event["platform_id"], "object_id": event["object_id"],
            "metadata_uri_declared": uri, "request_id": request["request_id"] if request else None,
            "snapshot_id": snapshot_id, "coverage_state": state,
        })
        if not uri:
            continue
        # The creation record itself directly declares the URI. This is a typed
        # relation, not evidence that a website existed or was accessible then.
        candidate_id = "cand:" + sid(event["launch_record_id"], uri)
        candidates.append({"candidate_id": candidate_id, "launch_record_id": event["launch_record_id"],
                           "object_id": event["object_id"], "offchain_value": uri,
                           "source_uri": uri, "parent_candidate_id": None,
                           "candidate_rule": "onchain_create_uri_exact/1.0", "status": "accepted_direct_declaration"})
        evidence_id = "ev:" + sid(candidate_id, event["creation_raw_ref"])
        evidence.append({"evidence_id": evidence_id, "candidate_id": candidate_id,
                         "evidence_kind": "onchain_creation_uri", "polarity": "supports",
                         "raw_ref": event["creation_raw_ref"], "snapshot_id": None,
                         "field_pointer": "/uri", "observed_at_utc": event["chain_event_time_utc"]})
        assertions.append({"assertion_id": "assert:" + sid(candidate_id, "declares_metadata_uri"),
                           "candidate_id": candidate_id, "object_id": event["object_id"],
                           "relation_type": "declares_metadata_uri", "right_value": uri,
                           "evidence_ids": [evidence_id], "status": "confirmed_direct_declaration",
                           "chain_event_time_utc": event["chain_event_time_utc"],
                           "first_verified_at_utc": event["chain_event_time_utc"],
                           "as_of_eligibility": "creation_record_only"})
        for declaration in declarations_by_uri.get(uri, []):
            cid = "cand:" + sid(event["launch_record_id"], declaration["declaration_id"])
            eid = "ev:" + sid(cid, declaration["declaration_id"])
            candidates.append({"candidate_id": cid, "launch_record_id": event["launch_record_id"],
                               "object_id": event["object_id"], "offchain_value": declaration["raw_value"],
                               "source_uri": uri, "parent_candidate_id": candidate_id,
                               "candidate_rule": "metadata_uri_follow_and_field_extract/1.0",
                               "status": "accepted_snapshot_declaration"})
            evidence.append({"evidence_id": eid, "candidate_id": cid,
                             "evidence_kind": "metadata_json_field", "polarity": "supports",
                             "raw_ref": None, "snapshot_id": declaration["snapshot_id"],
                             "field_pointer": declaration["json_pointer"],
                             "observed_at_utc": declaration["first_verified_at_utc"]})
            assertions.append({"assertion_id": "assert:" + sid(cid, declaration["relation_type"]),
                               "candidate_id": cid, "object_id": event["object_id"],
                               "relation_type": declaration["relation_type"],
                               "target_class": declaration["target_class"],
                               "right_value": declaration["raw_value"],
                               "evidence_ids": [evidence_id, eid], "status": "confirmed_snapshot_declaration",
                               "chain_event_time_utc": event["chain_event_time_utc"],
                               "first_verified_at_utc": declaration["first_verified_at_utc"],
                               "as_of_eligibility": "unknown"})

    for name, rows in (("offchain_snapshots", snapshots), ("offchain_declarations", declarations),
                       ("linkage_candidates", candidates), ("linkage_evidence", evidence),
                       ("linkage_assertions", assertions), ("coverage_ledger", coverage)):
        write_parquet(rows, output / (name + ".parquet"))
    report = {"cohort_events": len(cohort), "events_by_platform": dict(Counter(x["platform_id"] for x in cohort)),
              "requests": len(requests), "distinct_requested_uris": len(request_by_uri), "snapshots": len(snapshots),
              "declarations": len(declarations), "candidates": len(candidates),
              "assertions": len(assertions), "coverage_states": dict(Counter(x["coverage_state"] for x in coverage)),
              "generated_at_utc": datetime.now(timezone.utc).isoformat()}
    (output / "processing_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cohort", type=Path, required=True)
    p.add_argument("--requests", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--four-probe", type=Path)
    a = p.parse_args()
    print(json.dumps(process(a.cohort, a.requests, a.output, a.four_probe), indent=2))
