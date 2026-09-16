"""Solana getBlock/getTransaction consistency over a deterministic sample.

This network stage must run after collection and before final provenance and
offline processing. It uses the currently selected source, not an independent
node, and preserves every request through acquire.RPC.
"""
from pathlib import Path
import hashlib
import json
import random

from .acquire import client, RPCError
from .common import START, END, load_json, sha256, timestamp, utcnow, write_json

SEED = 20260914
SAMPLE_SIZE = 20
MISSING = object()


def status(transaction):
    meta = transaction.get("meta")
    return "unknown" if not isinstance(meta, dict) or "err" not in meta else "success" if meta["err"] is None else "failed"


def differences(expected, observed, path="", limit=20):
    """Exact JSON value/field-presence comparison, with bounded diagnostics."""
    output = []
    def add(pointer, left, right):
        def summary(value):
            if value is MISSING:
                return {"present": False}
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return {"present": True, "value": value} if len(encoded) <= 400 else {
                "present": True, "json_characters": len(encoded), "sha256": hashlib.sha256(encoded.encode()).hexdigest()}
        if len(output) < limit:
            output.append({"pointer": pointer or "/", "expected": summary(left), "observed": summary(right)})
    def visit(left, right, pointer):
        if len(output) >= limit:
            return
        if left is MISSING or right is MISSING:
            if left is not right:
                add(pointer, left, right)
        elif type(left) is not type(right):
            add(pointer, left, right)
        elif isinstance(left, dict):
            for key in sorted(set(left) | set(right)):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                visit(left.get(key, MISSING), right.get(key, MISSING), pointer + "/" + escaped)
        elif isinstance(left, list):
            if len(left) != len(right):
                add(pointer + "/length", len(left), len(right))
            for index, (a, b) in enumerate(zip(left, right)):
                visit(a, b, pointer + "/" + str(index))
        elif left != right:
            add(pointer, left, right)
    visit(expected, observed, path)
    return output


def select(root, scope):
    rng = random.Random(SEED)
    reservoir, representatives, errors, hashes = [], {}, [], {}
    seen = 0
    for slot in sorted(scope["main_blocks"]):
        relative = f"raw/solana/blocks/{slot}.json.gz"
        try:
            block = load_json(root / relative)["result"]
            txs = block["transactions"]
            if not isinstance(block, dict) or not isinstance(txs, list):
                raise ValueError("missing full block transaction array")
            block_time = block.get("blockTime")
            if type(block_time) is not int or not timestamp(START) <= block_time < timestamp(END):
                raise ValueError("raw block has unknown or out-of-window UTC membership")
            hashes[relative] = sha256(root / relative)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"slot": slot, "error": type(exc).__name__, "reason": "required main-window raw block unavailable"})
            continue
        for index, native in enumerate(txs):
            try:
                signature = native["transaction"]["signatures"][0]
                if not isinstance(signature, str) or not signature:
                    raise ValueError("missing transaction signature")
            except (KeyError, IndexError, TypeError, ValueError):
                errors.append({"slot": slot, "tx_index": index, "reason": "raw transaction signature unavailable"})
                continue
            candidate = {"slot": slot, "tx_index": index, "signature": signature,
                         "block_time": block.get("blockTime", MISSING), "version": native.get("version", MISSING),
                         "execution_status": status(native), "native": native,
                         "raw_ref": relative + f"#/result/transactions/{index}"}
            seen += 1
            if len(reservoir) < SAMPLE_SIZE:
                reservoir.append(candidate)
            else:
                replacement = rng.randrange(seen)
                if replacement < SAMPLE_SIZE:
                    reservoir[replacement] = candidate
            version_key = json.dumps(native.get("version"), sort_keys=True) if "version" in native else "<missing>"
            representatives.setdefault((version_key, candidate["execution_status"]), candidate)
    chosen = {}
    for reason, candidates in (("seeded_reservoir", reservoir), ("version_status_representative", representatives.values())):
        for item in candidates:
            key = (item["slot"], item["tx_index"])
            if key not in chosen:
                chosen[key] = dict(item, selection_reasons=[])
            chosen[key]["selection_reasons"].append(reason)
    return [chosen[k] for k in sorted(chosen)], seen, hashes, errors


def request_evidence(root, offset, signature, source_id):
    ledger = root / "provenance/request_log.jsonl"
    evidence = []
    if not ledger.exists():
        return evidence
    with ledger.open("rb") as fh:
        fh.seek(offset)
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("source_id") == source_id and row.get("rpc_method") == "getTransaction" and (row.get("request_params") or [None])[0] == signature:
                evidence.append({key: row.get(key) for key in ("source_id", "requested_at", "retrieved_at", "rpc_method", "request_params", "response_status", "raw_path", "raw_sha256", "error_code")})
    return evidence


def run(root):
    root = Path(root)
    report = {"started_at": utcnow(), "passed": False, "seed": SEED, "reservoir_size": SAMPLE_SIZE,
              "scope": "Solana main-window transactions: 20 seeded reservoir samples plus each observed version/status representative",
              "comparison": "same selected source, cross-method consistency; not independent-node verification",
              "checks": [], "errors": []}
    def finish():
        report["completed_at"] = utcnow()
        write_json(root / "reports/transaction_probe.json", report)
        return report
    try:
        collection = load_json(root / "reports/collection.json")
        window = load_json(root / "reports/window.json")
        scope = window["chains"]["solana"]
        if collection.get("complete") is not True or window.get("resolved") is not True or scope.get("resolved") is not True:
            raise ValueError("Complete fixed-window collection is required before probing")
        if window.get("start_ts") != timestamp(START) or window.get("end_ts") != timestamp(END):
            raise ValueError("Probe scope differs from the fixed study window")
        if not scope.get("main_blocks") or scope.get("uncertain_slots") or len(scope["main_blocks"]) != scope.get("expected_blocks") or len(set(scope["main_blocks"])) != len(scope["main_blocks"]):
            raise ValueError("Solana fixed-window manifest is incomplete")
        chosen, seen, hashes, errors = select(root, scope)
        report.update(population_transactions=seen, selected_transactions=len(chosen), input_block_hashes=hashes)
        report["errors"].extend(errors)
        if errors or not chosen:
            report["errors"].append({"reason": "No RPC probes performed because complete sampling frame was not established"})
            return finish()
        rpc = client(root, "solana")
        report.update(source_id=rpc.source_id, endpoint=rpc.public_endpoint)
        for item in chosen:
            record = {key: item[key] for key in ("slot", "tx_index", "signature", "execution_status", "raw_ref", "selection_reasons")}
            record["version_present"] = item["version"] is not MISSING
            record["version"] = item["version"] if item["version"] is not MISSING else None
            ledger = root / "provenance/request_log.jsonl"
            offset = ledger.stat().st_size if ledger.exists() else 0
            version = max(1, item["version"]) if type(item["version"]) is int else 1
            ceiling = max(version, 16)
            observed = None
            try:
                while True:
                    try:
                        observed = rpc.call("getTransaction", [item["signature"], {
                            "encoding": "json", "commitment": "finalized", "maxSupportedTransactionVersion": version}])
                        break
                    except RPCError as exc:
                        if exc.code == -32015 and version < ceiling:
                            version += 1
                            continue
                        raise
                if observed is None:
                    record.update(status="missing", reason="getTransaction returned explicit null")
                elif not isinstance(observed, dict):
                    record.update(status="mismatch", reason="getTransaction result is not an object")
                else:
                    expected = {"slot": item["slot"], "transaction": item["native"].get("transaction", MISSING),
                                "meta": item["native"].get("meta", MISSING)}
                    if item["block_time"] is not MISSING:
                        expected["blockTime"] = item["block_time"]
                    if item["version"] is not MISSING:
                        expected["version"] = item["version"]
                    compared = {key: observed[key] for key in ("slot", "blockTime", "transaction", "meta", "version") if key in observed}
                    diff = differences(expected, compared)
                    returned = observed.get("transaction")
                    signatures = returned.get("signatures") if isinstance(returned, dict) else None
                    record.update(signature_matches=isinstance(signatures, list) and bool(signatures) and signatures[0] == item["signature"],
                                  differences=diff, difference_limit=20,
                                  status="matched" if not diff else "mismatch")
                    if not record["signature_matches"]:
                        record["status"] = "mismatch"
            except (RPCError, ValueError, TypeError) as exc:
                record.update(status="request_failed", error_type=type(exc).__name__, error_code=getattr(exc, "code", None))
            record["max_supported_transaction_version"] = version
            record["request_evidence"] = request_evidence(root, offset, item["signature"], rpc.source_id)
            if not record["request_evidence"]:
                record.update(status="missing_provenance", reason="RPC attempt has no acquisition ledger receipt")
            report["checks"].append(record)
        if any(sha256(root / relative) != digest for relative, digest in hashes.items()):
            report["errors"].append({"reason": "Raw sampling frame changed during getTransaction probing"})
        report["passed"] = bool(report["checks"]) and not report["errors"] and all(r["status"] == "matched" for r in report["checks"])
    except (OSError, ValueError, KeyError, RPCError) as exc:
        report["errors"].append({"error_type": type(exc).__name__, "reason": str(exc)})
    return finish()
