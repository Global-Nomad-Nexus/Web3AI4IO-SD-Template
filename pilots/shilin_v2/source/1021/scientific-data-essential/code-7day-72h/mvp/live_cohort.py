"""Seven-day live cohort with a 72-hour per-event follow-up.

The process enrolls Pump.fun creates whose block times fall in a frozen
seven-day UTC window. T0 is requested when the creation is first decoded.
T24, T48 and T72 wait until that event's block time plus 24, 48 and 72 hours.
Receipts are rewritten after every enrollment batch and every checkpoint
attempt. A later call on the same directory resumes an unfinished cohort.
Discovery and observation errors are recorded and retried; they do not end
the process.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .acquire_chain import JsonRpcClient, FallbackRpcClient, decode_transaction
from .common import now_utc, parse_utc, read_csv, read_json, stable_hash, write_csv, write_json, write_jsonl
from .observe_metadata import observe_events
from .schedule import FOLLOWUP_SECONDS, event_in_window, plan_rows, validate_protocol
from .schema import ATTEMPT_FIELDS, EVENT_FIELDS, PLAN_FIELDS, SNAPSHOT_FIELDS


TERMINAL_STATUSES = {"success", "not_collected_policy"}
DEFAULT_AUTOSAVE_SECONDS = 600


def autosave_seconds(protocol: dict[str, Any]) -> float:
    """Return the progress interval. Missing or invalid values use 10 minutes."""
    raw = (protocol.get("observation") or {}).get("autosave_seconds", DEFAULT_AUTOSAVE_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(DEFAULT_AUTOSAVE_SECONDS)
    if value <= 0:
        return float(DEFAULT_AUTOSAVE_SECONDS)
    return value


def write_progress(dataset_dir: Path, run_dir: Path, snapshot: dict[str, Any]) -> None:
    """Save the latest progress and append it to the 10-minute history."""
    dataset_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "progress.json", snapshot)
    write_json(dataset_dir / "progress.json", snapshot)
    with (dataset_dir / "progress.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True, ensure_ascii=False) + "\n")
    next_at = snapshot.get("next_observation_at") or "-"
    window_in = snapshot.get("seconds_until_window")
    window_text = f" window_in={int(window_in)}s" if window_in else ""
    print(
        "progress "
        f"{snapshot['saved_at']} stage={snapshot['stage']} "
        f"events={snapshot['events']} "
        f"observations={snapshot['completed_observations']}/{snapshot['planned_observations']} "
        f"remaining={snapshot['remaining_observations']} "
        f"next={next_at}{window_text}",
        flush=True,
    )


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_rows(path: Path, fields: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return read_csv(path, fields)


def _failure_count(value: Any) -> int:
    if isinstance(value, dict):
        return int(value.get("count", 0))
    return int(value or 0)


def _failure_block_time(value: Any) -> int | None:
    if isinstance(value, dict) and str(value.get("block_time", "")).isdigit():
        return int(value["block_time"])
    return None


def _remember_failure(failures: dict[str, dict[str, str]], signature: str, block_time: Any) -> None:
    previous = failures.get(signature) or {}
    remembered = block_time if block_time is not None else _failure_block_time(previous)
    failures[signature] = {"count": str(_failure_count(previous) + 1), "block_time": "" if remembered is None else str(int(remembered))}


def _publish(state: dict[str, Any], batch: list[dict[str, str]]) -> None:
    callback = state.get("on_events")
    if callback and batch:
        callback(batch)


def _checkpoint(state: dict[str, Any], failures: dict[str, dict[str, str]], page_done: set[str]) -> None:
    state["signature_failures"] = failures
    state["page_done"] = sorted(page_done)
    callback = state.get("on_checkpoint")
    if callback:
        callback()


def fetch_parsed_transactions(client: Any, jobs: list[tuple[str, int]], workers: int = 4) -> list[tuple[str, int, Any, Exception | None]]:
    """Fetch parsed transactions. A selected fallback client uses several connections."""
    inner = getattr(client, "client", None)
    target = inner or client

    def one(job: tuple[str, int]) -> tuple[str, int, Any, Exception | None]:
        signature, block_time = job
        try:
            transaction = target.call("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
            return signature, block_time, transaction, None
        except Exception as exc:
            return signature, block_time, None, exc

    if inner is None or len(jobs) <= 1:
        return [one(job) for job in jobs]
    with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
        return list(pool.map(one, jobs))


def discover_window_events(client: JsonRpcClient, protocol: dict[str, Any], state: dict[str, Any], window_start: datetime, window_end: datetime) -> list[dict[str, str]]:
    """Poll newest program signatures and stop at the previous cursor or the window start.

    Each fully handled page is recorded in ``pending_before``. A later poll or
    a restarted process continues from that signature instead of the chain tip.
    A failed page does not move the cursor.
    """
    program_id = str(protocol.get("pumpfun_program_id"))
    events: list[dict[str, str]] = []
    failures: dict[str, dict[str, str]] = {}
    for key, value in (state.get("signature_failures") or {}).items():
        if isinstance(value, dict):
            failures[str(key)] = {"count": str(_failure_count(value)), "block_time": str(value.get("block_time", ""))}
        else:
            failures[str(key)] = {"count": str(_failure_count(value)), "block_time": ""}
    max_signature_retries = int(protocol.get("observation", {}).get("max_signature_retries", 5))
    # A 1000-signature page was timing out. Live polling uses short pages and
    # stops at the previous tip instead of replaying the whole window.
    live_tip = protocol.get("observation", {}).get("live_tip", True)
    configured_page_limit = max(1, int(protocol.get("acquisition", {}).get("page_limit", 100)))
    page_limit = min(configured_page_limit, 100) if live_tip else configured_page_limit
    transaction_budget = max(max(1, int(protocol.get("acquisition", {}).get("transactions_per_poll", 10))), page_limit)
    page_done = {str(item) for item in (state.get("page_done") or [])}
    if len(page_done) > page_limit:
        page_done = set()
        state["page_done"] = []
    transactions_this_poll = 0
    state["_batch_yielded"] = False
    deferred = [signature for signature, record in failures.items() if _failure_count(record) < max_signature_retries]
    for signature in deferred:
        if transactions_this_poll >= transaction_budget:
            state["_scan_complete"] = False
            state["_batch_yielded"] = True
            _checkpoint(state, failures, page_done)
            return events
        try:
            transactions_this_poll += 1
            transaction = client.call("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
        except Exception as exc:
            _remember_failure(failures, signature, None)
            print(f"transaction {signature} failed again: {exc}", flush=True)
            continue
        block_time = _failure_block_time(failures.get(signature))
        failures.pop(signature, None)
        page_done.add(signature)
        decoded = decode_transaction(transaction, signature, block_time, program_id)
        events.extend(decoded)
        _publish(state, decoded)
    _checkpoint(state, failures, page_done)

    if transactions_this_poll >= transaction_budget:
        state["_scan_complete"] = False
        state["_batch_yielded"] = True
        return events

    if live_tip:
        # Every poll starts at the chain tip. Older signatures belong to the gap task.
        state["pending_before"] = None
        state["scan_tip"] = None
        state["live_tip"] = True
        started_from_tip = True
        before = None
        scan_tip = None
    else:
        started_from_tip = not state.get("pending_before")
        before = state.get("pending_before") or None
        scan_tip = None if started_from_tip else state.get("scan_tip")
    pages = 0
    page_failed = False
    finished = False
    dropped_missing_cursor = False
    establish_tip = live_tip and not state.get("cursor")
    max_pages = 2 if live_tip else max(1, int(protocol.get("acquisition", {}).get("max_pages", 1)))
    while pages < max_pages:
        options: dict[str, Any] = {"limit": page_limit}
        if before:
            options["before"] = before
        pages += 1
        try:
            response = client.call("getSignaturesForAddress", [program_id, options])
        except Exception as exc:
            if "not found" in str(exc).lower() and before and not dropped_missing_cursor:
                print("resume signature is no longer on the RPC; scanning again from the chain tip", flush=True)
                dropped_missing_cursor = True
                before = None
                scan_tip = None
                started_from_tip = True
                state["pending_before"] = None
                state["scan_tip"] = None
                state["cursor"] = None
                page_done = set()
                state["page_done"] = []
                pages -= 1
                continue
            print(f"signature page failed: {exc}", flush=True)
            page_failed = True
            break
        page = response.get("result") or []
        if not page:
            finished = True
            break
        if scan_tip is None:
            scan_tip = str(page[0].get("signature") or "")
        reached_previous = False
        page_events: list[dict[str, str]] = []
        queued: list[tuple[str, int]] = []
        stop_before: str | None = None
        for item in page:
            signature = str(item.get("signature") or "")
            if transactions_this_poll >= transaction_budget:
                stop_before = previous_signature
                break
            previous_signature = signature
            if not signature or signature == state.get("cursor"):
                reached_previous = True
                break
            if signature in page_done:
                continue
            block_time = item.get("blockTime")
            if block_time is None or item.get("err") is not None:
                page_done.add(signature)
                continue
            event_time = datetime.fromtimestamp(int(block_time), tz=timezone.utc)
            if event_time < window_start:
                reached_previous = True
                break
            if event_time >= window_end:
                page_done.add(signature)
                continue
            if _failure_count(failures.get(signature)) >= max_signature_retries:
                page_done.add(signature)
                continue
            transactions_this_poll += 1
            queued.append((signature, int(block_time)))
        for signature, block_time, transaction, error in fetch_parsed_transactions(client, queued):
            if error is not None:
                _remember_failure(failures, signature, block_time)
                print(f"transaction {signature} failed: {error}", flush=True)
                continue
            failures.pop(signature, None)
            page_done.add(signature)
            decoded = decode_transaction(transaction, signature, block_time, program_id)
            page_events.extend(decoded)
            _publish(state, decoded)
        if queued or page_events:
            _checkpoint(state, failures, page_done)
        events.extend(page_events)
        if stop_before and not live_tip:
            state["pending_before"] = stop_before
            state["scan_tip"] = scan_tip
            state["_scan_complete"] = False
            state["_batch_yielded"] = True
            _checkpoint(state, failures, page_done)
            return events
        if stop_before or establish_tip or reached_previous or len(page) < page_limit:
            finished = True
            break
        before = str(page[-1].get("signature") or "") or before
        page_done.clear()
        state["pending_before"] = before
        state["scan_tip"] = scan_tip
        print(f"completed signature page; resume before {before}", flush=True)
        _checkpoint(state, failures, page_done)
    if finished and not page_failed:
        if scan_tip:
            state["cursor"] = scan_tip
        state["pending_before"] = None
        state["scan_tip"] = None
        page_done.clear()
    elif live_tip and not page_failed:
        if scan_tip:
            state["cursor"] = scan_tip
        state["pending_before"] = None
        state["scan_tip"] = None
        page_done.clear()
        state["_batch_yielded"] = False
    elif before and not page_failed:
        state["pending_before"] = before
        state["scan_tip"] = scan_tip
        state["_batch_yielded"] = True
    state["_scan_complete"] = finished and not page_failed
    state["signature_failures"] = failures
    state["page_done"] = sorted(page_done)
    if any(_failure_count(record) >= max_signature_retries for record in failures.values()):
        write_jsonl(Path(str(state.get("_output") or ".")) / "missing_transactions.jsonl", [{"signature": signature, "attempts": str(_failure_count(record)), "block_time": record.get("block_time", "")} for signature, record in sorted(failures.items()) if _failure_count(record) >= max_signature_retries])
    _checkpoint(state, failures, page_done)
    return events


def _terminal_keys(attempts: list[dict[str, str]], rounds: dict[str, int], max_rounds: int) -> set[tuple[str, str]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in attempts:
        grouped.setdefault((row["event_key"], row["checkpoint"]), []).append(row)
    done: set[tuple[str, str]] = set()
    for key, rows in grouped.items():
        if any(row["status"] in TERMINAL_STATUSES for row in rows):
            done.add(key)
            continue
        if any(row.get("http_status") in ("401", "403") for row in rows):
            done.add(key)
            continue
        if int(rounds.get(f"{key[0]}|{key[1]}", 0)) >= max_rounds:
            done.add(key)
    for key_text, count in rounds.items():
        event_key, separator, checkpoint = key_text.partition("|")
        if separator and int(count) >= max_rounds:
            done.add((event_key, checkpoint))
    return done


def run_live_cohort(protocol: dict[str, Any], source_register: list[dict[str, str]], output_dir: str | Path, rpc_endpoint: str | None = None, transport: Callable[..., Any] | None = None, clock: Callable[[], str] | None = None, sleep: Callable[[float], None] | None = None, discover: Callable[..., list[dict[str, str]]] | None = None, rpc_client: Any = None) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Enroll for seven UTC days and follow each event until 72 hours after its block time."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    clock = clock or now_utc
    sleep = sleep or __import__("time").sleep
    poll_seconds = float(protocol.get("observation", {}).get("poll_seconds", 20))
    save_every = autosave_seconds(protocol)
    max_rounds = int(protocol.get("observation", {}).get("max_retry_rounds", 5))

    status_path = output / "cohort_status.json"
    clock_path = output / "cohort_clock.json"
    protocol_path = output / "cohort_protocol.json"
    saved_status = read_json(status_path) if status_path.exists() else {}
    if saved_status.get("phase") == "finished" and (output / "launch_events.csv").exists():
        frozen = read_json(protocol_path) if protocol_path.exists() else dict(protocol)
        print(f"live cohort already finished with {saved_status.get('events', 0)} events", flush=True)
        return _load_rows(output / "launch_events.csv", EVENT_FIELDS), frozen

    if clock_path.exists():
        saved_clock = read_json(clock_path)
        window_start = parse_utc(str(saved_clock["window_start"]))
        enroll_until = parse_utc(str(saved_clock["enrollment_until"]))
        started = parse_utc(str(saved_clock["collection_started_at"]))
        print(f"resuming live cohort; window {saved_clock['window_start']} .. {saved_clock['enrollment_until']}", flush=True)
    else:
        window_start, enroll_until = validate_protocol(protocol)
        started = parse_utc(clock())
        write_json(clock_path, {
            "collection_started_at": _iso(started),
            "window_start": _iso(window_start),
            "enrollment_until": _iso(enroll_until),
            "followup_until": _iso(enroll_until + timedelta(seconds=FOLLOWUP_SECONDS)),
            "clock": "chain_event_time",
            "t0": "first_observation_time",
            "followups": "T24, T48 and T72 use block_time and cannot start early",
        })

    frozen = dict(protocol)
    frozen["collection_started_at"] = _iso(started)
    frozen["window"] = {
        "start": _iso(window_start),
        "end": _iso(enroll_until),
        "inclusion": "start_inclusive_end_exclusive",
        "clock": "chain_event_time",
        "frozen": True,
    }
    frozen["observation"] = dict(protocol.get("observation", {}))
    write_json(protocol_path, frozen)

    client = None
    if discover is None:
        client = rpc_client or FallbackRpcClient(frozen, rpc_endpoint, output.parent, source_register)
        discover = discover_window_events
    state: dict[str, Any] = {
        "cursor": saved_status.get("cursor"),
        "pending_before": saved_status.get("pending_before"),
        "scan_tip": saved_status.get("scan_tip"),
        "page_done": list(saved_status.get("page_done") or []),
        "signature_failures": saved_status.get("signature_failures") or {},
        "final_scan_complete": bool(saved_status.get("final_scan_complete", False)),
        "live_tip": bool(saved_status.get("live_tip", False)),
        "_output": str(output),
    }
    events = _load_rows(output / "launch_events.csv", EVENT_FIELDS)
    plan = _load_rows(output / "observation_plan.csv", PLAN_FIELDS)
    seen_keys = {row["event_key"] for row in events}
    rounds = {str(key): int(value) for key, value in (saved_status.get("rounds") or {}).items()}
    done = _terminal_keys(_load_rows(output / "request_attempts.csv", ATTEMPT_FIELDS), rounds, max_rounds)

    def flush_events() -> None:
        write_csv(output / "launch_events.csv", EVENT_FIELDS, events)
        write_csv(output / "observation_plan.csv", PLAN_FIELDS, plan)

    def write_status(now: datetime, phase: str) -> None:
        write_json(status_path, {
            "phase": phase,
            "now": _iso(now),
            "events": len(events),
            "completed_observations": len(done),
            "planned_observations": len(plan),
            "cursor": state.get("cursor"),
            "pending_before": state.get("pending_before"),
            "scan_tip": state.get("scan_tip"),
            "page_done": list(state.get("page_done") or []),
            "signature_failures": state.get("signature_failures") or {},
            "live_tip": bool(state.get("live_tip")),
            "final_scan_complete": bool(state.get("final_scan_complete")),
            "rounds": rounds,
            "protocol_hash": stable_hash(frozen),
            "autosave_seconds": save_every,
        })

    last_autosave: datetime | None = None

    def save_progress(now: datetime, phase: str) -> None:
        nonlocal last_autosave
        due = last_autosave is None or (now - last_autosave).total_seconds() + 1e-6 >= save_every or phase == "finished"
        if not due:
            return
        flush_events()
        unfinished_rows = [row for row in plan if (row["event_key"], row["checkpoint"]) not in done]
        next_due = None
        overdue = 0
        planned_by: dict[str, int] = {}
        completed_by: dict[str, int] = {}
        for row in plan:
            planned_by[row["checkpoint"]] = planned_by.get(row["checkpoint"], 0) + 1
        for _event_key, checkpoint in done:
            completed_by[checkpoint] = completed_by.get(checkpoint, 0) + 1
        for row in unfinished_rows:
            target = parse_utc(row["scheduled_at"])
            if target <= now:
                overdue += 1
            elif next_due is None or target < next_due:
                next_due = target
        if now < window_start:
            stage = "waiting_for_window"
        elif now < enroll_until:
            stage = "enrolling"
        elif not state.get("final_scan_complete"):
            stage = "finishing_scan"
        elif unfinished_rows:
            stage = "following_up"
        else:
            stage = "finished"
        failures = state.get("signature_failures") or {}
        snapshot = {
            "saved_at": _iso(now),
            "stage": stage,
            "phase": phase,
            "window_start": _iso(window_start),
            "enrollment_until": _iso(enroll_until),
            "followup_until": _iso(enroll_until + timedelta(seconds=FOLLOWUP_SECONDS)),
            "events": len(events),
            "planned_observations": len(plan),
            "completed_observations": len(done),
            "remaining_observations": len(unfinished_rows),
            "overdue_observations": overdue,
            "planned_by_checkpoint": planned_by,
            "completed_by_checkpoint": completed_by,
            "final_scan_complete": bool(state.get("final_scan_complete")),
            "cursor": state.get("cursor"),
            "pending_before": state.get("pending_before"),
            "signature_failures": len(failures),
            "next_observation_at": _iso(next_due) if next_due else None,
            "seconds_until_window": max(0, int((window_start - now).total_seconds())) if now < window_start else 0,
            "autosave_seconds": save_every,
        }
        write_progress(output.parent, output, snapshot)
        last_autosave = now

    def observe_due(now: datetime) -> None:
        due_rows = [row for row in plan if (row["event_key"], row["checkpoint"]) not in done and now >= parse_utc(row["earliest_allowed_at"])]
        if not due_rows:
            return
        print(f"observing {len(due_rows)} checkpoint rows at {_iso(now)}", flush=True)
        try:
            attempts, _snapshots = observe_events(events, due_rows, source_register, frozen, output, transport=transport, clock=clock, append=True)
        except Exception as exc:
            print(f"observation failed and will be retried: {exc.__class__.__name__}: {exc}", flush=True)
            attempts = _load_rows(output / "request_attempts.csv", ATTEMPT_FIELDS)
        closing_rounds: dict[str, int] = {}
        for row in due_rows:
            deadline = parse_utc(row["scheduled_at"]) + timedelta(seconds=int(row["max_lateness_seconds"]))
            if now >= deadline:
                key = f"{row['event_key']}|{row['checkpoint']}"
                rounds[key] = int(rounds.get(key, 0)) + 1
                closing_rounds[key] = rounds[key]
        done.update(_terminal_keys(attempts, closing_rounds, max_rounds))

    def enroll(batch: list[dict[str, str]], seen_at: datetime) -> int:
        added = 0
        for event in batch:
            if event.get("event_key") in seen_keys:
                continue
            try:
                if not event_in_window(event, window_start, enroll_until):
                    continue
                rows = plan_rows(event, frozen, seen_at=seen_at)
            except ValueError as exc:
                print(f"skip {event.get('event_key', '')}: {exc}", flush=True)
                continue
            seen_keys.add(event["event_key"])
            events.append(event)
            plan.extend(rows)
            added += 1
        if added:
            print(f"enrolled {added} events; cohort size {len(events)}", flush=True)
            flush_events()
            observe_due(seen_at)
        return added

    state["on_events"] = lambda batch: enroll(batch, parse_utc(clock()))
    state["on_checkpoint"] = lambda: write_status(parse_utc(clock()), "running")
    flush_events()
    while True:
        now = parse_utc(clock())
        retryable_transactions = any(_failure_count(row) < int(frozen["observation"].get("max_signature_retries", 5)) for row in (state.get("signature_failures") or {}).values())
        live_tip = frozen.get("observation", {}).get("live_tip", True)
        scanning = now >= window_start and (now < enroll_until or retryable_transactions or (bool(state.get("pending_before")) and not live_tip))
        if scanning:
            try:
                state["_scan_complete"] = True
                found = discover(client, frozen, state, window_start, enroll_until)
                if not state.get("pending_before"):
                    state["final_scan_complete"] = True
            except Exception as exc:
                print(f"discovery failed and will be retried: {exc.__class__.__name__}: {exc}", flush=True)
                state["_scan_complete"] = False
                found = []
            enroll(found, now)
        now = parse_utc(clock())
        observe_due(now)
        flush_events()
        pending_times: list[float] = []
        if now < window_start:
            pending_times.append(max((window_start - now).total_seconds(), 0))
        elif now < enroll_until:
            pending_times.append(min(poll_seconds, max((enroll_until - now).total_seconds(), 0)))
        if state.get("pending_before") and not frozen.get("observation", {}).get("live_tip", True):
            pending_times.append(0)
        elif retryable_transactions:
            pending_times.append(poll_seconds)
        unfinished = [row for row in plan if (row["event_key"], row["checkpoint"]) not in done]
        for row in unfinished:
            target = parse_utc(row["scheduled_at"])
            if now < target:
                pending_times.append(max((target - now).total_seconds(), 0))
            else:
                pending_times.append(poll_seconds)
        phase = "running" if pending_times else "finished"
        write_status(now, phase)
        save_progress(now, phase)
        if not pending_times:
            break
        wait = min(pending_times)
        if last_autosave is not None:
            until_save = save_every - (now - last_autosave).total_seconds()
            if until_save > 0:
                wait = min(wait, until_save)
        if wait > 0:
            print(f"waiting {wait:.0f}s", flush=True)
            sleep(wait)
    if not (output / "request_attempts.csv").exists():
        write_csv(output / "request_attempts.csv", ATTEMPT_FIELDS, [])
        write_jsonl(output / "request_attempts.jsonl", [])
    if not (output / "response_snapshots.csv").exists():
        write_csv(output / "response_snapshots.csv", SNAPSHOT_FIELDS, [])
        write_jsonl(output / "response_bodies.jsonl", [])
    write_status(parse_utc(clock()), "finished")
    print(f"live cohort finished with {len(events)} events", flush=True)
    return events, frozen
