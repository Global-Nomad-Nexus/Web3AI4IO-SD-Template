"""Fill missing block-time holes in the running cohort and merge them in place.

The extra task writes only to its own working directory. After the same T0,
T24, T48 and T72 rules have been applied, rows are appended to the main
dataset with the cohort schema. Nothing in those tables marks the rows as
supplemented.
"""

from __future__ import annotations

import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from mvp.acquire_chain import PUMPFUN_PROGRAM_ID, JsonRpcClient, decode_transaction
from mvp.common import ipv4_opener, now_utc, parse_utc, read_csv, read_json, read_jsonl, write_csv, write_json, write_jsonl
from mvp.observe_metadata import observe_events
from mvp.schedule import plan_rows
from mvp.schema import ATTEMPT_FIELDS, EVENT_FIELDS, PLAN_FIELDS, SNAPSHOT_FIELDS

MAIN = Path("/work/so192/scientific data/data/7day-72h-20261008T000000Z")
WORK = MAIN.parent / ".cohort-gap-work"
ROOT = Path("/work/so192/scientific data/7day+72h")
# PublicNode drops getSignaturesForAddress cursors once they age out of its
# index, including every signature on the last good page. Historical blocks
# are read from an archive endpoint instead, one slot at a time.
ENDPOINT = "https://public.rpc.solanavibestation.com/historical"
BLOCK_WORKERS = 5
REQUEST_INTERVAL = 0.8
HOLE_SECONDS = 3600
SLOT_MARGIN = 25
BLOCK_CHUNK = 1000
BLOCK_READ_ATTEMPTS = 4
BLOCK_CONFIG = {
    "encoding": "json",
    "transactionDetails": "full",
    "rewards": False,
    "maxSupportedTransactionVersion": 1,
}


def missing_ranges(block_times: list[int], minimum_hole: int = HOLE_SECONDS) -> list[tuple[int, int]]:
    """Return exclusive (start, end) holes between sorted block times."""
    ranges: list[tuple[int, int]] = []
    for earlier, later in zip(block_times, block_times[1:]):
        if later - earlier >= minimum_hole:
            ranges.append((earlier, later))
    return ranges


def in_ranges(block_time: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < block_time < end for start, end in ranges)


def _load_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {row["event_key"] for row in read_csv(path, EVENT_FIELDS)}


def _append_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    existing = read_csv(path, fields) if path.exists() else []
    write_csv(path, fields, existing + rows)


def signature_is_missing(error: BaseException) -> bool:
    text = str(error).lower()
    return "not found" in text and "transaction" in text


def covered_slots(start_slot: int, end_slot: int, margin: int = SLOT_MARGIN) -> tuple[int, int] | None:
    """Slots to read around a hole. The time filter drops the boundary blocks."""
    first = start_slot + 1 - margin
    last = end_slot - 1 + margin
    if first < 0:
        first = 0
    if first > last:
        return None
    return first, last


def _account_keys(message: dict, meta: dict) -> list:
    keys = list(message.get("accountKeys") or [])
    loaded = meta.get("loadedAddresses") or {}
    keys.extend(loaded.get("writable") or [])
    keys.extend(loaded.get("readonly") or [])
    return keys


def events_from_block(block: dict, slot: int, ranges: list[tuple[int, int]]) -> list[dict[str, str]]:
    """Decode Pump.fun creates in one block whose time falls inside a hole."""
    block_time = block.get("blockTime")
    if block_time is None or not in_ranges(int(block_time), ranges):
        return []
    block_time = int(block_time)
    events: list[dict[str, str]] = []
    for entry in block.get("transactions") or []:
        if not isinstance(entry, dict):
            continue
        meta = entry.get("meta") or {}
        if meta.get("err") is not None:
            continue
        transaction = entry.get("transaction") or {}
        signatures = transaction.get("signatures") or []
        message = transaction.get("message") or {}
        if not signatures or not isinstance(message, dict):
            continue
        keys = _account_keys(message, meta)
        if PUMPFUN_PROGRAM_ID not in [key if isinstance(key, str) else key.get("pubkey", "") for key in keys]:
            continue
        payload = {"slot": slot, "transaction": {**transaction, "message": {**message, "accountKeys": keys}}, "meta": meta}
        events.extend(decode_transaction(payload, str(signatures[0]), block_time))
    return [event for event in events if in_ranges(int(event["block_time"]), ranges)]


def _boundary_slot(client: JsonRpcClient, signature: str) -> int:
    result = client.call("getTransaction", [signature, {"encoding": "json", "maxSupportedTransactionVersion": 1}]).get("result")
    if not result or result.get("slot") is None:
        raise RuntimeError(f"boundary transaction {signature[:12]} is not on the historical RPC")
    return int(result["slot"])


def _slot_skipped(error: BaseException) -> bool:
    """A skipped slot was never produced. A cleaned-up block is still a failure."""
    text = str(error).lower()
    return "skipped" in text and "cleaned up" not in text


def block_read_should_retry(error: BaseException) -> bool:
    """A pruned backend or a torn body is not proof that the slot is gone.

    The historical URL is load-balanced. Some nodes only keep the last day or
    two and answer with ``Block cleaned up`` plus a much newer first available
    slot. Another connection can still return the block.
    """
    if _slot_skipped(error):
        return False
    text = f"{error.__class__.__name__}: {error}".lower()
    return any(token in text for token in (
        "cleaned up", "does not exist on node", "first available block",
        "incompleteread", "timed out", "timeout", "transport",
        "connection reset", "remote end closed", "broken pipe", "badstatusline",
    ))


class _HistoricalMiss(Exception):
    """Fifteen slots in a row were missing from the nodes that answered."""

    def __init__(self, slots: list[int]):
        super().__init__("historical nodes missed a run of slots")
        self.slots = slots


def read_block(client, slot: int, config: dict, attempts: int = BLOCK_READ_ATTEMPTS, pause=time.sleep, refresh=None):
    """Read one block, opening a new connection after a pruned or torn reply."""
    last: BaseException | None = None
    for attempt in range(attempts):
        opener = None
        if attempt and refresh is not None:
            opener = refresh()
            pause(min(attempt, 3))
        elif attempt:
            pause(min(attempt, 3))
        try:
            payload = client.call("getBlock", [slot, config], opener=opener)
        except Exception as exc:
            if _slot_skipped(exc):
                return None, None
            last = exc
            if attempt == 0 and block_read_should_retry(exc):
                print(f"slot {slot} read will be repeated on a new connection: {exc.__class__.__name__}", flush=True)
            if not block_read_should_retry(exc) or attempt + 1 == attempts:
                return None, last
            continue
        if not isinstance(payload, dict):
            return None, RuntimeError("RPC returned no block object")
        return payload.get("result"), None
    return None, last


def _remember(state_path: Path, holes: list[dict], failed: list[int], events: int, done: bool) -> None:
    write_json(state_path, {"mode": "slots", "done": done, "events": events, "holes": holes, "failed_slots": failed})


def _store_creates(run: Path, protocol: dict, known: set[str], found: list[dict[str, str]], events: list[dict[str, str]]) -> int:
    fresh = [event for event in events if event["event_key"] not in known]
    if not fresh:
        return 0
    seen_at = datetime.now(timezone.utc)
    new_plans: list[dict[str, str]] = []
    for event in fresh:
        known.add(event["event_key"])
        new_plans.extend(plan_rows(event, protocol, seen_at=seen_at))
    found.extend(fresh)
    _append_rows(run / "launch_events.csv", EVENT_FIELDS, fresh)
    _append_rows(run / "observation_plan.csv", PLAN_FIELDS, new_plans)
    return len(fresh)


def _observe_saved() -> None:
    """Apply the same checkpoint requests used by the running cohort."""
    run = WORK / "run"
    if not (run / "launch_events.csv").exists() or not (run / "observation_plan.csv").exists():
        return
    try:
        observe()
    except Exception as exc:
        print(f"observation will be retried: {exc.__class__.__name__}: {exc}", flush=True)


def scan() -> None:
    from concurrent.futures import ThreadPoolExecutor

    run = WORK / "run"
    run.mkdir(parents=True, exist_ok=True)
    source_events = read_csv(MAIN / "run" / "launch_events.csv", EVENT_FIELDS)
    by_time: dict[int, str] = {}
    for row in source_events:
        if row["block_time"].isdigit() and row["transaction_signature"]:
            by_time.setdefault(int(row["block_time"]), row["transaction_signature"])
    times = sorted(by_time)
    ranges = missing_ranges(times)
    write_json(WORK / "ranges.json", [{"start": start, "end": end} for start, end in ranges])
    if not ranges:
        print("no holes", flush=True)
        return
    known = _load_keys(MAIN / "run" / "launch_events.csv") | _load_keys(run / "launch_events.csv")
    protocol = read_json(MAIN / "run" / "cohort_protocol.json")
    state_path = WORK / "scan_state.json"
    state = read_json(state_path) if state_path.exists() else {"done": False}
    if state.get("done") and state.get("mode") == "slots":
        print("scan already complete", flush=True)
        return
    found = read_csv(run / "launch_events.csv", EVENT_FIELDS) if (run / "launch_events.csv").exists() else []
    saved = {(int(item["start"]), int(item["end"])): item for item in state.get("holes") or [] if state.get("mode") == "slots"}
    client = JsonRpcClient(ENDPOINT, timeout=45, max_attempts=4, min_interval=REQUEST_INTERVAL)
    holes: list[dict] = []
    for start, end in ranges:
        previous = saved.get((start, end))
        if previous and previous.get("done"):
            holes.append(previous)
            continue
        if previous and previous.get("first_slot") is not None:
            holes.append(previous)
            continue
        span = covered_slots(_boundary_slot(client, by_time[start]), _boundary_slot(client, by_time[end]))
        if span is None:
            holes.append({"start": start, "end": end, "first_slot": None, "last_slot": None, "next_slot": None, "done": True})
            continue
        first, last = span
        holes.append({"start": start, "end": end, "first_slot": first, "last_slot": last, "next_slot": first, "done": False})
    failed = [int(slot) for slot in (state.get("failed_slots") or [])]
    print(f"holes={len(ranges)} already={len(found)} reading slots on the historical RPC workers={BLOCK_WORKERS}", flush=True)
    for hole in holes:
        if hole.get("done"):
            continue
        print(
            f"hole {datetime.fromtimestamp(int(hole['start']), timezone.utc):%Y-%m-%dT%H:%MZ}"
            f" .. {datetime.fromtimestamp(int(hole['end']), timezone.utc):%Y-%m-%dT%H:%MZ}"
            f" slots {hole['next_slot']}..{hole['last_slot']}",
            flush=True,
        )

    connections = threading.local()

    def fresh_connection():
        connections.opener = ipv4_opener()
        return connections.opener

    def read_slot(slot: int) -> tuple[int, list[dict[str, str]], str | None]:
        block, error = read_block(client, slot, BLOCK_CONFIG, refresh=fresh_connection)
        if error is not None:
            return slot, [], str(error)
        if not block:
            return slot, [], None
        try:
            return slot, events_from_block(block, slot, ranges), None
        except Exception as exc:
            return slot, [], str(exc)

    def settle(slots: list[int]) -> int:
        """Read slots saved from an earlier pass. Returns how many of them are still unread."""
        pending = list(dict.fromkeys(slots))
        if not pending:
            return 0
        still: list[int] = []
        recovered = 0
        for slot in pending:
            _slot, events, error = read_slot(slot)
            if error:
                still.append(slot)
                print(f"slot {slot} still failed: {error}", flush=True)
            else:
                recovered += 1
                _store_creates(run, protocol, known, found, events)
        pending_set = set(pending)
        failed[:] = [item for item in failed if item not in pending_set] + still
        _remember(state_path, holes, failed, len(found), False)
        if recovered:
            _observe_saved()
        return len(still)

    def commit(batch: list[tuple[int, list[dict[str, str]], str | None]], hole: dict, streak: list[int]) -> None:
        added = 0
        for slot, events, error in batch:
            if error:
                print(f"slot {slot} failed: {error}", flush=True)
                failed.append(slot)
                streak[0] += 1
            else:
                streak[0] = 0
                added += _store_creates(run, protocol, known, found, events)
            hole["next_slot"] = slot + 1
        _remember(state_path, holes, failed, len(found), False)
        if added:
            _observe_saved()
        if streak[0] >= 15:
            raise _HistoricalMiss(list(dict.fromkeys(failed[-15:])))

    _observe_saved()
    with ThreadPoolExecutor(max_workers=BLOCK_WORKERS) as pool:
        if failed:
            print(f"retrying {len(failed)} saved slots", flush=True)
            settle(list(failed))
        for hole in holes:
            if hole.get("done") or hole.get("first_slot") is None:
                continue
            streak = [0]
            slot = int(hole["next_slot"])
            last = int(hole["last_slot"])
            seen = 0
            while slot <= last:
                chunk_end = min(last, slot + BLOCK_CHUNK - 1)
                try:
                    available = [int(item) for item in (client.call("getBlocks", [slot, chunk_end]).get("result") or [])]
                    if not available:
                        available = [int(item) for item in (client.call("getBlocks", [slot, chunk_end], opener=fresh_connection()).get("result") or [])]
                except Exception as exc:
                    print(f"getBlocks {slot}-{chunk_end} failed: {exc}; reading every slot in the chunk", flush=True)
                    available = list(range(slot, chunk_end + 1))
                if not available:
                    print(f"getBlocks {slot}-{chunk_end} returned no slots; reading every slot in the chunk", flush=True)
                    available = list(range(slot, chunk_end + 1))
                available = [item for item in available if item >= int(hole["next_slot"])]
                for offset in range(0, len(available), BLOCK_WORKERS):
                    batch = list(pool.map(read_slot, available[offset:offset + BLOCK_WORKERS]))
                    try:
                        commit(batch, hole, streak)
                    except _HistoricalMiss as miss:
                        print("historical nodes missed 15 slots; waiting, then asking again", flush=True)
                        time.sleep(45)
                        still = settle(miss.slots)
                        if still == len(set(miss.slots)):
                            raise SystemExit("historical block reads are failing; the saved slot is still the resume point")
                        streak[0] = still
                    previous = seen
                    seen += len(batch)
                    if previous // 30 != seen // 30:
                        print(f"events {len(found)} through slot {hole['next_slot'] - 1} toward {last}", flush=True)
                slot = chunk_end + 1
                hole["next_slot"] = max(int(hole["next_slot"]), slot)
                _remember(state_path, holes, failed, len(found), False)
            hole["done"] = True
            _remember(state_path, holes, failed, len(found), False)

        if failed:
            print(f"retrying {len(failed)} saved slots", flush=True)
            settle(list(failed))
    if failed:
        raise SystemExit(f"scan paused with {len(failed)} slots still unread; rerun continues from the saved slots")
    _remember(state_path, holes, [], len(found), True)
    print(f"scan complete events={len(found)}", flush=True)


def observe() -> None:
    run = WORK / "run"
    protocol = read_json(MAIN / "run" / "cohort_protocol.json")
    sources = read_csv(MAIN / "source_register.csv")
    events = read_csv(run / "launch_events.csv", EVENT_FIELDS)
    plan = read_csv(run / "observation_plan.csv", PLAN_FIELDS)
    done = {(row["event_key"], row["checkpoint"]) for row in read_csv(run / "request_attempts.csv", ATTEMPT_FIELDS)} if (run / "request_attempts.csv").exists() else set()
    now = datetime.now(timezone.utc)
    due = [row for row in plan if (row["event_key"], row["checkpoint"]) not in done and parse_utc(row["earliest_allowed_at"]) <= now]
    print(f"observing {len(due)} due rows of {len(plan)}", flush=True)
    if due:
        observe_events(events, due, sources, protocol, run, clock=now_utc, append=True)
    print("observation complete", flush=True)


def _merge_table(main_path: Path, extra_path: Path, fields: list[str], key) -> int:
    current = read_csv(main_path, fields) if main_path.exists() else []
    extra = read_csv(extra_path, fields) if extra_path.exists() else []
    seen = {key(row) for row in current}
    added = [row for row in extra if key(row) not in seen]
    if added:
        write_csv(main_path, fields, current + added)
    return len(added)


def _merge_jsonl(main_path: Path, extra_path: Path, key) -> int:
    current = read_jsonl(main_path) if main_path.exists() else []
    extra = read_jsonl(extra_path) if extra_path.exists() else []
    seen = {key(row) for row in current}
    added = [row for row in extra if key(row) not in seen]
    if added:
        write_jsonl(main_path, current + added)
    return len(added)


def merge() -> None:
    run = WORK / "run"
    if not (WORK / "scan_state.json").exists() or not read_json(WORK / "scan_state.json").get("done"):
        raise SystemExit("scan is not complete")
    observe()
    job_ids = subprocess.check_output(["squeue", "-u", "so192", "-n", "pump-7day-72h", "-h", "-o", "%i"], text=True).split()
    for job_id in job_ids:
        subprocess.check_call(["scancel", job_id])
    for _ in range(30):
        still = subprocess.check_output(["squeue", "-u", "so192", "-n", "pump-7day-72h", "-h", "-o", "%i"], text=True).strip()
        if not still:
            break
        time.sleep(2)
    main_run = MAIN / "run"
    added_events = _merge_table(main_run / "launch_events.csv", run / "launch_events.csv", EVENT_FIELDS, lambda row: row["event_key"])
    added_plan = _merge_table(main_run / "observation_plan.csv", run / "observation_plan.csv", PLAN_FIELDS, lambda row: (row["event_key"], row["checkpoint"]))
    added_attempts = _merge_table(main_run / "request_attempts.csv", run / "request_attempts.csv", ATTEMPT_FIELDS, lambda row: (row["request_id"], row["attempt"]))
    _merge_jsonl(main_run / "request_attempts.jsonl", run / "request_attempts.jsonl", lambda row: (row.get("request_id"), row.get("attempt")))
    _merge_table(main_run / "response_snapshots.csv", run / "response_snapshots.csv", SNAPSHOT_FIELDS, lambda row: (row["request_id"], row["checkpoint"]))
    _merge_jsonl(main_run / "response_bodies.jsonl", run / "response_bodies.jsonl", lambda row: row.get("request_id"))
    subprocess.check_call(["sbatch", str(ROOT / "slurm" / "collect-7day-72h.sh")])
    print(f"merged events={added_events} plan={added_plan} attempts={added_attempts}", flush=True)
    # Remove the working files after they have been absorbed.
    for path in sorted(WORK.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
    for path in sorted(WORK.rglob("*"), reverse=True):
        if path.is_dir():
            path.rmdir()
    WORK.rmdir()


def main() -> None:
    import sys
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in {"scan", "all"}:
        scan()
    if step in {"observe", "all"}:
        observe()
    if step in {"merge", "all"}:
        merge()


if __name__ == "__main__":
    main()
