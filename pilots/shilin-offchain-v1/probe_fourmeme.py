"""Bounded exact-address feasibility probe of the documented Four.meme API."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import requests


ENDPOINT = "https://four.meme/meme-api/v1/private/token/get/v2"
DOC = "https://github.com/four-meme-community/four-meme-ai/blob/main/skills/four-meme-integration/references/token-query-api.md"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(cohort_path: Path, output: Path):
    rows = [r for r in pq.read_table(cohort_path).to_pylist() if r["platform_id"] == "four.meme"]
    rows.sort(key=lambda x: (x["chain_event_time_unix"], x["creation_tx_id"]))
    sample = [rows[i] for i in sorted({0, len(rows) // 2, len(rows) - 1})]
    output.mkdir(parents=True, exist_ok=True)
    receipts = []
    for row in sample:
        params = {"address": row["address_or_mint"]}
        receipt = {"launch_record_id": row["launch_record_id"], "object_id": row["object_id"],
                   "request_id_declared": row["request_id_declared"],
                   "chain_event_time_utc": row["chain_event_time_utc"],
                   "endpoint": ENDPOINT, "parameters": params, "documentation": DOC,
                   "requested_at_utc": utc_now(), "status_code": None,
                   "response_sha256": None, "response_bytes": None,
                   "response_content_type": None, "identity_verified": False, "result": None}
        try:
            response = requests.get(ENDPOINT, params=params, headers={"Accept": "application/json",
                                    "User-Agent": "Web3AI4IO-SD-pilot/1.0"}, timeout=(8, 20))
            receipt["status_code"] = response.status_code
            receipt["response_sha256"] = hashlib.sha256(response.content).hexdigest()
            receipt["response_bytes"] = len(response.content)
            receipt["response_content_type"] = response.headers.get("Content-Type")
            if response.status_code == 200:
                try:
                    data = response.json()
                    body = data.get("data") if isinstance(data, dict) else None
                    if isinstance(body, dict):
                        got = body.get("address") or body.get("tokenAddress")
                        receipt["identity_verified"] = isinstance(got, str) and got.lower() == row["address_or_mint"].lower()
                    receipt["result"] = "exact_address_verified" if receipt["identity_verified"] else "identity_unverifiable"
                except ValueError:
                    receipt["result"] = "parse_error"
            elif response.status_code in (401, 403, 429):
                receipt["result"] = "access_restricted_here"
            else:
                receipt["result"] = "http_error"
        except requests.RequestException as exc:
            receipt["result"] = "request_failed"
            receipt["error"] = type(exc).__name__ + ": " + str(exc)[:200]
        receipt["retrieved_at_utc"] = utc_now()
        receipts.append(receipt)
    (output / "fourmeme_probe.json").write_text(json.dumps(receipts, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"eligible_bsc_creation_events": len(rows), "probed": len(receipts),
                      "verified": sum(r["identity_verified"] for r in receipts),
                      "statuses": [r["result"] for r in receipts]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    run(a.cohort, a.output)
