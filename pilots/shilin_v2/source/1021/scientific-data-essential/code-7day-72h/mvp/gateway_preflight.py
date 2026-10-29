"""Confirm that at least one metadata gateway returns JSON before a live run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .common import now_utc, read_json, write_json
from .observe_metadata import FetchResult, HttpTransport


def extract_ipfs_cid(uri: str) -> str:
    """Return the CID from an ipfs:// URI or an /ipfs/<cid> path."""
    if not uri:
        return ""
    if uri.startswith("ipfs://"):
        rest = uri[len("ipfs://"):]
        if rest.startswith("ipfs/"):
            rest = rest[len("ipfs/"):]
        return rest.split("/", 1)[0].split("?", 1)[0]
    marker = "/ipfs/"
    if marker not in uri:
        return ""
    return uri.split(marker, 1)[1].split("/", 1)[0].split("?", 1)[0]


def gateway_url(template: str, cid: str) -> str:
    return template.replace("{cid}", cid)


def confirm_metadata_gateways(protocol: dict[str, Any], output_dir: str | Path, transport: Callable[[str], FetchResult] | None = None) -> list[dict[str, Any]]:
    """Request the sample CID from each candidate and keep the ones that return a JSON object.

    The report is written even when every candidate fails. An empty result does
    not stop the cohort; the caller retries, then continues with declared URIs.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    settings = protocol.get("metadata_gateways") or {}
    cid = str(settings.get("sample_cid") or "")
    candidates = list(settings.get("candidates") or [])
    transport = transport or HttpTransport(timeout=20, max_bytes=int(protocol["observation"]["max_response_bytes"]))
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        template = str(candidate.get("template") or "")
        url = gateway_url(template, cid) if cid and "{cid}" in template else ""
        row: dict[str, Any] = {"host": candidate.get("host", ""), "template": template, "url": url, "status": "not_attempted", "http_status": "", "json_keys": [], "error": ""}
        if not url:
            row["status"] = "invalid_template"
            results.append(row)
            continue
        fetched = transport(url)
        row["http_status"] = fetched.http_status
        if fetched.status != "success" or fetched.http_status not in ("", "200") or not fetched.body:
            row["status"] = fetched.status or "failed"
            row["error"] = fetched.error_class or fetched.error_message
            results.append(row)
            continue
        try:
            document = json.loads(fetched.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            row["status"] = "not_json"
            row["error"] = exc.__class__.__name__
            results.append(row)
            continue
        if not isinstance(document, dict):
            row["status"] = "not_json_object"
            results.append(row)
            continue
        row["status"] = "json_ok"
        row["json_keys"] = sorted(document)[:12]
        results.append(row)
    passed = [row for row in results if row["status"] == "json_ok"]
    write_json(output / "gateway_preflight.json", {"created_at": now_utc(), "sample_cid": cid, "address_family": "ipv4", "results": results, "passed_hosts": [row["host"] for row in passed]})
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default=str(Path(__file__).resolve().parents[1] / "configs" / "mvp_protocol.json"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    protocol = read_json(args.protocol)
    settings = protocol.get("metadata_gateways") or {}
    attempts = max(1, int(settings.get("preflight_attempts", 5)))
    delay = float(settings.get("preflight_sleep_seconds", 15))
    passed: list[dict] = []
    for attempt in range(1, attempts + 1):
        try:
            passed = confirm_metadata_gateways(protocol, args.output)
        except Exception as exc:
            print(f"attempt {attempt} failed: {exc.__class__.__name__}: {exc}")
            passed = []
        if passed or attempt == attempts:
            break
        print(f"no gateway returned JSON; retrying in {delay:.0f}s")
        __import__("time").sleep(delay)
    print(f"passed {', '.join(row['host'] for row in passed) or 'none'}")


if __name__ == "__main__":
    main()
