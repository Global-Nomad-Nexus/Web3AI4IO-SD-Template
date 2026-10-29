"""Small live probe: connect to Solana and decode a few real Pump.fun creates.

This does not open the seven-day cohort. It reads recent program signatures,
fetches at most 250 transactions, and stops after 3 decoded creations.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from mvp.acquire_chain import PUMPFUN_PROGRAM_ID, JsonRpcClient, decode_transaction
from mvp.observe_metadata import HttpTransport

ENDPOINT = "https://solana-rpc.publicnode.com"
MAX_TRANSACTIONS = 250
TARGET_CREATES = 3
OUT = Path("/work/so192/scientific data/data/probe-live-20261007")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = JsonRpcClient(ENDPOINT, timeout=20, max_attempts=2, min_interval=0.2)
    slot = client.call("getSlot", [{"commitment": "finalized"}]).get("result")
    print(f"connected endpoint={ENDPOINT} slot={slot}", flush=True)

    before = None
    signatures_seen = 0
    creates = []
    fetched = 0
    errors = 0
    instruction_names: dict[str, int] = {}
    while fetched < MAX_TRANSACTIONS and len(creates) < TARGET_CREATES:
        options: dict = {"limit": 20}
        if before:
            options["before"] = before
        page = client.call("getSignaturesForAddress", [PUMPFUN_PROGRAM_ID, options]).get("result") or []
        if not page:
            break
        signatures_seen += len(page)
        before = page[-1].get("signature")
        print(f"signatures seen={signatures_seen} newest={page[0].get('signature', '')[:12]}", flush=True)
        for item in page:
            if fetched >= MAX_TRANSACTIONS or len(creates) >= TARGET_CREATES:
                break
            signature = str(item.get("signature") or "")
            if not signature or item.get("err") is not None or item.get("blockTime") is None:
                continue
            fetched += 1
            try:
                transaction = client.call("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
            except Exception as exc:
                errors += 1
                print(f"transaction failed {signature[:12]} {exc.__class__.__name__}: {exc}", flush=True)
                continue
            logs = ((transaction.get("result") or {}).get("meta") or {}).get("logMessages") or []
            for line in logs:
                if line.startswith("Program log: Instruction:"):
                    name = line.split("Instruction:", 1)[1].strip()
                    instruction_names[name] = instruction_names.get(name, 0) + 1
            if fetched % 25 == 0:
                print(f"scanned {fetched} transactions instructions={instruction_names}", flush=True)
            decoded = decode_transaction(transaction, signature, int(item["blockTime"]))
            if not decoded:
                continue
            event = decoded[0]
            block = datetime.fromtimestamp(int(event["block_time"]), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            creates.append({
                "signature": signature,
                "block_time": block,
                "mint": event["mint"],
                "creator": event["creator"],
                "metadata_uri": event["metadata_uri"],
                "decoder_version": event["decoder_version"],
            })
            print(
                f"create {len(creates)} block={block} mint={event['mint']} creator={event['creator']} uri={event['metadata_uri'][:140]}",
                flush=True,
            )

    metadata = None
    if creates and creates[0]["metadata_uri"].startswith("https://"):
        result = HttpTransport(timeout=20)(creates[0]["metadata_uri"])
        metadata = {
            "uri": creates[0]["metadata_uri"],
            "status": result.status,
            "http_status": result.http_status,
            "bytes": len(result.body or b""),
            "content_type": result.content_type,
            "error": result.error_message,
        }
        print(
            f"metadata status={result.status} http={result.http_status} bytes={metadata['bytes']} error={result.error_message}",
            flush=True,
        )

    summary = {
        "endpoint": ENDPOINT,
        "slot": slot,
        "signatures_seen": signatures_seen,
        "transactions_fetched": fetched,
        "transaction_errors": errors,
        "instruction_names": instruction_names,
        "creates": creates,
        "metadata": metadata,
        "rpc_calls": client.calls,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"summary {OUT / 'summary.json'} creates={len(creates)} fetched={fetched} errors={errors} instructions={instruction_names}", flush=True)
    if fetched == 0:
        raise SystemExit("RPC connected but no Pump.fun transactions were fetched")


if __name__ == "__main__":
    main()
