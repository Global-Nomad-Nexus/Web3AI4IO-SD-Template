"""Offline verification of the public fixed pilot snapshot (no raw bytes needed)."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(root: Path):
    manifest = json.loads((root / "release_manifest.json").read_text())
    problems = []
    for name, expected in manifest["release_files"].items():
        path = root / name
        if not path.is_file() or path.stat().st_size != expected["bytes"] or sha(path) != expected["sha256"]:
            problems.append("file_mismatch:" + name)
        if path.suffix == ".parquet" and path.is_file() and pq.read_metadata(path).num_rows != expected["rows"]:
            problems.append("row_count_mismatch:" + name)
    cohort = pq.read_table(root / "onchain_launch_cohort.parquet").to_pylist()
    coverage = pq.read_table(root / "coverage_ledger.parquet").to_pylist()
    assertions = pq.read_table(root / "linkage_assertions.parquet").to_pylist()
    evidence = pq.read_table(root / "linkage_evidence.parquet").to_pylist()
    candidates = pq.read_table(root / "linkage_candidates.parquet").to_pylist()
    snapshots = pq.read_table(root / "offchain_snapshots.parquet").to_pylist()
    declarations = pq.read_table(root / "offchain_declarations.parquet").to_pylist()
    ids = {x["launch_record_id"] for x in cohort}
    if len(ids) != len(cohort) or {x["launch_record_id"] for x in coverage} != ids or len(coverage) != len(cohort):
        problems.append("cohort_coverage_integrity")
    cids = {x["candidate_id"] for x in candidates}
    eids = {x["evidence_id"] for x in evidence}
    sids = {x["snapshot_id"] for x in snapshots}
    if any(x["candidate_id"] not in cids or not set(x["evidence_ids"]) <= eids for x in assertions):
        problems.append("assertion_evidence_integrity")
    if any(x["snapshot_id"] not in sids for x in declarations):
        problems.append("declaration_snapshot_integrity")
    if any(x["as_of_eligibility"] != "unknown" for x in assertions if x["relation_type"] != "declares_metadata_uri"):
        problems.append("as_of_time_leakage")
    return {"passed": not problems, "problems": problems, "cohort_events": len(cohort),
            "platform_events": dict(Counter(x["platform_id"] for x in cohort)),
            "coverage_states": dict(Counter(x["coverage_state"] for x in coverage)),
            "snapshots": len(snapshots), "declarations": len(declarations),
            "assertions": len(assertions)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--release", type=Path, required=True)
    a = p.parse_args()
    result = verify(a.release)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)
