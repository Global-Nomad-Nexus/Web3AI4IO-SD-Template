"""Small file primitives; no network is imported by offline stages."""
from pathlib import Path
import gzip
import hashlib
import json
from datetime import datetime, timezone

CHAINS = {"solana": "solana:mainnet", "bsc": "eip155:56", "base": "eip155:8453"}
START = "2026-09-14T12:00:00Z"
END = "2026-09-14T12:05:00Z"

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def timestamp(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())

def load_json(path):
    path = Path(path)
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as fh:
        return json.load(fh)

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def file_hashes(root, prefixes=("raw", "tables/base")):
    root = Path(root)
    return {str(p.relative_to(root)): sha256(p) for prefix in prefixes
            for p in sorted((root / prefix).rglob("*")) if p.is_file()}

def implementation_hashes(root):
    """Portable implementation inputs, excluding runtime caches and reports."""
    root=Path(root)
    paths=[p for name in ("claire_demo","config","sources") for p in (root/name).rglob("*")
           if p.is_file() and "__pycache__" not in p.parts]
    paths.extend(root/name for name in ("requirements.txt","requirements-local.lock.txt") if (root/name).exists())
    return {str(p.relative_to(root)):sha256(p) for p in sorted(paths)}

def save_raw(path, response):
    """Immutable successful RPC envelope; gzip timestamp is deterministic."""
    path = Path(path)
    payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode()
    if path.exists():
        if load_json(path) != response:
            raise RuntimeError(f"Refusing to replace immutable raw response: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(gzip.compress(payload + b"\n", mtime=0))
    temporary.replace(path)

def append_jsonl(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
