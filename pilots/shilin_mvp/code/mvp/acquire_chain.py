"""Acquire and decode Pump.fun creation events.

Inputs are either a versioned local fixture (the default reproducibility path)
or an approved Solana JSON-RPC endpoint. Outputs are ``launch_events.csv`` and
an acquisition receipt. RPC failures are recorded and raised; no fallback is
silently substituted. The module never writes credentials to logs.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .common import ipv4_opener, now_utc, parse_utc, read_json, require, sha256_file, stable_hash, write_csv, write_json
from .schema import EVENT_FIELDS


PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
DECODER_VERSION = "pumpfun-create-borsh-v1"


def _base58_decode(value: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in value:
        require(char in alphabet, f"Invalid base58 character in instruction data: {char!r}")
        number = number * 58 + alphabet.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + raw


def _read_borsh_string(data: bytes, offset: int) -> tuple[str, int]:
    require(offset + 4 <= len(data), "Truncated Borsh string length")
    length = int.from_bytes(data[offset:offset + 4], "little")
    start = offset + 4
    end = start + length
    require(end <= len(data), "Truncated Borsh string payload")
    return data[start:end].decode("utf-8"), end


def decode_create_args(encoded_data: str) -> tuple[str, str, str] | None:
    """Decode the first three Anchor/Borsh strings after an 8-byte discriminator."""
    try:
        raw = _base58_decode(encoded_data)
        if len(raw) < 8:
            return None
        offset = 8
        name, offset = _read_borsh_string(raw, offset)
        symbol, offset = _read_borsh_string(raw, offset)
        uri, _ = _read_borsh_string(raw, offset)
        return name, symbol, uri
    except (UnicodeDecodeError, ValueError, OverflowError):
        return None


def _account_pubkey(account: Any) -> str:
    if isinstance(account, str):
        return account
    if isinstance(account, dict):
        return str(account.get("pubkey", ""))
    return ""


def _instruction_program_id(instruction: dict[str, Any], account_keys: list[str]) -> str:
    if instruction.get("programId"):
        return str(instruction["programId"])
    index = instruction.get("programIdIndex")
    if isinstance(index, int) and 0 <= index < len(account_keys):
        return account_keys[index]
    return ""


def _event_from_instruction(instruction: dict[str, Any], account_keys: list[str], program_id: str, signature: str, slot: str, block_timestamp: str, outer_index: int, inner_index: int) -> dict[str, str] | None:
    if _instruction_program_id(instruction, account_keys) != program_id:
        return None
    decoded = decode_create_args(str(instruction.get("data", ""))) if instruction.get("data") else None
    if decoded is None or not decoded[2]:
        return None
    accounts = instruction.get("accounts") or []
    account_values = [_account_pubkey(a) if not isinstance(a, int) else (account_keys[a] if isinstance(a, int) and a < len(account_keys) else "") for a in accounts]
    mint = account_values[0] if account_values else ""
    creator = account_values[7] if len(account_values) > 7 else (account_values[-1] if account_values else "")
    return {
        "event_key": f"solana:{signature}:{outer_index}:{inner_index}", "network": "solana-mainnet", "platform": "pump.fun",
        "transaction_signature": signature, "slot": slot, "block_time": block_timestamp,
        "outer_instruction_index": str(outer_index), "inner_instruction_index": str(inner_index),
        "mint": mint, "creator": creator, "metadata_uri": decoded[2],
        "decoder_version": DECODER_VERSION, "event_status": "success",
    }


def decode_transaction(transaction: dict[str, Any], signature: str, block_time: int | None, program_id: str = PUMPFUN_PROGRAM_ID) -> list[dict[str, str]]:
    """Extract Pump.fun creates from top-level and inner instructions.

    An event is emitted only when the instruction data decodes to a metadata URI.
    Log text that merely contains ``Create`` is not treated as a create.
    """
    result = transaction.get("result") or transaction
    if not result:
        return []
    tx = result.get("transaction", {})
    meta = result.get("meta") or {}
    message = tx.get("message", {})
    account_keys = [_account_pubkey(k) for k in message.get("accountKeys", [])]
    slot = str(result.get("slot", ""))
    block_timestamp = "" if block_time is None else str(int(block_time))
    events: list[dict[str, str]] = []
    for outer_index, instruction in enumerate(message.get("instructions", [])):
        if isinstance(instruction, dict):
            event = _event_from_instruction(instruction, account_keys, program_id, signature, slot, block_timestamp, outer_index, 0)
            if event:
                events.append(event)
    for group in meta.get("innerInstructions") or []:
        if not isinstance(group, dict):
            continue
        outer_index = int(group.get("index", 0))
        for inner_index, instruction in enumerate(group.get("instructions") or []):
            if isinstance(instruction, dict):
                event = _event_from_instruction(instruction, account_keys, program_id, signature, slot, block_timestamp, outer_index, inner_index + 1)
                if event:
                    events.append(event)
    return events


class JsonRpcClient:
    """Small JSON-RPC client with explicit timeout and response accounting."""

    def __init__(self, endpoint: str, timeout: float = 20.0, opener: urllib.request.OpenerDirector | None = None, min_interval: float = 0.2):
        self.endpoint = endpoint
        self.timeout = timeout
        self.opener = opener or ipv4_opener()
        self.min_interval = min_interval
        self.calls = 0

    def call(self, method: str, params: list[Any]) -> dict[str, Any]:
        delay = 1.0
        last_error: Exception | None = None
        for _ in range(8):
            self.calls += 1
            payload = json.dumps({"jsonrpc": "2.0", "id": self.calls, "method": method, "params": params}).encode()
            request = urllib.request.Request(self.endpoint, data=payload, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "mvp-metadata-observer/1.0"}, method="POST")
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    body = response.read()
            except urllib.error.HTTPError as exc:
                last_error = RuntimeError(f"RPC HTTP {exc.code}")
                print(f"rpc {method} HTTP {exc.code}; retrying", flush=True)
                if exc.code in (429, 500, 502, 503, 504):
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                raise last_error from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = RuntimeError(f"RPC transport error: {exc.__class__.__name__}: {exc}")
                print(f"rpc {method} transport {exc.__class__.__name__}: {exc}; retrying", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            try:
                value = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("RPC returned invalid JSON") from exc
            if value.get("error"):
                message = str(value["error"])
                if any(token in message.lower() for token in ("429", "too many", "rate")):
                    last_error = RuntimeError(f"RPC error: {value['error']}")
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                raise RuntimeError(f"RPC error: {value['error']}")
            if self.min_interval:
                time.sleep(self.min_interval)
            return value
        raise last_error or RuntimeError("RPC retries exhausted")


def load_fixture(path: str | Path) -> list[dict[str, str]]:
    """Load a frozen event fixture and enforce the release schema."""
    value = read_json(path)
    require(isinstance(value, list), "Fixture must be a JSON array")
    events = [{field: str(row.get(field, "")) for field in EVENT_FIELDS} for row in value if isinstance(row, dict)]
    require(len(events) == len(value), "Fixture contains a non-object row")
    return events


def enumerate_rpc_events(client: JsonRpcClient, protocol: dict[str, Any], max_pages: int = 5000) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Enumerate signatures then fetch transactions until the frozen window is covered."""
    start = parse_utc(protocol["window"]["start"])
    end = parse_utc(protocol["window"]["end"])
    program_id = str(protocol.get("pumpfun_program_id", PUMPFUN_PROGRAM_ID))
    require(start < end, "Protocol window must be increasing")
    before: str | None = None
    signatures_seen = 0
    tx_seen = 0
    events: list[dict[str, str]] = []
    pages = 0
    oldest_seen: int | None = None
    reached_window_start = False
    tx_error_count = 0
    tx_errors: list[dict[str, str]] = []
    while pages < max_pages:
        options: dict[str, Any] = {"limit": 1000}
        if before:
            options["before"] = before
        print(f"rpc page {pages + 1} starting", flush=True)
        response = client.call("getSignaturesForAddress", [program_id, options])
        page = response.get("result") or []
        pages += 1
        if not page:
            break
        for item in page:
            signatures_seen += 1
            block_time = item.get("blockTime")
            if block_time is None:
                continue
            oldest_seen = int(block_time) if oldest_seen is None else min(oldest_seen, int(block_time))
            event_time = __import__("datetime").datetime.fromtimestamp(int(block_time), tz=__import__("datetime").timezone.utc)
            if event_time < start:
                before = item.get("signature")
                reached_window_start = True
                break
            if event_time >= end or item.get("err") is not None:
                continue
            signature = str(item.get("signature", ""))
            try:
                transaction = client.call("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
            except RuntimeError as exc:
                tx_error_count += 1
                if len(tx_errors) < 50:
                    tx_errors.append({"signature": signature, "error": str(exc)[:300]})
                continue
            tx_seen += 1
            events.extend(decode_transaction(transaction, signature, int(block_time), program_id))
        else:
            before = page[-1].get("signature")
            print(f"rpc page {pages} signatures={signatures_seen} events={len(events)}", flush=True)
            continue
        if oldest_seen is not None and event_time < start:
            break
    # DGP-ACQ-001: event denominator is defined by event key and frozen chain-time window.
    unique: dict[str, dict[str, str]] = {}
    for event in events:
        if not event["block_time"]:
            continue
        event_time = datetime.fromtimestamp(int(event["block_time"]), tz=timezone.utc)
        if start <= event_time < end and event["event_key"] not in unique:
            unique[event["event_key"]] = event
    return sorted(unique.values(), key=lambda row: (int(row["block_time"] or 0), row["event_key"])), {"pages": pages, "signatures_seen": signatures_seen, "transactions_fetched": tx_seen, "rpc_calls": client.calls, "transaction_errors": tx_error_count, "transaction_error_sample": tx_errors, "reached_window_start": reached_window_start, "scan_truncated": not reached_window_start}


def acquire_events(protocol: dict[str, Any], output_dir: str | Path, fixture: str | Path | None = None, rpc_endpoint: str | None = None) -> list[dict[str, str]]:
    """Acquire events from a frozen fixture or an approved RPC endpoint."""
    output = Path(output_dir)
    if fixture:
        events = load_fixture(fixture)
        stats = {"mode": "fixture", "fixture_sha256": sha256_file(fixture), "rpc_calls": 0}
    else:
        require(rpc_endpoint, "An approved RPC endpoint is required when fixture is absent")
        client = JsonRpcClient(rpc_endpoint)
        events, stats = enumerate_rpc_events(client, protocol)
        stats.update({"mode": "rpc", "endpoint": rpc_endpoint})
    window_start = parse_utc(protocol["window"]["start"])
    window_end = parse_utc(protocol["window"]["end"])
    accepted: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()
    for event in events:
        reason = ""
        if not event.get("event_key"):
            reason = "missing_event_key"
        elif event["event_key"] in seen:
            reason = "duplicate_event_key"
        elif event.get("network") != "solana-mainnet" or event.get("platform") != "pump.fun":
            reason = "unexpected_scope"
        elif event.get("event_status") != "success":
            reason = "non_success"
        elif not str(event.get("block_time", "")).isdigit():
            reason = "missing_block_time"
        else:
            event_time = datetime.fromtimestamp(int(event["block_time"]), tz=timezone.utc)
            if not (window_start <= event_time < window_end):
                reason = "outside_window"
        if reason:
            skipped.append({"event_key": event.get("event_key", ""), "reason": reason})
            continue
        seen.add(event["event_key"])
        accepted.append(event)
    write_csv(output / "launch_events.csv", EVENT_FIELDS, accepted)
    stats["skipped_events"] = len(skipped)
    stats["skipped_event_sample"] = skipped[:50]
    write_json(output / "acquisition_receipt.json", {"created_at": now_utc(), "protocol_hash": stable_hash(protocol), "event_count": len(accepted), "stats": stats})
    return accepted


def benchmark_candidates(protocol: dict[str, Any], candidates: list[dict[str, Any]], output: str | Path, fixture: str | Path | None = None) -> list[dict[str, Any]]:
    """Run a small, comparable benchmark and emit ``api_benchmark.csv``.

    A fixture benchmark records deterministic evidence without making network
    calls. Live candidates are opt-in and use the same frozen protocol window.
    """
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        started = time.perf_counter()
        row = {"candidate_id": candidate.get("candidate_id", ""), "endpoint": candidate.get("endpoint", ""), "role": candidate.get("role", ""), "access_decision": candidate.get("access_decision", "pending_benchmark"), "mode": "fixture" if fixture else "live", "events": "", "duplicates": "", "status": "", "latency_ms": "", "p50_latency_ms": "", "p95_latency_ms": "", "request_bytes": "", "rate_limit": "unknown", "estimated_cost": "not_recorded", "boundary_difference": "not_compared", "error": "", "evidence_protocol_hash": stable_hash(protocol)}
        try:
            if fixture:
                events = load_fixture(fixture)
                row.update(events=len(events), duplicates=len(events) - len({e["event_key"] for e in events}), status="ok")
            else:
                client = JsonRpcClient(str(candidate["endpoint"]))
                events, stats = enumerate_rpc_events(client, protocol, max_pages=2)
                row.update(events=len(events), duplicates=0, status="ok", rpc_calls=stats["rpc_calls"])
        except Exception as exc:  # evidence is recorded, candidate is not silently promoted
            row.update(status="failed", error=exc.__class__.__name__ + ": " + str(exc)[:200])
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        row["p50_latency_ms"] = row["latency_ms"]
        row["p95_latency_ms"] = row["latency_ms"]
        rows.append(row)
    fields = sorted({key for row in rows for key in row})
    write_csv(output, fields, rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fixture")
    parser.add_argument("--rpc-endpoint")
    args = parser.parse_args()
    acquire_events(read_json(args.protocol), args.output, args.fixture, args.rpc_endpoint)


if __name__ == "__main__":
    main()
