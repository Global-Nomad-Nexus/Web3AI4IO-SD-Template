"""Read-only second-source comparison, separate from offline file integrity."""
from pathlib import Path
import hashlib
import random
import json
from .common import CHAINS, load_json, write_json, utcnow
from .acquire import RPC, RPCError, endpoints, sol_block, evm_block

def run(root):
    root=Path(root)
    window=load_json(root/"reports/window.json")
    preflight=load_json(root/"reports/preflight.json")
    baseline_sources={}
    with (root/"provenance/request_log.jsonl").open() as handle:
        for line in handle:
            item=json.loads(line)
            if item.get("response_status")=="ok" and item.get("raw_path"):
                baseline_sources[item["raw_path"]]=item.get("source_id")
    report={"started_at":utcnow(),"seed":20260914,"chains":{},"scope":"Two boundary blocks plus three seeded main-window blocks; block hash and complete transaction ID list. Different public endpoints may share upstream infrastructure; this is source consistency, not an independent consensus proof."}
    for chain in CHAINS:
        scope=window["chains"][chain]
        provider=preflight["chains"][chain]
        seed=random.Random(20260914)
        heights=sorted(set(scope["boundary_blocks"]+seed.sample(scope["main_blocks"],min(3,len(scope["main_blocks"])))))
        checks=[];complete=False
        candidates=[c for c in provider["checks"] if c.get("core_access") and c["source_id"]!=provider["selected_source_id"]]
        for candidate in candidates:
            url=next((url for url in endpoints(root,chain) if hashlib.sha256(url.encode()).hexdigest()[:16]==candidate["source_id"]),None)
            if not url: continue
            rpc=RPC(root,chain,url,retries=2)
            current=[]
            for height in heights:
                item={"source_id":candidate["source_id"],"endpoint":rpc.public_endpoint,"height":height,"status":"unknown"}
                try:
                    relative=f"raw/{chain}/blocks/{height}.json.gz"
                    item["baseline_source_id"]=baseline_sources.get(relative)
                    if not item["baseline_source_id"] or item["baseline_source_id"]==candidate["source_id"]:
                        item["status"]="source_not_distinct" if item["baseline_source_id"] else "baseline_source_unknown"
                        current.append(item)
                        continue
                    original=load_json(root/relative)["result"]
                    other=sol_block(rpc,height) if chain=="solana" else evm_block(rpc,height)
                    field="blockhash" if chain=="solana" else "hash"
                    ids=lambda b: [t["transaction"]["signatures"][0] for t in b["transactions"]] if chain=="solana" else [t["hash"] for t in b["transactions"]]
                    item.update(expected_hash=original[field],observed_hash=other[field],transaction_ids_equal=ids(original)==ids(other))
                    item["status"]="matched" if original[field]==other[field] and item["transaction_ids_equal"] else "mismatch"
                except Exception as exc: item["error"]=str(exc)
                current.append(item)
            checks.extend(current)
            if all(c["status"]=="matched" for c in current): complete=True;break
        report["chains"][chain]={"status":"mismatch" if any(c["status"]=="mismatch" for c in checks) else "matched" if complete else "no_available_second_source","checks":checks}
        write_json(root/"reports/cross_source.json",report)
    report["completed_at"]=utcnow()
    report["passed"]=not any(c["status"]=="mismatch" for c in report["chains"].values())
    report["acceptance_scope"]="No observed conflict; unavailable second sources remain unverified"
    write_json(root/"reports/cross_source.json",report)
    return report
