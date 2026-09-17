"""Fetch the exact metadata URIs declared in Claire's Pump.fun creation records.

Raw third-party responses are local working files. A rights decision is required
before copying them into a public release. Every attempted URI gets a receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pyarrow.parquet as pq
import requests


MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = "Web3AI4IO-SD-pilot/1.0 (research metadata fetch; GitHub Global-Nomad-Nexus/Web3AI4IO-SD-Template)"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def resolve_uri(uri: str, gateway: str | None = None):
    if uri.startswith("ipfs://"):
        tail = uri[7:].lstrip("/")
        if tail.startswith("ipfs/"):
            tail = tail[5:]
        return (gateway or "https://ipfs.io").rstrip("/") + "/ipfs/" + tail
    if gateway and uri.startswith("https://ipfs.io/ipfs/"):
        return gateway.rstrip("/") + "/ipfs/" + uri.split("/ipfs/", 1)[1]
    if uri.startswith("ar://"):
        return "https://arweave.net/" + uri[5:].lstrip("/")
    return uri


def public_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("unsupported_or_credentialed_url")
    host = parsed.hostname
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        ips = []
        for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
            ips.append(ipaddress.ip_address(item[4][0]))
    if not ips or any(not ip.is_global for ip in ips):
        raise ValueError("non_public_address")
    return url


def fetch(session: requests.Session, uri: str, gateway: str | None = None):
    url = resolve_uri(uri, gateway)
    redirects = []
    for _ in range(6):
        public_url(url)
        with session.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain;q=0.9, */*;q=0.2"},
                         timeout=(8, 20), allow_redirects=False, stream=True) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("redirect_without_location")
                redirects.append({"url": url, "status": response.status_code, "location": location})
                url = urljoin(url, location)
                continue
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    raise ValueError("response_over_2MiB")
            return {
                "status_code": response.status_code,
                "resolved_url": url,
                "redirects": redirects,
                "content_type": response.headers.get("Content-Type"),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "cache_control": response.headers.get("Cache-Control"),
                "body": bytes(content),
            }
    raise ValueError("more_than_five_redirects")


def collect(cohort: Path, output: Path, limit: int | None = None,
            gateway: str | None = None, retry_failed: bool = False, delay: float = 1.0):
    rows = pq.read_table(cohort).to_pylist()
    pump = [r for r in rows if r["platform_id"] == "pump.fun"]
    uris = sorted({r["metadata_uri_declared"] for r in pump if r["metadata_uri_declared"]})
    if limit is not None:
        uris = uris[:limit]
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    session = requests.Session()
    log_path = output / "offchain_requests.jsonl"
    prior = {}
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            item = json.loads(line)
            prior[item["original_uri"]] = item
    count = 0
    consecutive_429 = 0
    with log_path.open("a") as log:
        for uri in uris:
            if uri in prior and (prior[uri]["status"] == "response_saved" or not retry_failed):
                continue
            start = now()
            rec = {"request_id": "req:" + sha((uri + "|" + start).encode())[:24],
                   "original_uri": uri, "resolved_url": resolve_uri(uri, gateway),
                   "gateway_override": gateway,
                   "requested_at_utc": start, "retrieved_at_utc": None,
                   "status": None, "status_code": None, "error": None,
                   "redirects": [], "content_type": None, "byte_count": None,
                   "raw_sha256": None, "raw_local_path": None,
                   "collector_version": "shilin-metadata-collector/1.0.0"}
            try:
                response = fetch(session, uri, gateway)
                rec.update({k: response[k] for k in ("status_code", "resolved_url", "redirects", "content_type", "etag", "last_modified", "cache_control")})
                body = response["body"]
                rec["byte_count"] = len(body)
                rec["raw_sha256"] = sha(body)
                path = raw / (rec["raw_sha256"] + ".body")
                path.write_bytes(body)
                rec["raw_local_path"] = str(path)
                rec["status"] = "response_saved" if response["status_code"] == 200 else "http_error"
            except (requests.RequestException, OSError, ValueError) as exc:
                rec["status"] = "request_failed"
                rec["error"] = type(exc).__name__ + ": " + str(exc)[:300]
            rec["retrieved_at_utc"] = now()
            log.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log.flush()
            count += 1
            print(json.dumps({k: rec[k] for k in ("original_uri", "status", "status_code", "error")}, ensure_ascii=False), flush=True)
            consecutive_429 = consecutive_429 + 1 if rec["status_code"] == 429 else 0
            if consecutive_429 >= 2:
                print("Stopping after two consecutive HTTP 429 responses", flush=True)
                break
            time.sleep(delay)
    return {"eligible_pump_events": len(pump), "distinct_nonempty_uris": len(uris), "new_requests": count,
            "request_log": str(log_path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--gateway", help="Documented alternate public IPFS gateway base URL")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(collect(args.cohort, args.output, args.limit, args.gateway, args.retry_failed, args.delay), indent=2))
