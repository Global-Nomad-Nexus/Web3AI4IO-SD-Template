"""Frozen seven-day cohort and 72-hour per-event observation schedule.

The live window is seven complete UTC days, chosen before collection.
T0 is requested when the collector first sees the creation. T24, T48 and T72
are requested at that event's block time plus 24, 48 and 72 hours, and not
before. This module does not reconstruct a window that has already started.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .common import parse_utc


WEEK_SECONDS = 7 * 24 * 3600
FOLLOWUP_SECONDS = 72 * 3600
CHECKPOINTS = ("T0", "T24", "T48", "T72")
OFFSETS = {"T0": 0, "T24": 24 * 3600, "T48": 48 * 3600, "T72": 72 * 3600}
LATENESS_SECONDS = {"T0": 5 * 60, "T24": 60 * 60, "T48": 2 * 60 * 60, "T72": 3 * 60 * 60}
JOIN_GRACE = timedelta(minutes=5)


def chain_time(event: dict) -> datetime:
    raw = str(event.get("block_time", ""))
    if not raw.isdigit():
        raise ValueError(f"Event {event.get('event_key', '')} has no numeric block_time")
    return datetime.fromtimestamp(int(raw), tz=timezone.utc)


def event_in_window(event: dict, start: datetime, end: datetime) -> bool:
    moment = chain_time(event)
    return start <= moment < end


def validate_protocol(protocol: dict) -> tuple[datetime, datetime]:
    """Reject a protocol that is not the frozen seven-day, 72-hour design."""
    window = protocol.get("window") or {}
    if window.get("inclusion") != "start_inclusive_end_exclusive":
        raise ValueError("window inclusion must be start_inclusive_end_exclusive")
    if window.get("clock") != "chain_event_time":
        raise ValueError("window clock must be chain_event_time")
    start = parse_utc(str(window.get("start", "")))
    end = parse_utc(str(window.get("end", "")))
    if (start.hour, start.minute, start.second, start.microsecond) != (0, 0, 0, 0):
        raise ValueError("window start must be UTC midnight")
    if (end.hour, end.minute, end.second, end.microsecond) != (0, 0, 0, 0):
        raise ValueError("window end must be UTC midnight")
    if int((end - start).total_seconds()) != WEEK_SECONDS:
        raise ValueError("window must be exactly seven consecutive UTC days")
    observation = protocol.get("observation") or {}
    if list(observation.get("checkpoints") or []) != list(CHECKPOINTS):
        raise ValueError("checkpoints must be T0, T24, T48, T72")
    offsets = {str(name): int(seconds) for name, seconds in (observation.get("checkpoint_offsets_seconds") or {}).items()}
    if offsets != OFFSETS:
        raise ValueError("checkpoint offsets must be 0, 24h, 48h and 72h from the event anchor")
    lateness = {str(name): int(seconds) for name, seconds in (observation.get("checkpoint_max_lateness_seconds") or {}).items()}
    if lateness != LATENESS_SECONDS:
        raise ValueError("checkpoint lateness must stay at the frozen engineering targets: T0 5 min, T24 1 h, T48 2 h, T72 3 h")
    if int(observation.get("enrollment_seconds", 0)) != WEEK_SECONDS:
        raise ValueError("enrollment_seconds must be seven days")
    if int(observation.get("followup_seconds", 0)) != FOLLOWUP_SECONDS:
        raise ValueError("followup_seconds must be 72 hours")
    return start, end


def assert_window_joinable(protocol: dict, now: datetime) -> None:
    start, _end = validate_protocol(protocol)
    if now > start + JOIN_GRACE:
        raise SystemExit(
            f"Frozen window {start.strftime('%Y-%m-%dT%H:%M:%SZ')} has already started "
            f"(now {now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}). "
            "A late start cannot supply prospective T0 observations. Freeze the next seven complete UTC days."
        )


def runtime_budget_seconds(protocol: dict, now: datetime) -> int:
    """Seconds from now until the last possible T72, plus its lateness and a short flush."""
    _start, end = validate_protocol(protocol)
    horizon = end + timedelta(seconds=FOLLOWUP_SECONDS + LATENESS_SECONDS["T72"] + 900)
    remaining = (horizon - now.astimezone(timezone.utc)).total_seconds()
    if remaining > 0:
        return int(remaining)
    return 12 * 3600


def plan_rows(event: dict, protocol: dict, seen_at: datetime | None = None) -> list[dict[str, str]]:
    """Build four observation rows for one enrolled event.

    Fixture plans pass ``seen_at=None`` and anchor T0 to block time. Live plans
    pass the clock time at which the creation was first decoded.
    """
    moment = chain_time(event)
    observation = protocol["observation"]
    lateness = {str(name): int(seconds) for name, seconds in observation["checkpoint_max_lateness_seconds"].items()}
    offsets = {str(name): int(seconds) for name, seconds in observation["checkpoint_offsets_seconds"].items()}
    rows: list[dict[str, str]] = []
    for name in observation["checkpoints"]:
        if name == "T0" and seen_at is not None:
            scheduled = seen_at.astimezone(timezone.utc)
        else:
            scheduled = moment + timedelta(seconds=offsets[name])
        text = scheduled.isoformat(timespec="seconds").replace("+00:00", "Z")
        rows.append({
            "event_key": event["event_key"],
            "checkpoint": name,
            "required": "true",
            "scheduled_at": text,
            "earliest_allowed_at": text,
            "max_lateness_seconds": str(lateness[name]),
            "protocol_version": str(protocol["protocol_version"]),
            "plan_status": "scheduled",
        })
    return rows
