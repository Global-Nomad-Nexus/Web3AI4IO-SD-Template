"""Derive a typed request ledger without editing acquisition evidence.

Block identity is method-aware: transaction signatures and commitment objects
are never converted into block heights. A request-only block reference is
distinguished from an observed response. The parser makes no network requests.
"""
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import re

import pyarrow as pa
import pyarrow.parquet as pq

from .common import load_json, sha256, write_json

VERSION = "claire-provenance/1.0.0"
S, I, B = pa.string(), pa.int64(), pa.bool_()
SCHEMA = pa.schema([(name, S) for name in (
    "source_id", "endpoint", "rpc_method", "request_params", "requested_at",
    "retrieved_at", "chain_id", "response_status", "raw_response_status",
    "error_code", "raw_path", "raw_sha256", "ledger_raw_sha256",
    "raw_integrity", "block_hash", "block_context_source",
    "block_context_status", "parser_issues", "provenance_parser_version",
)] + [(name, I) for name in (
    "block_number_or_slot", "response_context_slot", "retry_count",
    "http_status", "ledger_line",
)] + [("request_params_redacted", B)])
SECRET_KEYS = {"apikey", "authorization", "password", "secret", "accesstoken", "authtoken", "clientsecret", "xapikey"}
MULTIBLOCK_METHODS = {"getBlocks", "getBlocksWithLimit", "getConfirmedBlocks", "getConfirmedBlocksWithLimit"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def redact_endpoint(value):
    """Keep public origin only; provider path/query/userinfo can contain keys."""
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        host = parsed.hostname
        if ":" in host:
            host = "[" + host + "]"
        port = ":" + str(parsed.port) if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}"
    except ValueError:
        return None


def redact_params(value):
    changed = False
    def clean(item):
        nonlocal changed
        if isinstance(item, dict):
            result = {}
            for key, val in item.items():
                normalized = re.sub(r"[^a-z]", "", str(key).lower())
                if normalized in SECRET_KEYS:
                    result[key] = "[REDACTED]"
                    changed = True
                else:
                    result[key] = clean(val)
            return result
        if isinstance(item, list):
            return [clean(v) for v in item]
        if isinstance(item, str) and re.match(r"^https?://", item):
            redacted = redact_endpoint(item)
            changed |= redacted != item
            return redacted
        return item
    result = clean(value)
    return result, changed


def height(value):
    """Only explicit nonnegative integers/hex quantities that fit Arrow int64."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]+", value):
        number = int(value, 16)
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        number = int(value)
    else:
        return None
    return number if 0 <= number <= 2**63 - 1 else None


def blockhash(value):
    return value if isinstance(value, str) and value else None


def unwrap(raw):
    """HTTP failure wrappers remain errors even if body resembles valid JSON."""
    if not isinstance(raw, dict):
        return None, "missing_or_malformed", None, None
    http = height(raw.get("http_status"))
    envelope = raw
    if "http_status" in raw and "body" in raw:
        try:
            envelope = json.loads(raw["body"]) if isinstance(raw["body"], str) else raw["body"]
        except (ValueError, TypeError):
            envelope = None
        if isinstance(envelope, dict) and isinstance(envelope.get("error"), dict):
            return envelope, "http_rpc_error", http, envelope["error"].get("code")
        return envelope, "http_error" if http is not None and http >= 400 else "http_wrapper", http, None
    if isinstance(envelope.get("error"), dict):
        return envelope, "rpc_error", http, envelope["error"].get("code")
    if "result" in envelope:
        return envelope, "null_result" if envelope["result"] is None else "ok", http, None
    return envelope, "malformed_response", http, None


def explicit_request_context(method, params):
    """A requested reference is not evidence that a node returned that block."""
    params = params if isinstance(params, list) else []
    positions = {
        "eth_getBlockByNumber": 0, "eth_getBlockReceipts": 0,
        "debug_traceBlockByNumber": 0, "getBlock": 0, "getBlockTime": 0,
        "getConfirmedBlock": 0, "eth_getCode": 1, "eth_getBalance": 1,
        "eth_getTransactionCount": 1, "eth_call": 1, "eth_getStorageAt": 2,
    }
    if method in positions and len(params) > positions[method]:
        val = params[positions[method]]
        if isinstance(val, dict):
            return height(val.get("blockNumber")), blockhash(val.get("blockHash"))
        if method == "eth_getBlockReceipts" and isinstance(val, str) and re.fullmatch(r"0x[0-9a-fA-F]{64}", val):
            return None, val
        return height(val), None
    if method in ("eth_getBlockByHash", "debug_traceBlockByHash") and params:
        # Hash is retained only in the hash field, never parsed as an integer.
        return None, blockhash(params[0])
    return None, None


def _uniform_receipt_context(result):
    if not isinstance(result, list) or not result:
        return None, None, "empty_or_absent_array"
    if not all(isinstance(x, dict) for x in result):
        return None, None, "malformed_array"
    numbers = [height(x.get("blockNumber")) for x in result]
    hashes = [blockhash(x.get("blockHash")) for x in result]
    if len(set(numbers)) > 1 or len(set(hashes)) > 1:
        return None, None, "multiple_or_inconsistent_blocks"
    return numbers[0], hashes[0], "uniform_receipt_array"


def infer_context(method, params, raw):
    envelope, status, _, _ = unwrap(raw)
    response_ok = status == "ok"
    result = envelope.get("result") if isinstance(envelope, dict) else None
    # A range/listing RPC is never labelled as one block, even if one item is
    # returned. Its context slot (if present) is recorded separately below.
    if method in MULTIBLOCK_METHODS:
        return None, None, "multi_block_listing", "unknown"
    number = digest = None
    source = "not_block_scoped"
    if response_ok and method in ("eth_getBlockByNumber", "eth_getBlockByHash") and isinstance(result, dict):
        number, digest, source = height(result.get("number")), blockhash(result.get("hash")), "evm_block_response"
    elif response_ok and method in ("eth_getTransactionReceipt", "eth_getTransactionByHash") and isinstance(result, dict):
        number, digest, source = height(result.get("blockNumber")), blockhash(result.get("blockHash")), "evm_transaction_block_context"
    elif response_ok and method in ("eth_getBlockReceipts", "eth_getLogs"):
        number, digest, source = _uniform_receipt_context(result)
        if source in ("multiple_or_inconsistent_blocks", "malformed_array"):
            return None, None, source, "unknown" if method == "eth_getLogs" and source == "multiple_or_inconsistent_blocks" else "conflict"
    elif response_ok and method in ("getBlock", "getConfirmedBlock") and isinstance(result, dict):
        # Solana blockHeight is not its slot. getBlock's explicit request gives
        # the slot, while its result provides the block hash.
        number, _, = explicit_request_context(method, params)
        digest, source = blockhash(result.get("blockhash")), "solana_block_request_slot_and_response_hash"
    elif response_ok and method in ("getTransaction", "getConfirmedTransaction") and isinstance(result, dict):
        number, digest, source = height(result.get("slot")), None, "solana_transaction_slot"
        # message.recentBlockhash is intentionally not used as the containing
        # block's hash: it is a transaction lifetime / freshness reference.
    elif response_ok and method in ("getSlot", "getFirstAvailableBlock", "minimumLedgerSlot", "eth_blockNumber"):
        number, source = height(result), "scalar_result"
    requested_number, requested_hash = explicit_request_context(method, params)
    if number is not None or digest is not None:
        if requested_number is not None and number is not None and requested_number != number:
            return None, None, "request_response_height_conflict", "conflict"
        if requested_hash is not None and digest is not None and requested_hash.lower() != digest.lower():
            return None, None, "request_response_hash_conflict", "conflict"
        return number, digest, source, "resolved"
    if requested_number is not None or requested_hash is not None:
        return requested_number, requested_hash, "explicit_request_reference", "requested_only"
    return None, None, source, "unknown"


def parse_record(item, raw, ledger_line, raw_integrity="not_checked", actual_raw_hash=None):
    params, redacted = redact_params(item.get("request_params"))
    envelope, raw_status, http, remote_code = unwrap(raw)
    number, digest, source, context_status = infer_context(item.get("rpc_method"), item.get("request_params"), raw)
    context_slot = None
    if isinstance(envelope, dict) and isinstance(envelope.get("result"), dict):
        context = envelope["result"].get("context")
        if isinstance(context, dict):
            context_slot = height(context.get("slot"))
    code = item.get("error_code") if item.get("error_code") is not None else remote_code
    code = str(code) if isinstance(code, (int, str)) and not isinstance(code, bool) else None
    return dict(source_id=item.get("source_id"), endpoint=redact_endpoint(item.get("endpoint")), rpc_method=item.get("rpc_method"), request_params=canonical(params), requested_at=item.get("requested_at"), retrieved_at=item.get("retrieved_at"), chain_id=item.get("chain_id"), response_status=item.get("response_status"), raw_response_status=raw_status, error_code=code, retry_count=height(item.get("retry_count")), http_status=height(item.get("http_status")) or http, raw_path=item.get("raw_path"), raw_sha256=actual_raw_hash or item.get("raw_sha256"), ledger_raw_sha256=item.get("raw_sha256"), raw_integrity=raw_integrity, block_number_or_slot=number, block_hash=digest, block_context_source=source, block_context_status=context_status, response_context_slot=context_slot, ledger_line=ledger_line, parser_issues="[]", request_params_redacted=redacted, provenance_parser_version=VERSION)


def _prefix_digest(path, size):
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        remaining = size
        while remaining:
            chunk = fh.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk); remaining -= len(chunk)
    return digest.hexdigest(), remaining


def run(root):
    root = Path(root).resolve()
    ledger = root / "provenance/request_log.jsonl"
    if not ledger.exists():
        raise FileNotFoundError("Acquisition request ledger is required")
    snapshot_size = ledger.stat().st_size
    output = root / "provenance/requests.parquet"
    temporary = output.with_suffix(".parquet.tmp")
    counts, contexts, integrity_counts = Counter(), Counter(), Counter()
    issues, rows, buffer, tail_bytes = [], 0, [], 0
    captured_hash = hashlib.sha256()
    raw_cache = {}
    with pq.ParquetWriter(temporary, SCHEMA, compression="zstd") as writer, ledger.open("rb") as fh:
        remaining = snapshot_size
        line_no = 0
        while remaining:
            line = fh.readline(remaining)
            if not line:
                break
            captured_hash.update(line); remaining -= len(line)
            if not line.endswith(b"\n"):
                tail_bytes = len(line)
                break
            line_no += 1
            raw, actual_hash, integrity = None, None, "no_raw_response"
            local_issues = []
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("ledger row is not an object")
            except (ValueError, UnicodeDecodeError):
                item = {"response_status": "malformed_ledger_line"}
                local_issues.append("malformed_ledger_line")
            rel = item.get("raw_path")
            if rel:
                try:
                    raw_path = (root / rel).resolve()
                    raw_path.relative_to(root / "raw")
                    if not raw_path.is_file():
                        integrity = "missing"
                        local_issues.append("raw_response_missing")
                    else:
                        cache_key = (str(raw_path), raw_path.stat().st_size, raw_path.stat().st_mtime_ns)
                        actual_hash = raw_cache.get(cache_key)
                        if actual_hash is None:
                            actual_hash = sha256(raw_path)
                            raw_cache[cache_key] = actual_hash
                        expected = item.get("raw_sha256")
                        integrity = "matched" if expected == actual_hash else "unrecorded" if expected is None else "mismatch"
                        if integrity == "mismatch":
                            local_issues.append("raw_sha256_mismatch")
                        else:
                            raw = load_json(raw_path)
                except (OSError, ValueError, TypeError, UnicodeDecodeError):
                    integrity = "unreadable_or_invalid_path"
                    local_issues.append("raw_response_unreadable_or_invalid_path")
            row = parse_record(item, raw, line_no, integrity, actual_hash)
            if row["block_context_status"] == "conflict":
                local_issues.append("block_context_conflict")
            row["parser_issues"] = canonical(local_issues)
            issues.extend({"ledger_line": line_no, "code": code} for code in local_issues)
            if integrity == "unreadable_or_invalid_path":
                row["raw_path"] = None
            buffer.append(row)
            rows += 1
            counts[row["response_status"] or "unknown"] += 1
            contexts[row["block_context_status"]] += 1
            integrity_counts[integrity] += 1
            if len(buffer) >= 1000:
                writer.write_table(pa.Table.from_pylist(buffer, schema=SCHEMA)); buffer.clear()
        if buffer:
            writer.write_table(pa.Table.from_pylist(buffer, schema=SCHEMA))
    current_hash, missing_bytes = _prefix_digest(ledger, snapshot_size)
    prefix_unchanged = missing_bytes == 0 and current_hash == captured_hash.hexdigest()
    if not prefix_unchanged:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Acquisition ledger prefix changed during provenance parsing")
    temporary.replace(output)
    report = dict(status="completed", passed=not issues and tail_bytes == 0, provenance_parser_version=VERSION, rows=rows, output_path=str(output.relative_to(root)), output_sha256=sha256(output), ledger_path=str(ledger.relative_to(root)), ledger_snapshot_bytes=snapshot_size, covered_ledger_bytes=snapshot_size-tail_bytes, ledger_snapshot_sha256=captured_hash.hexdigest(), ledger_prefix_unchanged=True, ledger_bytes_at_finish=ledger.stat().st_size, appended_bytes_during_run=max(0, ledger.stat().st_size - snapshot_size), unparsed_trailing_bytes=tail_bytes, response_status_counts=dict(counts), block_context_counts=dict(contexts), raw_integrity_counts=dict(integrity_counts), parser_issues=issues, limitations=["This table covers the ledger prefix present when parsing began; later acquisition rows require a rerun.", "Requested-only block references are not proof that a provider returned that block.", "A Solana transaction recentBlockhash is not used as its containing block hash.", "Multi-block listings have null single-block identity. Original acquisition records remain unchanged."])
    write_json(root / "reports/provenance_summary.json", report)
    return report
