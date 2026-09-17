"""Export small human-readable review tables from the hash-verified release."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pyarrow.parquet as pq

from verify_release import verify


ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "release"
OUTPUT = ROOT / "review"


def write_csv(name, rows, fields):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / name).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(name, len(rows))


def main():
    result = verify(RELEASE)
    if not result["passed"]:
        raise RuntimeError(result["problems"])
    cohort = pq.read_table(RELEASE / "onchain_launch_cohort.parquet").to_pylist()
    coverage = pq.read_table(RELEASE / "coverage_ledger.parquet").to_pylist()
    write_csv("coverage_ledger.csv", coverage,
              ("launch_record_id", "chain_id", "platform_id", "object_id", "metadata_uri_declared", "request_id", "snapshot_id", "coverage_state"))
    unresolved = [row for row in coverage if row["coverage_state"] != "declaration_observed"]
    assert len(unresolved) == 87
    write_csv("unmatched_cases.csv", unresolved,
              ("launch_record_id", "chain_id", "platform_id", "object_id", "metadata_uri_declared", "request_id", "snapshot_id", "coverage_state"))
    bsc = [{"launch_record_id": row["launch_record_id"], "object_id": row["object_id"],
            "address_or_mint": row["address_or_mint"], "request_id_declared": row["request_id_declared"],
            "creation_tx_id": row["creation_tx_id"], "chain_event_time_utc": row["chain_event_time_utc"],
            "coverage_state": next(x["coverage_state"] for x in coverage if x["launch_record_id"] == row["launch_record_id"])}
           for row in cohort if row["platform_id"] == "four.meme"]
    assert len(bsc) == 55
    write_csv("fourmeme_exact_queue.csv", bsc,
              ("launch_record_id", "object_id", "address_or_mint", "request_id_declared", "creation_tx_id", "chain_event_time_utc", "coverage_state"))
    funnel = json.loads((RELEASE / "cohort_report.json").read_text())["funnel"]
    write_csv("count_waterfall.csv", [{"stage": k, "rows": v} for k, v in funnel.items()], ("stage", "rows"))


if __name__ == "__main__":
    main()
