"""Publish a small rights-limited fixed pilot snapshot from a completed local run.

The external JSON bodies stay local. Public files contain factual URLs, hashes,
request metadata and typed relations, plus explicit limitations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq


TABLES = (
    "onchain_launch_cohort", "offchain_snapshots", "offchain_declarations",
    "linkage_candidates", "linkage_evidence", "linkage_assertions", "coverage_ledger",
)
HF_REVISION = "8b29598a6565b67a8a943962dbf77f3d6b2559de"
CLAIRE_ARCHIVE_SHA256 = "c5040f4a2351e7555abe1ba7695398011dba55f1ddb5c352c59affee9065e503"
CLAIRE_MANIFEST_SHA256 = "ae3f0068ab9d5ec4eaae34d21eb3f83889c0c958d2215abfc19b8e3125062273"


def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze(run: Path, code: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run / "cohort/onchain_launch_cohort.parquet", output / "onchain_launch_cohort.parquet")
    for name in TABLES[1:]:
        shutil.copy2(run / "processed" / (name + ".parquet"), output / (name + ".parquet"))
    for src, dst in (("cohort/cohort_report.json", "cohort_report.json"),
                     ("processed/processing_report.json", "processing_report.json"),
                     ("validation/validation.json", "validation.json"),
                     ("validation/validation_report.md", "validation_report.md"),
                     ("fourmeme/fourmeme_probe.json", "fourmeme_probe.json")):
        shutil.copy2(run / src, output / dst)
    for name in ("DATA_DICTIONARY.md", "rights_sources.csv", "PROPOSAL.md", "REVIEW_EXAMPLES.md"):
        shutil.copy2(code / name, output / name)

    requests = [json.loads(line) for line in (run / "offchain/offchain_requests.jsonl").read_text().splitlines() if line.strip()]
    with (output / "offchain_requests.jsonl").open("w") as f:
        for item in requests:
            item.pop("raw_local_path", None)
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    files = {}
    for path in sorted(output.iterdir()):
        if not path.is_file() or path.name == "release_manifest.json":
            continue
        files[path.name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
        if path.suffix == ".parquet":
            files[path.name]["rows"] = pq.read_metadata(path).num_rows
    code_files = {p.name: digest(p) for p in sorted(code.glob("*.py"))}
    manifest = {
        "dataset_id": "shilin-offchain-pilot-v1",
        "release_status": "bounded_research_pilot",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "claire_hf_revision": HF_REVISION,
        "claire_demo_archive_sha256": CLAIRE_ARCHIVE_SHA256,
        "claire_manifest_sha256": CLAIRE_MANIFEST_SHA256,
        "window": {"start_inclusive": "2026-09-14T12:00:00Z", "end_exclusive": "2026-09-14T12:05:00Z"},
        "raw_third_party_responses_included": False,
        "release_files": files,
        "code_sha256": code_files,
    }
    (output / "release_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"release": str(output), "files": len(files), "tables": {k:v.get("rows") for k,v in files.items() if "rows" in v}}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--code", type=Path, default=Path(__file__).parent)
    p.add_argument("--output", type=Path, default=Path(__file__).parent / "release")
    a = p.parse_args()
    freeze(a.run, a.code, a.output)
