#!/usr/bin/env python3
"""Run the Pump.fun MVP data flow.

Fixture mode replays local files. RPC mode enrolls a rolling 24-hour cohort
from the moment the process starts, then waits through 36 hours of follow-up
observation. Network
calls use IPv4. Failures are saved and retried; the process does not stop for
a manual review.
"""

from __future__ import annotations

import argparse
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from mvp.acquire_chain import acquire_events, benchmark_candidates
from mvp.build_release import build_release
from mvp.common import read_csv, read_json, sha256_file, stable_hash, write_csv, write_json
from mvp.gateway_preflight import confirm_metadata_gateways
from mvp.live_cohort import run_live_cohort
from mvp.observe_metadata import FixtureTransport, build_observation_plan, observe_events
from mvp.schema import PLAN_FIELDS


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path("/work/so192/scientific data/data")


def unfinished_output(path: Path) -> Path | None:
    """Return the newest unfinished cohort under ``path``, if one exists."""
    if not path.exists():
        return None
    candidates = []
    if (path / "run" / "cohort_status.json").exists():
        candidates.append(path)
    for child in path.iterdir():
        if child.is_dir() and (child / "run" / "cohort_status.json").exists():
            candidates.append(child)
    unfinished = []
    for item in candidates:
        try:
            status = read_json(item / "run" / "cohort_status.json")
        except (OSError, ValueError):
            continue
        if status.get("phase") != "finished":
            unfinished.append(item)
    if not unfinished:
        return None
    return max(unfinished, key=lambda item: (item / "run" / "cohort_status.json").stat().st_mtime)


def resolve_output(path: Path, resume: bool) -> Path:
    """Resume an unfinished cohort, or start a new timestamped run."""
    if resume:
        found = unfinished_output(path)
        if found is not None:
            print(f"resuming unfinished cohort: {found}", flush=True)
            return found
    if path.exists() and any(path.iterdir()):
        stamp = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
        return path / stamp
    return path


def confirm_gateways_with_retry(protocol: dict, output: Path) -> list[dict]:
    """Try the metadata gateways more than once, then continue either way."""
    settings = protocol.get("metadata_gateways") or {}
    attempts = max(1, int(settings.get("preflight_attempts", 5)))
    delay = float(settings.get("preflight_sleep_seconds", 15))
    passed: list[dict] = []
    for attempt in range(1, attempts + 1):
        try:
            passed = confirm_metadata_gateways(protocol, output)
        except Exception as exc:
            print(f"gateway preflight attempt {attempt} failed: {exc.__class__.__name__}: {exc}", flush=True)
            passed = []
        if passed:
            print(f"gateway preflight passed: {', '.join(str(row.get('host', '')) for row in passed)}", flush=True)
            return passed
        if attempt < attempts:
            print(f"gateway preflight empty; retrying in {delay:.0f}s", flush=True)
            time.sleep(delay)
    print("gateway preflight did not pass; collection continues with declared URIs and registered routes", flush=True)
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixture", "rpc"), default="fixture")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--rpc-endpoint")
    parser.add_argument("--protocol", default=str(ROOT / "configs" / "mvp_protocol.json"))
    parser.add_argument("--source-register", default=str(ROOT / "configs" / "source_register.csv"))
    parser.add_argument("--fixture", default=str(ROOT / "fixtures" / "sample_events.json"))
    args = parser.parse_args()
    protocol = read_json(args.protocol)
    source_register = read_csv(args.source_register)
    output = resolve_output(Path(args.output), resume=args.mode == "rpc")
    run_dir = output / "run"
    release_dir = output / "mvp_release"
    run_dir.mkdir(parents=True, exist_ok=True)
    release_dir.mkdir(parents=True, exist_ok=True)

    benchmark_path = output / "api_benchmark.csv"
    candidates = [row for row in protocol["api_candidates"] if row.get("access_decision") == "allowed"] or list(protocol["api_candidates"])
    if args.mode == "fixture":
        benchmark_candidates(protocol, candidates, benchmark_path, args.fixture)
        benchmark_rows = read_csv(benchmark_path)
        winner = next((row for row in benchmark_rows if row.get("status") == "ok"), None)
        selection_status = "fixture_only"
    else:
        if not args.rpc_endpoint and candidates:
            args.rpc_endpoint = str(candidates[0].get("endpoint", ""))
        primary = candidates[0] if candidates else {}
        winner = {"candidate_id": primary.get("candidate_id", ""), "status": "direct_collection"}
        write_csv(benchmark_path, ["candidate_id", "endpoint", "status", "access_decision", "address_family"], [{"candidate_id": primary.get("candidate_id", ""), "endpoint": args.rpc_endpoint or "", "status": "direct_collection", "access_decision": "allowed", "address_family": "ipv4"}])
        selection_status = "direct_collection"
    selection = {"status": selection_status, "selected_candidate": winner.get("candidate_id") if winner else None, "selected_endpoint": args.rpc_endpoint or (winner.get("endpoint") if winner else None), "evidence_file": "api_benchmark.csv", "evidence_row": 2 if winner else None, "address_family": "ipv4", "limitations": "RPC mode enrolls for 24 hours from the process start, then observes for 36 hours, and retries failed network calls. The endpoint is not silently replaced."}
    write_json(output / "API_SELECTION.json", selection)
    (output / "API_SELECTION.md").write_text(
        "# API selection\n\n"
        f"- Status: **{selection['status']}**\n"
        f"- Candidate: `{selection['selected_candidate'] or 'none'}`\n"
        f"- Endpoint: `{selection.get('selected_endpoint') or 'none'}`\n"
        "- Address family: IPv4\n"
        "- RPC mode enrolls for 24 hours from the process start. T0 is that start, then the same process collects T+24h and observes again at T+60h, 36 hours after collection ends. Failed calls are saved and retried.\n",
        encoding="utf-8",
    )

    if args.mode == "fixture":
        events = acquire_events(protocol, run_dir, args.fixture, args.rpc_endpoint)
        plan = build_observation_plan(events, protocol)
        write_csv(run_dir / "observation_plan.csv", PLAN_FIELDS, plan)
        uri_files = {uri: ROOT / relative for uri, relative in protocol["fixture"]["uri_files"].items()}
        observe_events(events, plan, source_register, protocol, run_dir, transport=FixtureTransport(uri_files))
        shutil.copyfile(args.protocol, output / "mvp_protocol.json")
    else:
        passed = confirm_gateways_with_retry(protocol, output)
        protocol.setdefault("metadata_gateways", {})["confirmed"] = passed
        events, protocol = run_live_cohort(protocol, source_register, run_dir, args.rpc_endpoint)
        write_json(output / "mvp_protocol.json", protocol)
    manifest = build_release(run_dir, release_dir, protocol, source_register)

    shutil.copyfile(args.source_register, output / "source_register.csv")
    write_json(output / "input_manifest.json", {"protocol_sha256": stable_hash(protocol), "source_register_sha256": sha256_file(args.source_register), "mode": args.mode, "fixture_sha256": sha256_file(args.fixture) if args.mode == "fixture" else None, "release_manifest": str((release_dir / "release_manifest.json").relative_to(output))})
    write_csv(output / "DGP_DATA_LINEAGE.csv", ["lineage_id", "input", "output", "rule", "code_location", "validation", "responsible", "version"], [
        {"lineage_id": "DGP-ACQ-001", "input": "RPC/fixture transaction", "output": "launch_events.event_key", "rule": "Successful Pump.fun create. Live mode enrolls from collection start for 24 hours; fixture mode uses the protocol window.", "code_location": "mvp/live_cohort.py:run_live_cohort", "validation": "validate_release", "responsible": "Owen", "version": protocol["protocol_version"]},
        {"lineage_id": "DGP-OBS-001", "input": "collection_started_at or block_time", "output": "observation_plan.scheduled_at", "rule": "Live T0 is collection start; T+24h ends the 24-hour collection and T+60h is 36 hours later. Fixture mode uses block_time.", "code_location": "mvp/live_cohort.py:run_live_cohort", "validation": "plan denominator check", "responsible": "Owen", "version": protocol["protocol_version"]},
        {"lineage_id": "DGP-OBS-002", "input": "metadata_uri", "output": "request_attempts.request_url", "rule": "Public http(s) URI is requested on IPv4. ipfs:// and ar:// keep the original URI and record the gateway route. Local and private hosts are not collected. Failures are retried.", "code_location": "mvp/observe_metadata.py:observe_events", "validation": "coverage ledger terminal state", "responsible": "Owen", "version": protocol["protocol_version"]},
        {"lineage_id": "DGP-REL-001", "input": "JSON response", "output": "field_observations", "rule": "fixed JSON pointers and presence/type", "code_location": "mvp/build_release.py:parse_field_observations", "validation": "field allow-list and response hash", "responsible": "Owen", "version": protocol["protocol_version"]},
    ])
    write_json(output / "run_status.json", {"phase": "finished", "mode": args.mode, "events": len(events), "release_files": len(manifest["files"]), "address_family": "ipv4"})
    print(f"Run complete: {output}")
    print(f"Events: {len(events)}; release files: {len(manifest['files'])}")


if __name__ == "__main__":
    main()
