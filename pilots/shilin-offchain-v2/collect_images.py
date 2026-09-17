"""Fetch every image URI declared by the fixed v1 metadata snapshots once."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shilin-offchain-v1"))
from collect_metadata import fetch  # noqa: E402


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def collect(queue_path: Path, output: Path, delay: float = 1.0):
    queue = json.loads(queue_path.read_text())
    uris = [x["image_uri"] for x in queue]
    if uris != sorted(set(uris)):
        raise ValueError("Image queue must be sorted and distinct")
    output.mkdir(parents=True, exist_ok=True)
    raw_dir = output / "raw"
    raw_dir.mkdir(exist_ok=True)
    log_path = output / "image_requests.jsonl"
    if log_path.exists():
        raise FileExistsError("Prespecified one-pass image run already exists: " + str(log_path))
    session = requests.Session()
    consecutive_429 = 0
    with log_path.open("w") as log:
        for item in queue:
            uri = item["image_uri"]
            started = now()
            rec = {
                "request_id": "imgreq:" + hashlib.sha256((uri + "|" + started).encode()).hexdigest()[:24],
                "image_uri": uri,
                "source_snapshot_ids": item["source_snapshot_ids"],
                "requested_at_utc": started,
                "retrieved_at_utc": None,
                "status": None,
                "status_code": None,
                "error": None,
                "resolved_url": None,
                "redirects": [],
                "content_type": None,
                "byte_count": None,
                "raw_sha256": None,
                "raw_local_path": None,
                "collector_version": "shilin-image-collector/1.0.0",
            }
            try:
                response = fetch(session, uri, "https://gateway.pinata.cloud")
                for key in ("status_code", "resolved_url", "redirects", "content_type", "etag", "last_modified", "cache_control"):
                    rec[key] = response[key]
                body = response["body"]
                rec["byte_count"] = len(body)
                rec["raw_sha256"] = hashlib.sha256(body).hexdigest()
                path = raw_dir / (rec["raw_sha256"] + ".body")
                path.write_bytes(body)
                rec["raw_local_path"] = str(path)
                rec["status"] = "response_saved" if response["status_code"] == 200 else "http_error"
            except (requests.RequestException, OSError, ValueError) as exc:
                rec["status"] = "request_failed"
                rec["error"] = type(exc).__name__ + ": " + str(exc)[:300]
            rec["retrieved_at_utc"] = now()
            log.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log.flush()
            print(json.dumps({k: rec[k] for k in ("image_uri", "status", "status_code", "error")}, ensure_ascii=False), flush=True)
            consecutive_429 = consecutive_429 + 1 if rec["status_code"] == 429 else 0
            if consecutive_429 >= 2:
                print("Stopped after two consecutive HTTP 429 responses", flush=True)
                break
            time.sleep(delay)
    return {"declared_distinct_images": len(uris), "attempted_images": sum(1 for _ in log_path.open())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(collect(args.queue, args.output, args.delay), indent=2))
