"""Resolve a documented schedule subset to real UTC instants."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_WINDOW = timedelta(days=62)


def parse_aware(value):
    """Return a UTC datetime, or None when the value is not an aware instant."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def audit_bounds(audit):
    """Return (start, end), None, or 'too_large'."""
    if not isinstance(audit, dict) or not isinstance(audit.get("window"), dict):
        return None
    window = audit["window"]
    start = parse_aware(window.get("start"))
    end = parse_aware(window.get("end"))
    if start is None or end is None or end <= start:
        return None
    if end - start > MAX_WINDOW:
        return "too_large"
    return (start, end)


def _unknown(reason):
    return {
        "status": "unknown",
        "reason": reason,
        "mode": "none",
        "instants": set(),
        "start": None,
        "end": None,
    }


def _instants(instants):
    return {
        "status": "resolved",
        "reason": "resolved",
        "mode": "instants",
        "instants": set(instants),
        "start": None,
        "end": None,
    }


def _window(start, end):
    return {
        "status": "resolved",
        "reason": "resolved",
        "mode": "window",
        "instants": set(),
        "start": start,
        "end": end,
    }


def _parse_field(token, low, high):
    if token == "*":
        return None
    if token.isdigit():
        value = int(token)
        if value < low or value > high:
            return "bad"
        return {value}
    if len(token.split("-")) == 2 and all(part.isdigit() for part in token.split("-")):
        left, right = (int(part) for part in token.split("-"))
        if left < low or right > high or left > right:
            return "bad"
        return set(range(left, right + 1))
    return "bad"


def parse_cron(expression):
    """Parse the supported five-field subset, or return None."""
    if not isinstance(expression, str):
        return None
    parts = expression.split()
    if len(parts) != 5:
        return None
    ranges = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
    parsed = []
    for token, bounds in zip(parts, ranges):
        field = _parse_field(token, *bounds)
        if field == "bad":
            return None
        parsed.append(field)
    _minute, _hour, dom, _month, dow = parsed
    if dom is not None and dow is not None:
        return None
    return tuple(parsed)


def _candidate(zone, year, month, day, hour, minute, start, end):
    samples = []
    for fold in (0, 1):
        local = datetime(year, month, day, hour, minute, tzinfo=zone, fold=fold)
        utc = local.astimezone(timezone.utc)
        back = utc.astimezone(zone)
        gap = (back.year, back.month, back.day, back.hour, back.minute) != (
            year,
            month,
            day,
            hour,
            minute,
        )
        samples.append((utc, gap, local.utcoffset()))
    in_window = [sample for sample in samples if start <= sample[0] < end]
    if not in_window:
        return "skip", None
    ambiguous = samples[0][2] != samples[1][2]
    if ambiguous or any(sample[1] for sample in in_window):
        return "dst", None
    return "ok", samples[0][0]


def _resolve_cron(schedule, bounds):
    timezone_name = schedule.get("timezone")
    if not isinstance(timezone_name, str) or timezone_name.strip() == "":
        return _unknown("timezone_missing")
    if timezone_name.strip().lower() == "unknown":
        return _unknown("timezone_missing")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return _unknown("timezone_invalid")
    fields = parse_cron(schedule.get("expression"))
    if fields is None:
        return _unknown("cron_unsupported")
    minute_field, hour_field, dom_field, month_field, dow_field = fields
    start, end = bounds
    instants = set()
    day = (start.astimezone(zone) - timedelta(days=1)).date()
    last = (end.astimezone(zone) + timedelta(days=1)).date()
    while day <= last:
        cron_dow = (day.weekday() + 1) % 7
        if month_field is not None and day.month not in month_field:
            day += timedelta(days=1)
            continue
        if dom_field is not None and day.day not in dom_field:
            day += timedelta(days=1)
            continue
        if dow_field is not None and cron_dow not in dow_field:
            day += timedelta(days=1)
            continue
        hours = hour_field if hour_field is not None else range(24)
        minutes = minute_field if minute_field is not None else range(60)
        for hour in hours:
            for minute in minutes:
                outcome, instant = _candidate(
                    zone, day.year, day.month, day.day, hour, minute, start, end
                )
                if outcome == "dst":
                    return _unknown("dst_semantics")
                if outcome == "ok":
                    instants.add(instant)
        day += timedelta(days=1)
    return _instants(instants)


def _known_scope(schedule):
    scope = schedule.get("scope")
    return isinstance(scope, str) and scope.strip() != "" and scope.strip().lower() != "unknown"


def resolve_schedule(schedule, bounds):
    """Resolve one schedule inside the audit window."""
    if bounds is None:
        return _unknown("audit_window_missing")
    if bounds == "too_large":
        return _unknown("window_too_large")
    if not isinstance(schedule, dict):
        return _unknown("schedule_missing")
    if not _known_scope(schedule):
        return _unknown("schedule_scope_unknown")
    kind = schedule.get("kind")
    if kind == "instants":
        values = schedule.get("instants")
        if not isinstance(values, list) or not values:
            return _unknown("instants_missing")
        instants = []
        for value in values:
            parsed = parse_aware(value)
            if parsed is None:
                return _unknown("instant_tz_missing")
            instants.append(parsed)
        start, end = bounds
        return _instants(item for item in instants if start <= item < end)
    if kind == "cron":
        if schedule.get("flexible") is True:
            return _unknown("flexible_cron")
        return _resolve_cron(schedule, bounds)
    if kind == "window":
        if schedule.get("flexible") is not False:
            return _unknown("flexible_window")
        raw = schedule.get("window")
        if not isinstance(raw, dict):
            return _unknown("window_missing")
        start = parse_aware(raw.get("start"))
        end = parse_aware(raw.get("end"))
        if start is None or end is None:
            return _unknown("window_tz_missing")
        if end <= start:
            return _unknown("window_invalid")
        audit_start, audit_end = bounds
        clipped_start = max(start, audit_start)
        clipped_end = min(end, audit_end)
        if clipped_end <= clipped_start:
            return _instants(())
        return _window(clipped_start, clipped_end)
    return _unknown("kind_unsupported")


def overlaps(left, right):
    """True when two resolved schedules share time inside the audit window."""
    if left["mode"] == "window" and right["mode"] == "window":
        return left["start"] < right["end"] and right["start"] < left["end"]
    if left["mode"] == "window" and right["mode"] == "instants":
        return any(left["start"] <= item < left["end"] for item in right["instants"])
    if right["mode"] == "window" and left["mode"] == "instants":
        return any(right["start"] <= item < right["end"] for item in left["instants"])
    return bool(left["instants"] & right["instants"])
