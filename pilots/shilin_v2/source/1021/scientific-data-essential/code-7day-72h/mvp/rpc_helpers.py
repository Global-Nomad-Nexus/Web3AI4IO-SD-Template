"""RPC route override for the frozen seven-day, 72-hour collector."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit


def record_rpc_override(protocol: dict, sources: list[dict], endpoint: str) -> None:
    """Record a selected runtime route without changing publication decisions."""
    for candidate in protocol["api_candidates"]:
        if candidate.get("endpoint") == endpoint:
            candidate.update(access_decision="allowed", role="user-selected-chain-rpc", selection_note="Explicit endpoint choice for this invocation; availability is established only by its request evidence.")
    source = next((row for row in sources if row.get("endpoint") == endpoint), None)
    if source is None:
        source = {field: "" for field in sources[0]}
        source.update(host=urlsplit(endpoint).hostname or "", endpoint=endpoint, acquisition_method="Solana JSON-RPC")
        sources.append(source)
    source.update(automatic_access_decision="allowed", query_scope="User-selected Solana RPC for this cohort", temporary_retention_decision="retain run receipt only", reproduction_mode="live_rerun_only", checked_at=datetime.now(timezone.utc).date().isoformat(), evidence_id="SRC-RPC-USER")

