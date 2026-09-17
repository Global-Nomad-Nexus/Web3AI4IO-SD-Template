"""Verify the public v2 extension without local third-party response bodies."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq


def verify(release: Path, v1_release: Path):
    manifest = json.loads((release / "release_manifest.json").read_text())
    checks = {}
    checks["v1_manifest_pin"] = hashlib.sha256((v1_release / "release_manifest.json").read_bytes()).hexdigest() == manifest["v1_manifest_sha256"]
    for name, spec in manifest["files"].items():
        path = release / name
        checks["file:" + name] = path.exists() and path.stat().st_size == spec["bytes"] and hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"]
        if path.suffix == ".parquet":
            checks["rows:" + name] = pq.read_metadata(path).num_rows == spec["rows"]
    if not all(checks.values()):
        return {"passed": False, "checks": checks}

    cohort = pq.read_table(v1_release / "onchain_launch_cohort.parquet").to_pylist()
    snapshots = pq.read_table(v1_release / "offchain_snapshots.parquet").to_pylist()
    fields = pq.read_table(release / "metadata_field_audit.parquet").to_pylist()
    event_checks = pq.read_table(release / "event_metadata_checks.parquet").to_pylist()
    refetch = pq.read_table(release / "metadata_refetch.parquet").to_pylist()
    images = pq.read_table(release / "image_acquisition.parquet").to_pylist()
    semantic = pq.read_table(release / "url_semantic_checks.parquet").to_pylist()
    coverage = pq.read_table(release / "event_extension_coverage.parquet").to_pylist()
    queue = pq.read_table(release / "human_review_queue.parquet").to_pylist()
    snapshot_ids = {x["snapshot_id"] for x in snapshots}
    cohort_ids = {x["launch_record_id"] for x in cohort}
    snapshot_by_uri = {x["original_uri"]: x for x in snapshots}
    image_uris = {x["image_uri"] for x in images}

    checks.update({
        "frozen_denominators": len(cohort) == 116 and len(snapshots) == 57 and len(fields) == 798 and len(event_checks) == 61 and len(refetch) == 57 and len(images) == 56 and len(semantic) == 39 and len(coverage) == 116,
        "field_matrix": len({(x["snapshot_id"], x["field_name"]) for x in fields}) == 798 and all(x["snapshot_id"] in snapshot_ids for x in fields),
        "event_keys": {x["launch_record_id"] for x in coverage} == cohort_ids and len({x["launch_record_id"] for x in coverage}) == 116,
        "pump_comparison_keys": len({x["launch_record_id"] for x in event_checks}) == 61 and all(x["launch_record_id"] in cohort_ids for x in event_checks),
        "image_queue_keys": len(image_uris) == 56 and all(set(x["source_snapshot_ids"]) <= snapshot_ids for x in images),
        "semantic_declaration_keys": {x["declaration_id"] for x in semantic} == {x["declaration_id"] for x in pq.read_table(v1_release / "offchain_declarations.parquet").to_pylist()},
        "refetch_keys": {x["original_uri"] for x in refetch} == set(snapshot_by_uri),
        "refetch_old_digest": all(x["v1_raw_sha256"] == snapshot_by_uri[x["original_uri"]]["raw_sha256"] for x in refetch),
        "human_queue_pending": all(x["review_status"] == "pending_independent_human_review" and x["launch_record_id"] in cohort_ids for x in queue),
        "no_raw_bodies_released": manifest["raw_third_party_bodies_released"] is False and all("raw_local_path" not in x for x in refetch + images),
        "utc_refetch_times": all(x["retrieved_at_utc"] is None or x["retrieved_at_utc"].endswith("Z") for x in refetch),
        "utc_image_times": all(x["retrieved_at_utc"] is None or x["retrieved_at_utc"].endswith("Z") for x in images),
    })
    for row in coverage:
        if row["platform_id"] == "pump.fun":
            checks.setdefault("pump_image_declared", True)
            checks["pump_image_declared"] &= row["image_uri_declared"] in image_uris
        else:
            checks.setdefault("four_source_not_overstated", True)
            checks["four_source_not_overstated"] &= row["metadata_refetch_state"] == "not_applicable_no_verified_source" and row["image_acquisition_state"] == "not_applicable_no_verified_source"

    return {"passed": all(checks.values()), "checks": checks,
            "metadata_refetch_statuses": dict(Counter(x["status"] for x in refetch)),
            "image_statuses": dict(Counter(x["status"] for x in images)),
            "human_review_completed": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--v1-release", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.release, args.v1_release)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)
