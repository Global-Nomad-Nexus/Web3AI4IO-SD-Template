#!/usr/bin/env python3
"""Recompute aggregate RQ feasibility statistics from the six seven-day tables.

Offline, Python standard library only. No token identifiers, URI values, field
contents or request identifiers are written to the report. Dates are compared
using actual response completion times, not checkpoint labels or timing flags.

Usage from any directory:
    python3 analysis/rq_feasibility_audit.py --check-reference
    python3 analysis/rq_feasibility_audit.py --output /tmp/rq-audit.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


TABLES = (
    "launch_events", "observation_plan", "request_attempts",
    "response_snapshots", "field_observations", "coverage_ledger",
)
CHECKPOINTS = ("T0", "T24", "T48", "T72")
FIELDS = ("name", "symbol", "description", "createdOn", "image",
          "website", "twitter", "telegram")
KNOWN_FAILURES = {"http_error", "timeout", "transport_error"}
HOST_BUCKETS = {
    "ipfs.io", "pump.mypinata.cloud", "metadata.j7tracker.io",
    "meta.uxento.io", "m.rapidlaunch.io",
}


def timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("A table timestamp lacks an explicit timezone")
    return parsed.timestamp()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_uri(value: str):
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        return parsed, hostname
    except ValueError:
        return None, ""


def is_http_url_syntax(value: str) -> bool:
    parsed, hostname = split_uri(value.strip())
    return bool(parsed and parsed.scheme in {"http", "https"} and hostname)


def audit(release: Path, project: Path) -> dict:
    tables, inputs = {}, {}
    for table in TABLES:
        path = release / f"{table}.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            tables[table] = list(csv.DictReader(stream))
        inputs[path.name] = {
            "bytes": path.stat().st_size,
            "rows": len(tables[table]),
            "sha256": file_sha256(path),
        }

    events, plans, attempts, snapshots, fields, ledger = (
        tables[name] for name in TABLES
    )
    block = {row["event_key"]: float(row["block_time"]) for row in events}
    cutoff = {key: moment + 24 * 3600 for key, moment in block.items()}
    attempts_by_id, attempts_by_event = defaultdict(list), defaultdict(list)
    for row in attempts:
        attempts_by_id[row["request_id"]].append(row)
        attempts_by_event[row["event_key"]].append(row)
    snapshots_by_id = {row["request_id"]: row for row in snapshots}
    field_by_id, field_trajectories = defaultdict(dict), defaultdict(list)
    for row in fields:
        field_by_id[row["request_id"]][row["field_name"]] = row
        field_trajectories[(row["event_key"], row["field_name"])].append(
            (row["presence"], row["value_type"], row["value_hash"])
        )

    matching_attempts = {}
    match_anomalies = 0
    json_by_event, eligible = defaultdict(list), defaultdict(list)
    for row in snapshots:
        matches = [
            attempt for attempt in attempts_by_id[row["request_id"]]
            if attempt["status"] == "success"
            and attempt["completed_at"] == row["retrieved_at"]
            and attempt["response_sha256"] == row["response_sha256"]
        ]
        if len(matches) != 1:
            match_anomalies += 1
        else:
            matching_attempts[row["request_id"]] = matches[0]
        if row["parse_state"] != "json_ok":
            continue
        json_by_event[row["event_key"]].append(row)
        if len(matches) == 1 and timestamp(matches[0]["completed_at"]) <= cutoff[row["event_key"]]:
            eligible[row["event_key"]].append(row)

    selected = {
        key: max(rows, key=lambda row: timestamp(row["retrieved_at"]))
        for key, rows in eligible.items()
    }
    group_by_event, groups, no_json_last_status = {}, Counter(), Counter()
    no_completed_attempt = in_flight_only = 0
    for event in events:
        key = event["event_key"]
        finished = [
            row for row in attempts_by_event[key]
            if row["started_at"] and row["completed_at"]
            and timestamp(row["completed_at"]) <= cutoff[key]
        ]
        started = [
            row for row in attempts_by_event[key]
            if row["started_at"] and timestamp(row["started_at"]) <= cutoff[key]
        ]
        if not finished:
            no_completed_attempt += 1
            in_flight_only += bool(started)
        if key in selected:
            group = "json_success_by_24h"
        else:
            unresolved_success = False
            for row in finished:
                if row["status"] != "success":
                    continue
                snapshot = snapshots_by_id.get(row["request_id"])
                if (not snapshot or snapshot["retrieved_at"] != row["completed_at"]
                        or snapshot["parse_state"] not in {"json_ok", "parse_error"}):
                    unresolved_success = True
            known_non_json = any(
                row["status"] in KNOWN_FAILURES
                or (row["status"] == "success"
                    and snapshots_by_id.get(row["request_id"], {}).get("parse_state") == "parse_error"
                    and snapshots_by_id[row["request_id"]]["retrieved_at"] == row["completed_at"])
                for row in finished
            )
            group = ("attempted_without_json" if known_non_json and not unresolved_success
                     else "state_unknown")
            if finished:
                last = max(finished, key=lambda row: timestamp(row["completed_at"]))
                snapshot = snapshots_by_id.get(last["request_id"])
                detail = last["status"]
                if last["status"] == "success":
                    detail = ("json_parse_error" if snapshot and snapshot["parse_state"] == "parse_error"
                              else "http_success_without_snapshot")
                no_json_last_status[detail] += 1
        group_by_event[key] = group
        groups[group] += 1

    field_stats = {}
    for name in FIELDS:
        counts = Counter({key: 0 for key in (
            "absent", "present", "null", "string", "other_type",
            "empty_or_whitespace_string", "nonempty_string", "missing_field_row",
        )})
        if name in {"image", "website", "twitter", "telegram"}:
            counts.update({"http_url_syntax": 0, "other_nonempty_string": 0})
        for snapshot in selected.values():
            row = field_by_id[snapshot["request_id"]].get(name)
            if row is None:
                counts["missing_field_row"] += 1
                continue
            counts[row["presence"]] += 1
            kind = row["value_type"]
            if kind == "null":
                counts["null"] += 1
            elif kind == "string":
                counts["string"] += 1
                value = row["allowed_value"]
                nonempty = bool(value.strip())
                counts["nonempty_string" if nonempty else "empty_or_whitespace_string"] += 1
                if nonempty and name in {"image", "website", "twitter", "telegram"}:
                    counts["http_url_syntax" if is_http_url_syntax(value)
                           else "other_nonempty_string"] += 1
            elif kind != "absent":
                counts["other_type"] += 1
        field_stats[name] = dict(counts)

    comparable = [rows for rows in json_by_event.values() if len(rows) >= 2]
    per_field_comparable = Counter({name: 0 for name in FIELDS})
    per_field_changed = Counter({name: 0 for name in FIELDS})
    changed_field_events = set()
    for (event, name), values in field_trajectories.items():
        if len(values) >= 2:
            per_field_comparable[name] += 1
            if len(set(values)) > 1:
                per_field_changed[name] += 1
                changed_field_events.add(event)
    ledger_by_event = defaultdict(dict)
    for row in ledger:
        ledger_by_event[row["event_key"]][row["checkpoint"]] = row["final_state"]
    trajectories = Counter(
        "|".join(states.get(checkpoint, "missing_row") for checkpoint in CHECKPOINTS)
        for states in ledger_by_event.values()
    )

    uri_counts = Counter(row["metadata_uri"] for row in events)
    shared_events = sum(count for count in uri_counts.values() if count > 1)
    uri_forms, hosts = Counter(), defaultdict(Counter)
    for row in events:
        parsed, hostname = split_uri(row["metadata_uri"])
        ipfs_form = bool(parsed and (
            parsed.scheme == "ipfs" or parsed.path.startswith("/ipfs/")
            or ".ipfs." in hostname
        ))
        uri_forms["ipfs_string_form" if ipfs_form else "other_string_form"] += 1
        bucket = hostname if hostname in HOST_BUCKETS else ("other_hosts" if hostname else "no_host")
        hosts[bucket]["events"] += 1
        hosts[bucket][group_by_event[row["event_key"]]] += 1

    refused = [row for row in attempts if row["status"] in {"route_refused_policy", "not_collected_policy"}]
    selected_prior_failure = selected_prior_refusal = 0
    for key, snapshot in selected.items():
        previous = [row for row in attempts_by_event[key]
                    if row["checkpoint"] == snapshot["checkpoint"]]
        selected_prior_failure += any(
            row["status"] in KNOWN_FAILURES and row["completed_at"]
            and timestamp(row["completed_at"]) < timestamp(snapshot["retrieved_at"])
            for row in previous
        )
        selected_prior_refusal += any(row["status"] == "route_refused_policy" for row in previous)

    expected_keys = {(event, checkpoint) for event in block for checkpoint in CHECKPOINTS}
    checks = {
        "unique_event_keys": len(events) == len(block),
        "plan_keys_match_event_times_four_checkpoints":
            {(row["event_key"], row["checkpoint"]) for row in plans} == expected_keys
            and len(plans) == len(expected_keys),
        "ledger_keys_match_event_times_four_checkpoints":
            {(row["event_key"], row["checkpoint"]) for row in ledger} == expected_keys
            and len(ledger) == len(expected_keys),
        "unique_snapshot_request_ids": len(snapshots) == len(snapshots_by_id),
        "snapshot_success_match_anomalies": match_anomalies,
        "selected_snapshots_without_eight_field_rows":
            sum(len(field_by_id[row["request_id"]]) != 8 for row in selected.values()),
        "all_records_reference_enrolled_events":
            all(row["event_key"] in block for name in TABLES[1:] for row in tables[name]),
        "input_hashes_unchanged_after_read": all(
            file_sha256(release / filename) == item["sha256"] for filename, item in inputs.items()
        ),
    }
    raw_bodies = sum(path.is_file() for path in project.rglob("response_bodies.jsonl"))
    return {
        "audit_version": "1.0",
        "scope": "Six seven-day release tables; offline aggregate analysis only",
        "input_files": inputs,
        "definitions": {
            "cutoff": "block_time + 86400 seconds; actual completed_at <= cutoff",
            "json_success": "json_ok snapshot matched to one success attempt by request_id, completion time and response SHA-256",
            "attempted_without_json": "completed actual network attempts without qualifying JSON, with known request/parse failure and no unresolved HTTP success",
            "state_unknown": "no completed network evidence or unresolved HTTP success without qualifying snapshot",
            "field_selection": "last qualifying JSON by cutoff; field states are conditional on having that JSON",
            "nonempty_string": "value_type=string and allowed_value.strip() is nonempty",
            "http_url_syntax": "nonempty string parsed as HTTP(S) with a hostname; no network or ownership validation",
            "field_change": "different (presence, value_type, value_hash) across successfully recorded checkpoints",
            "uri_form": "scheme=ipfs OR path starts /ipfs/ OR hostname contains .ipfs.; string classification, not CID validation",
        },
        "cohort_events": len(events),
        "at_24h": {
            "groups": {name: groups[name] for name in (
                "json_success_by_24h", "attempted_without_json", "state_unknown")},
            "no_json_evidence": len(events) - len(selected),
            "no_completed_network_attempt": no_completed_attempt,
            "started_but_no_completed_attempt": in_flight_only,
            "non_json_by_last_completed_status": dict(no_json_last_status),
            "qualifying_snapshots_by_checkpoint": dict(Counter(row["checkpoint"] for row in selected.values())),
            "qualifying_snapshot_count_per_event": dict(Counter(str(len(rows)) for rows in eligible.values())),
            "fields_denominator": len(selected),
            "fields": field_stats,
            "json_success_first_observed_after_24h": sum(key not in selected for key in json_by_event),
        },
        "longitudinal": {
            "ever_json_success_events": len(json_by_event),
            "at_least_two_successful_json_events": len(comparable),
            "response_sha256_changed_events": sum(len({row["response_sha256"] for row in rows}) > 1 for rows in comparable),
            "per_field_comparable_events": dict(per_field_comparable),
            "per_field_changed_events": dict(per_field_changed),
            "any_extracted_field_changed_events": len(changed_field_events),
            "checkpoint_order": list(CHECKPOINTS),
            "final_state_trajectories": dict(trajectories),
        },
        "observation_states": {
            "attempt_status_counts": dict(Counter(row["status"] for row in attempts)),
            "snapshot_parse_counts": dict(Counter(row["parse_state"] for row in snapshots)),
            "ledger_final_state_counts": dict(Counter(row["final_state"] for row in ledger)),
            "ledger_timing_counts": dict(Counter(row["timing_state"] for row in ledger)),
            "by_checkpoint": {checkpoint: dict(Counter(row["final_state"] for row in ledger if row["checkpoint"] == checkpoint))
                              for checkpoint in CHECKPOINTS},
        },
        "request_routes": {
            "route_counts": dict(Counter(row["route_id"] for row in attempts)),
            "policy_refusal_rows": len(refused),
            "policy_refusal_without_started_or_completed_at": sum(not row["started_at"] and not row["completed_at"] for row in refused),
            "policy_refusal_hosts": dict(Counter(row["host"] if row["host"] in HOST_BUCKETS else "other_hosts" for row in refused)),
            "selected_json_routes_by_24h": dict(Counter(row["route_id"] for row in selected.values())),
            "selected_json_with_prior_same_checkpoint_network_failure": selected_prior_failure,
            "selected_json_with_same_checkpoint_policy_refusal": selected_prior_refusal,
        },
        "resources": {
            "distinct_uri_original_strings": len(uri_counts),
            "empty_uri_events": uri_counts[""],
            "shared_uri_groups": sum(count > 1 for count in uri_counts.values()),
            "events_in_shared_uri_groups": shared_events,
            "fraction_events_in_shared_uri_groups": shared_events / len(events) if events else None,
            "uri_string_forms": dict(uri_forms),
            "declared_host_buckets": {host: dict(counts) for host, counts in hosts.items()},
        },
        "package_evidence": {
            "raw_response_body_files_present": raw_bodies,
            "raw_response_body_in_package": bool(raw_bodies),
            "note": "File-presence check only; no claim about current retention on the collection cluster",
        },
        "checks": checks,
    }


def check_reference(report: dict) -> None:
    observed = {
        "groups": report["at_24h"]["groups"],
        "nonempty_fields": {name: report["at_24h"]["fields"][name]["nonempty_string"]
                            for name in ("description", "website", "twitter", "telegram")},
        "later_json": report["at_24h"]["json_success_first_observed_after_24h"],
        "comparable_events": report["longitudinal"]["at_least_two_successful_json_events"],
        "digest_changed": report["longitudinal"]["response_sha256_changed_events"],
        "fields_changed": report["longitudinal"]["any_extracted_field_changed_events"],
        "uri_forms": report["resources"]["uri_string_forms"],
    }
    expected = {
        "groups": {"json_success_by_24h": 4197, "attempted_without_json": 470, "state_unknown": 1},
        "nonempty_fields": {"description": 2140, "website": 1681, "twitter": 2460, "telegram": 84},
        "later_json": 13, "comparable_events": 4185, "digest_changed": 21, "fields_changed": 0,
        "uri_forms": {"ipfs_string_form": 3415, "other_string_form": 1253},
    }
    if observed != expected:
        raise RuntimeError("Reference aggregate verification failed; inspect recomputed aggregates")


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path,
                        default=project / "data" / "7day-72h-20261008-release")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_suffix(".json"))
    parser.add_argument("--check-reference", action="store_true",
                        help="Verify the aggregate results of the supplied 2026-10-08 release")
    args = parser.parse_args()
    release, output = args.release_dir.resolve(), args.output.resolve()
    if output in {(release / f"{table}.csv").resolve() for table in TABLES}:
        raise ValueError("Output must not overwrite an input table")
    report = audit(release, project)
    if args.check_reference:
        check_reference(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "events": report["cohort_events"],
                      "groups_at_24h": report["at_24h"]["groups"],
                      "reference_checked": args.check_reference}, ensure_ascii=False))


if __name__ == "__main__":
    main()
