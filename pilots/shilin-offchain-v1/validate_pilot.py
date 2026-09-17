"""Recompute pilot integrity, provenance and time checks from local inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import base58
import pyarrow.parquet as pq


def check(name, passed, detail, severity="required"):
    return {"check": name, "status": "pass" if passed else "fail", "detail": detail, "severity": severity}


def validate(cohort_path: Path, request_log: Path, processed: Path, output: Path,
             claire_root: Path | None = None, claire_code: Path | None = None):
    cohort = pq.read_table(cohort_path).to_pylist()
    requests = [json.loads(x) for x in request_log.read_text().splitlines() if x.strip()]
    tables = {name: pq.read_table(processed / (name + ".parquet")).to_pylist()
              for name in ("offchain_snapshots", "offchain_declarations", "linkage_candidates",
                           "linkage_evidence", "linkage_assertions", "coverage_ledger")}
    checks = []
    ids = [x["launch_record_id"] for x in cohort]
    checks.append(check("unique_launch_ids", len(ids) == len(set(ids)), f"{len(ids)} events"))
    platform = Counter(x["platform_id"] for x in cohort)
    checks.append(check("frozen_window_creation_counts", platform == {"pump.fun": 61, "four.meme": 55}, str(dict(platform))))
    unique_tokens = len({(x["chain_id"], x["object_id"]) for x in cohort})
    checks.append(check("unique_token_denominator", unique_tokens == len(cohort), f"{unique_tokens} unique tokens"))
    checks.append(check("coverage_totality", {x["launch_record_id"] for x in tables["coverage_ledger"]} == set(ids)
                        and len(tables["coverage_ledger"]) == len(ids),
                        f"{len(tables['coverage_ledger'])} coverage rows for {len(ids)} events"))
    pump_uris = {x["metadata_uri_declared"] for x in cohort if x["platform_id"] == "pump.fun" and x["metadata_uri_declared"]}
    attempted = {x["original_uri"] for x in requests}
    checks.append(check("pump_uri_attempts", pump_uris <= attempted, f"{len(attempted & pump_uris)}/{len(pump_uris)} distinct Pump URIs attempted"))
    good_hash = True
    for x in requests:
        path = x.get("raw_local_path")
        if path:
            p = Path(path)
            good_hash &= p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == x.get("raw_sha256")
    checks.append(check("response_sha256", good_hash, f"{sum(bool(x.get('raw_local_path')) for x in requests)} saved HTTP response bodies"))
    candidate_ids = {x["candidate_id"] for x in tables["linkage_candidates"]}
    evidence_ids = {x["evidence_id"] for x in tables["linkage_evidence"]}
    snapshot_ids = {x["snapshot_id"] for x in tables["offchain_snapshots"]}
    links_ok = all(x["candidate_id"] in candidate_ids for x in tables["linkage_evidence"])
    links_ok &= all(x["candidate_id"] in candidate_ids and set(x["evidence_ids"]) <= evidence_ids
                    for x in tables["linkage_assertions"])
    links_ok &= all(x["snapshot_id"] is None or x["snapshot_id"] in snapshot_ids for x in tables["linkage_evidence"])
    links_ok &= all(x["snapshot_id"] in snapshot_ids for x in tables["offchain_declarations"])
    links_ok &= all(x["parent_candidate_id"] is None or x["parent_candidate_id"] in candidate_ids
                    for x in tables["linkage_candidates"])
    checks.append(check("linkage_foreign_keys", links_ok, "candidate, evidence and snapshot references"))
    url_syntax_ok = all(urlparse(x["raw_value"]).scheme in ("http", "https") and
                        bool(urlparse(x["raw_value"]).hostname) for x in tables["offchain_declarations"])
    checks.append(check("declared_url_syntax", url_syntax_ok,
                        f"{len(tables['offchain_declarations'])} extracted nonempty URL fields"))
    field_specific = all(x["relation_type"].startswith("declares_") and
                         x["relation_type"] != "declares_social_account" for x in tables["linkage_assertions"])
    checks.append(check("field_level_relation_semantics", field_specific,
                        "URL fields do not assert account ownership or project identity"))
    no_cid_mismatch = not any(x["cid_integrity_status"] == "cid_digest_mismatch" for x in tables["offchain_snapshots"])
    checks.append(check("cidv1_raw_integrity", no_cid_mismatch,
                        str(dict(Counter(x["cid_integrity_status"] for x in tables["offchain_snapshots"])))) )
    temporal_ok = all(x["as_of_eligibility"] == "unknown" and
                      x["first_verified_at_utc"] >= x["chain_event_time_utc"]
                      for x in tables["linkage_assertions"] if x["relation_type"] != "declares_metadata_uri")
    checks.append(check("no_retrospective_time_leakage", temporal_ok,
                        "Every fetched metadata declaration is observed no earlier than retrieval and has unknown creation-time eligibility"))
    bsc_positive = [x for x in tables["linkage_assertions"] if x["object_id"].startswith("eip155:56:")]
    checks.append(check("no_unverified_bsc_links", not bsc_positive,
                        f"{len(bsc_positive)} BSC positive linkage assertions"))

    raw_checks = []
    if claire_root and claire_code:
        sys.path.insert(0, str(claire_code))
        from claire_demo.validate import resolve_raw_ref
        from claire_demo.decode import ANCHOR_EVENT_CPI, decode_anchor
        idl = json.loads((claire_code / "sources/pump-public-docs/idl/pump.json").read_text())
        event = next(x for x in idl["events"] if x["name"] == "CreateEvent")
        pump = [x for x in cohort if x["platform_id"] == "pump.fun"]
        pump.sort(key=lambda x: x["launch_record_id"])
        for row in (pump[0], pump[len(pump)//2], pump[-1]):
            try:
                native = resolve_raw_ref(claire_root, row["creation_raw_ref"])
                payload = base58.b58decode(native["data"])
                args = decode_anchor(payload[8:], event, idl, True) if payload.startswith(ANCHOR_EVENT_CPI) else {}
                okay = args.get("uri") == row["metadata_uri_declared"] and args.get("mint") == row["address_or_mint"]
            except Exception:
                okay = False
            raw_checks.append({"launch_record_id": row["launch_record_id"], "raw_ref": row["creation_raw_ref"], "pass": okay})
        checks.append(check("sample_raw_event_redecode", all(x["pass"] for x in raw_checks),
                            f"{sum(x['pass'] for x in raw_checks)}/{len(raw_checks)} deterministic event samples"))

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cohort_events": len(cohort), "unique_tokens": unique_tokens,
        "events_by_platform": dict(platform), "pump_uris": len(pump_uris),
        "request_attempts": len(requests),
        "request_statuses": dict(Counter(x["status"] for x in requests)),
        "snapshots": len(tables["offchain_snapshots"]),
        "declarations": len(tables["offchain_declarations"]),
        "target_classes": dict(Counter(x["target_class"] for x in tables["offchain_declarations"])),
        "website_field_social_targets": sum(x["field_name"] == "website" and x["target_class"] in
                                            ("social_post", "social_profile_or_path", "telegram_path")
                                            for x in tables["offchain_declarations"]),
        "assertions": len(tables["linkage_assertions"]),
        "coverage_states": dict(Counter(x["coverage_state"] for x in tables["coverage_ledger"])),
        "checks": checks, "raw_sample_checks": raw_checks,
        "passed": all(x["status"] == "pass" for x in checks if x["severity"] == "required"),
        "limitations": ["Four.meme API returned access restrictions in a bounded local probe; unprobed BSC events remain not attempted.",
                        "Fetched metadata is a retrieval-time observation; historical website/account states are unknown.",
                        "Raw third-party response redistribution has not been cleared; release includes hashes and factual extracted links.",
                        "Independent coauthor reproduction and human double review require Claire's participation."],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Shilin off-chain pilot: technical validation", "", f"Generated: {summary['generated_at_utc']}",
             "", f"Overall machine-check status: **{'PASS' if summary['passed'] else 'FAIL'}**", "",
             f"Cohort: {len(cohort)} creation events / {unique_tokens} distinct chain-qualified tokens; Pump.fun {platform['pump.fun']}, Four.meme {platform['four.meme']}, Clanker {platform['clanker']}.",
             f"Requests: {len(requests)} attempts for {len(attempted)} distinct URIs; {len(tables['offchain_snapshots'])} successful response snapshots; {len(tables['offchain_declarations'])} extracted link declarations.",
             "", "## Checks", "", "| Check | Status | Evidence |", "|---|---|---|"]
    lines += [f"| {c['check']} | {c['status']} | {c['detail']} |" for c in checks]
    lines += ["", "## Coverage states", "", "| State | Events |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in sorted(summary["coverage_states"].items())]
    lines += ["", "## URL target classes", "", "| Class | Declarations |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in sorted(summary["target_classes"].items())]
    lines += ["", f"Website fields pointing to a social target: {summary['website_field_social_targets']}. These remain field-level declarations, not validated project websites."]
    lines += ["", "## Limits and remaining review", ""]
    lines += ["- " + x for x in summary["limitations"]]
    (output / "validation_report.md").write_text("\n".join(lines) + "\n")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cohort", type=Path, required=True)
    p.add_argument("--requests", type=Path, required=True)
    p.add_argument("--processed", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--claire-root", type=Path)
    p.add_argument("--claire-code", type=Path)
    a = p.parse_args()
    result = validate(a.cohort, a.requests, a.processed, a.output, a.claire_root, a.claire_code)
    print(json.dumps({"passed": result["passed"], "checks": result["checks"]}, indent=2))
    if not result["passed"]:
        raise SystemExit(1)
