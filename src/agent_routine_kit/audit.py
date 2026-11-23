"""Deterministic offline audit of a normalized routine snapshot."""

from __future__ import annotations

from agent_routine_kit.errors import ContractError
from agent_routine_kit.schedule import audit_bounds, overlaps, parse_aware, resolve_schedule
from agent_routine_kit.versions import (
    CONTRACT_VERSION,
    KIT_VERSION,
    MAX_ROUTINES,
    REPORT_VERSION,
    RULES_VERSION,
    SCHEMA_VERSION,
)

TOP_KEYS = {"contract_version", "export", "routines", "audit"}
EXPORT_KEYS = {"source", "coverage", "pagination", "exported_at", "deadline_coverage"}
PAGINATION_KEYS = {"complete"}
AUDIT_KEYS = {"window", "as_of"}
WINDOW_KEYS = {"start", "end"}
ROUTINE_KEYS = {
    "id",
    "name",
    "identity",
    "target",
    "schedule",
    "auth_recovery",
    "notification",
    "delivery",
    "deadline",
    "runs",
}
IDENTITY_KEYS = {"account", "cli", "profile"}
TARGET_KEYS = {
    "resource_id",
    "topic",
    "action",
    "source",
    "deliverable",
    "output_scope",
}
SCHEDULE_KEYS = {"kind", "expression", "timezone", "instants", "window", "flexible", "scope"}
AUTH_KEYS = {"policy"}
NOTIFICATION_KEYS = {"owner", "channel", "events"}
EVENT_KEYS = {"at", "idempotency_key", "kind"}
DELIVERY_KEYS = {
    "state",
    "idempotency_key",
    "attempts",
    "last_alert",
    "notify",
    "claimed",
    "receipt",
}
ATTEMPT_KEYS = {"at", "result", "receipt_id", "idempotency_key"}
RECEIPT_KEYS = {"id", "confirmed_at"}
DEADLINE_KEYS = {"at", "timezone"}
RUN_KEYS = {"scheduled_at", "status"}
SCOPE_FIELDS = (
    ("identity", "account"),
    ("identity", "cli"),
    ("identity", "profile"),
    ("target", "resource_id"),
    ("target", "topic"),
    ("target", "action"),
    ("target", "source"),
    ("target", "deliverable"),
    ("target", "output_scope"),
)
KNOWN_POLICIES = {"auto-login", "no-login", "manual"}
MISLEADING_RESULTS = {"http_200", "exit_0", "started", "notify"}
CLAIMED_DELIVERED = {"delivered", "sent", "notified"}


def audit_snapshot(data):
    """Return a versioned report. Raise ContractError when the contract is unusable."""
    _require_contract(data)
    findings = []
    findings.extend(_unknown_field_findings(data))
    findings.extend(_shape_findings(data))
    export = data.get("export") if isinstance(data.get("export"), dict) else {}
    audit = data.get("audit") if isinstance(data.get("audit"), dict) else {}
    findings.extend(_coverage_findings(export))
    findings.extend(_deadline_coverage_findings(export, audit))
    raw_routines = data.get("routines") if isinstance(data.get("routines"), list) else []
    indexed = list(enumerate(raw_routines))
    too_large = len(raw_routines) > MAX_ROUTINES
    if too_large:
        findings.append(
            _finding(
                "snapshot_too_large",
                "routine_limit",
                detail=f"routine_count={len(raw_routines)}; limit={MAX_ROUTINES}",
                severity="error",
            )
        )
    prepared = []
    seen_ids = {}
    for index, routine in indexed:
        if not isinstance(routine, dict):
            findings.append(
                _finding(
                    "malformed_routine",
                    "not_an_object",
                    fields=[f"routines[{index}]"],
                    severity="error",
                )
            )
            continue
        routine_id = routine.get("id")
        if not isinstance(routine_id, str) or routine_id.strip() == "":
            findings.append(
                _finding(
                    "malformed_routine",
                    "missing_id",
                    fields=[f"routines[{index}]"],
                    severity="error",
                )
            )
            continue
        if routine_id in seen_ids:
            findings.append(
                _finding(
                    "malformed_routine",
                    "duplicate_id",
                    subjects=[routine_id],
                    severity="error",
                )
            )
            continue
        seen_ids[routine_id] = index
        prepared.append(routine)
    prepared.sort(key=lambda item: item["id"])
    bounds = audit_bounds(audit)
    as_of = parse_aware(audit.get("as_of")) if isinstance(audit, dict) else None
    deadline_complete = export.get("deadline_coverage") == "complete"
    routine_reports = []
    resolved = {}
    if not too_large:
        for routine in prepared:
            routine_findings, schedule, summary = _audit_routine(
                routine, bounds, as_of, deadline_complete
            )
            findings.extend(routine_findings)
            resolved[routine["id"]] = schedule
            routine_reports.append(summary)
        findings.extend(_pair_findings(prepared, resolved))
        pairs = _pairs(prepared, resolved)
    else:
        for routine in prepared:
            routine_reports.append(
                {
                    "id": routine["id"],
                    "delivery_status": "unknown",
                    "schedule_status": "unknown",
                    "scope_status": "unknown",
                }
            )
        pairs = []
    findings = sorted(
        findings,
        key=lambda item: (
            item["code"],
            item["subjects"],
            item["reason"],
            item["fields"],
            item["detail"],
        ),
    )
    by_code = {}
    for item in findings:
        by_code[item["code"]] = by_code.get(item["code"], 0) + 1
    pagination = export.get("pagination") if isinstance(export.get("pagination"), dict) else {}
    coverage_status = (
        "complete"
        if export.get("coverage") == "complete" and pagination.get("complete") is True
        else "unknown"
    )
    return {
        "all_clear": not any(item["blocks_all_clear"] for item in findings),
        "contract_version": CONTRACT_VERSION,
        "coverage": {
            "deadline_coverage": export.get("deadline_coverage")
            if isinstance(export.get("deadline_coverage"), str)
            else None,
            "export_coverage": export.get("coverage")
            if isinstance(export.get("coverage"), str)
            else None,
            "pagination_complete": pagination.get("complete")
            if isinstance(pagination.get("complete"), bool)
            else None,
            "status": coverage_status,
        },
        "findings": findings,
        "kit_version": KIT_VERSION,
        "pairs": pairs,
        "report_version": REPORT_VERSION,
        "routines": routine_reports,
        "rules_version": RULES_VERSION,
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "by_code": dict(sorted(by_code.items())),
            "finding_count": len(findings),
            "routine_count": len(raw_routines),
        },
    }


def _require_contract(data):
    if not isinstance(data, dict):
        raise ContractError("snapshot must be a JSON object")
    version = data.get("contract_version", None)
    if version != CONTRACT_VERSION:
        raise ContractError(f"unsupported contract_version: {version!r}")
    if "routines" not in data or not isinstance(data["routines"], list):
        raise ContractError("routines must be a list")
    if "export" in data and not isinstance(data["export"], dict):
        raise ContractError("export must be an object")
    if "audit" in data and not isinstance(data["audit"], dict):
        raise ContractError("audit must be an object")


def _finding(code, reason, subjects=None, fields=None, detail="", blocks=True, severity=None):
    if severity is None:
        if code.startswith("malformed") or code == "snapshot_too_large":
            severity = "error"
        elif blocks:
            severity = "warning"
        else:
            severity = "info"
    return {
        "blocks_all_clear": blocks,
        "code": code,
        "detail": detail,
        "fields": sorted(fields or []),
        "reason": reason,
        "severity": severity,
        "subjects": sorted(subjects or []),
    }


def _check_keys(node, allowed, path, unknown):
    if not isinstance(node, dict):
        return
    for key in node:
        if key not in allowed:
            unknown.append(f"{path}.{key}" if path else key)


def _routine_label(routine, index):
    routine_id = routine.get("id")
    if isinstance(routine_id, str) and routine_id.strip() != "":
        return routine_id
    return f"index-{index}"


def _unknown_field_findings(data):
    unknown = []
    _check_keys(data, TOP_KEYS, "", unknown)
    export = data.get("export")
    if isinstance(export, dict):
        _check_keys(export, EXPORT_KEYS, "export", unknown)
        _check_keys(export.get("pagination"), PAGINATION_KEYS, "export.pagination", unknown)
    audit = data.get("audit")
    if isinstance(audit, dict):
        _check_keys(audit, AUDIT_KEYS, "audit", unknown)
        _check_keys(audit.get("window"), WINDOW_KEYS, "audit.window", unknown)
    routines = data.get("routines")
    if isinstance(routines, list):
        for index, routine in enumerate(routines):
            if not isinstance(routine, dict):
                continue
            label = _routine_label(routine, index)
            base = f"routine:{label}"
            _check_keys(routine, ROUTINE_KEYS, base, unknown)
            _check_keys(routine.get("identity"), IDENTITY_KEYS, f"{base}.identity", unknown)
            _check_keys(routine.get("target"), TARGET_KEYS, f"{base}.target", unknown)
            schedule = routine.get("schedule")
            _check_keys(schedule, SCHEDULE_KEYS, f"{base}.schedule", unknown)
            if isinstance(schedule, dict):
                _check_keys(schedule.get("window"), WINDOW_KEYS, f"{base}.schedule.window", unknown)
            _check_keys(routine.get("auth_recovery"), AUTH_KEYS, f"{base}.auth_recovery", unknown)
            notification = routine.get("notification")
            _check_keys(notification, NOTIFICATION_KEYS, f"{base}.notification", unknown)
            if isinstance(notification, dict) and isinstance(notification.get("events"), list):
                for event_index, event in enumerate(notification["events"]):
                    _check_keys(
                        event,
                        EVENT_KEYS,
                        f"{base}.notification.events[{event_index}]",
                        unknown,
                    )
            delivery = routine.get("delivery")
            _check_keys(delivery, DELIVERY_KEYS, f"{base}.delivery", unknown)
            if isinstance(delivery, dict):
                _check_keys(delivery.get("receipt"), RECEIPT_KEYS, f"{base}.delivery.receipt", unknown)
                if isinstance(delivery.get("attempts"), list):
                    for attempt_index, attempt in enumerate(delivery["attempts"]):
                        _check_keys(
                            attempt,
                            ATTEMPT_KEYS,
                            f"{base}.delivery.attempts[{attempt_index}]",
                            unknown,
                        )
            _check_keys(routine.get("deadline"), DEADLINE_KEYS, f"{base}.deadline", unknown)
            if isinstance(routine.get("runs"), list):
                for run_index, run in enumerate(routine["runs"]):
                    _check_keys(run, RUN_KEYS, f"{base}.runs[{run_index}]", unknown)
    if not unknown:
        return []
    return [
        _finding(
            "unknown_field",
            "unsupported_field",
            fields=sorted(set(unknown)),
        )
    ]


def _shape_findings(data):
    findings = []
    routines = data.get("routines")
    if not isinstance(routines, list):
        return findings
    for index, routine in enumerate(routines):
        if not isinstance(routine, dict):
            continue
        label = _routine_label(routine, index)
        base = f"routine:{label}"
        for key in ("identity", "target", "schedule", "auth_recovery", "notification", "delivery", "deadline"):
            if key in routine and routine[key] is not None and not isinstance(routine[key], dict):
                findings.append(
                    _finding(
                        "malformed_field",
                        "wrong_type",
                        subjects=[label] if not label.startswith("index-") else [],
                        fields=[f"{base}.{key}"],
                        severity="error",
                    )
                )
        notification = routine.get("notification")
        if isinstance(notification, dict) and "events" in notification and not isinstance(notification["events"], list):
            findings.append(
                _finding(
                    "malformed_field",
                    "wrong_type",
                    subjects=[label] if not str(label).startswith("index-") else [],
                    fields=[f"{base}.notification.events"],
                    severity="error",
                )
            )
        elif isinstance(notification, dict) and isinstance(notification.get("events"), list):
            for event_index, event in enumerate(notification["events"]):
                if not isinstance(event, dict):
                    findings.append(
                        _finding(
                            "malformed_field",
                            "wrong_type",
                            subjects=[label] if not str(label).startswith("index-") else [],
                            fields=[f"{base}.notification.events[{event_index}]"],
                            severity="error",
                        )
                    )
                    continue
                if "kind" in event and not isinstance(event.get("kind"), str):
                    findings.append(
                        _finding(
                            "malformed_field",
                            "wrong_type",
                            subjects=[label] if not str(label).startswith("index-") else [],
                            fields=[f"{base}.notification.events[{event_index}].kind"],
                            severity="error",
                        )
                    )
        delivery = routine.get("delivery")
        if isinstance(delivery, dict) and "attempts" in delivery and not isinstance(delivery["attempts"], list):
            findings.append(
                _finding(
                    "malformed_field",
                    "wrong_type",
                    subjects=[label] if not str(label).startswith("index-") else [],
                    fields=[f"{base}.delivery.attempts"],
                    severity="error",
                )
            )
        if "runs" in routine and routine["runs"] is not None and not isinstance(routine["runs"], list):
            findings.append(
                _finding(
                    "malformed_field",
                    "wrong_type",
                    subjects=[label] if not str(label).startswith("index-") else [],
                    fields=[f"{base}.runs"],
                    severity="error",
                )
            )
    return findings


def _coverage_findings(export):
    findings = []
    if export.get("coverage") != "complete":
        findings.append(_finding("coverage_unknown", "export_coverage_not_complete"))
    pagination = export.get("pagination")
    if not isinstance(pagination, dict) or pagination.get("complete") is not True:
        findings.append(_finding("coverage_unknown", "pagination_incomplete"))
    return findings


def _deadline_coverage_findings(export, audit):
    findings = []
    if export.get("deadline_coverage") != "complete":
        findings.append(_finding("deadline_boundary_missing", "deadline_coverage_not_complete"))
    if parse_aware(audit.get("as_of")) is None:
        findings.append(_finding("deadline_boundary_missing", "as_of_missing"))
    return findings


def _known(value):
    return isinstance(value, str) and value.strip() != "" and value.strip().lower() != "unknown"


def _group(routine, name):
    value = routine.get(name)
    return value if isinstance(value, dict) else {}


def _unknown_scope_fields(routine):
    missing = []
    for group, field in SCOPE_FIELDS:
        if not _known(_group(routine, group).get(field)):
            missing.append(f"{group}.{field}")
    return missing


def _valid_receipt(delivery):
    if not isinstance(delivery, dict):
        return False
    receipt = delivery.get("receipt")
    if not isinstance(receipt, dict):
        return False
    return _known(receipt.get("id")) and parse_aware(receipt.get("confirmed_at")) is not None


def _misleading_signals(routine):
    signals = set()
    delivery = routine.get("delivery")
    if isinstance(delivery, dict):
        last_alert = delivery.get("last_alert")
        if last_alert is True or (isinstance(last_alert, str) and last_alert.strip() != ""):
            signals.add("last_alert")
        if delivery.get("notify") is True:
            signals.add("notify")
        claimed = delivery.get("claimed")
        if isinstance(claimed, str) and claimed.strip().lower() in CLAIMED_DELIVERED:
            signals.add("claimed")
        state = delivery.get("state")
        if isinstance(state, str) and state.strip().lower() in CLAIMED_DELIVERED and not _valid_receipt(delivery):
            signals.add("state_delivered")
        if state == "confirmed" and not _valid_receipt(delivery):
            signals.add("state_confirmed")
        attempts = delivery.get("attempts")
        if isinstance(attempts, list):
            for attempt in attempts:
                if isinstance(attempt, dict) and attempt.get("result") in MISLEADING_RESULTS:
                    signals.add(attempt["result"])
    notification = routine.get("notification")
    if isinstance(notification, dict) and isinstance(notification.get("events"), list):
        for event in notification["events"]:
            if isinstance(event, dict):
                kind = event.get("kind")
                if isinstance(kind, str) and kind in MISLEADING_RESULTS | {"last_alert"}:
                    signals.add(kind)
    return sorted(signals)


def _delivery_status(routine):
    delivery = routine.get("delivery")
    notification = routine.get("notification")
    has_delivery = isinstance(delivery, dict)
    events = notification.get("events") if isinstance(notification, dict) else None
    has_events = isinstance(events, list) and len(events) > 0
    if not has_delivery and not has_events:
        return "not_applicable"
    if _valid_receipt(delivery):
        return "confirmed"
    if _misleading_signals(routine):
        return "not_delivered"
    state = delivery.get("state") if has_delivery else None
    attempts = delivery.get("attempts") if has_delivery else None
    if state == "pending":
        return "pending"
    if state == "attempted" or (isinstance(attempts, list) and attempts) or has_events:
        return "attempted"
    return "unknown"


def _idempotency_keys(routine):
    keys = []
    delivery = routine.get("delivery") if isinstance(routine.get("delivery"), dict) else {}
    notification = routine.get("notification") if isinstance(routine.get("notification"), dict) else {}
    for collection in (delivery.get("attempts"), notification.get("events")):
        if not isinstance(collection, list):
            continue
        for item in collection:
            if isinstance(item, dict) and _known(item.get("idempotency_key")):
                keys.append(item["idempotency_key"])
    return keys


def _audit_routine(routine, bounds, as_of, deadline_complete):
    findings = []
    routine_id = routine["id"]
    missing_scope = _unknown_scope_fields(routine)
    if missing_scope:
        findings.append(
            _finding(
                "scope_unknown",
                "missing_or_unknown_scope",
                subjects=[routine_id],
                fields=missing_scope,
            )
        )
    identity = _group(routine, "identity")
    if not _known(identity.get("account")) or not _known(identity.get("profile")):
        findings.append(
            _finding(
                "auth_applicability_unknown",
                "account_or_profile_unknown",
                subjects=[routine_id],
            )
        )
    schedule = resolve_schedule(routine.get("schedule"), bounds)
    if schedule["status"] != "resolved":
        findings.append(
            _finding(
                "schedule_unknown",
                schedule["reason"],
                subjects=[routine_id],
            )
        )
    status = _delivery_status(routine)
    signals = _misleading_signals(routine)
    if status == "not_delivered":
        findings.append(
            _finding(
                "delivery_not_confirmed",
                "signal_is_not_receipt",
                subjects=[routine_id],
                fields=signals,
                detail="receipt=absent",
            )
        )
    elif status == "pending":
        findings.append(
            _finding(
                "delivery_pending",
                "pending",
                subjects=[routine_id],
                blocks=False,
            )
        )
    elif status == "attempted":
        findings.append(
            _finding(
                "delivery_attempted",
                "attempted",
                subjects=[routine_id],
                blocks=False,
            )
        )
    elif status == "unknown":
        findings.append(
            _finding(
                "delivery_not_confirmed",
                "delivery_unknown",
                subjects=[routine_id],
            )
        )
    notification = routine.get("notification") if isinstance(routine.get("notification"), dict) else None
    delivery = routine.get("delivery") if isinstance(routine.get("delivery"), dict) else None
    if notification is not None or delivery is not None:
        owner = notification.get("owner") if notification is not None else None
        if not _known(owner):
            findings.append(
                _finding(
                    "notification_owner_missing",
                    "owner_missing",
                    subjects=[routine_id],
                )
            )
    counts = {}
    for key in _idempotency_keys(routine):
        counts[key] = counts.get(key, 0) + 1
    receipt_present = _valid_receipt(delivery)
    for key in sorted(counts):
        if counts[key] >= 2:
            findings.append(
                _finding(
                    "repeated_notification",
                    "duplicate_idempotency_key",
                    subjects=[routine_id],
                    detail=f"idempotency_key={key}; receipt={'present' if receipt_present else 'absent'}",
                    blocks=not receipt_present,
                )
            )
    runs = routine.get("runs")
    if isinstance(runs, list):
        for run in runs:
            if not isinstance(run, dict):
                findings.append(
                    _finding(
                        "malformed_field",
                        "wrong_type",
                        subjects=[routine_id],
                        fields=[f"routine:{routine_id}.runs"],
                        severity="error",
                    )
                )
                continue
            scheduled_at = run.get("scheduled_at")
            parsed = parse_aware(scheduled_at)
            run_status = run.get("status")
            if parsed is None or not isinstance(scheduled_at, str):
                findings.append(
                    _finding(
                        "run_status_unknown",
                        "timestamp_tz_missing",
                        subjects=[routine_id],
                        detail=f"scheduled_at={scheduled_at}",
                    )
                )
                continue
            if run_status == "missed":
                findings.append(
                    _finding(
                        "missed_run",
                        "missed",
                        subjects=[routine_id],
                        detail=f"scheduled_at={scheduled_at}",
                    )
                )
            elif not isinstance(run_status, str) or run_status not in {"ran", "skipped"}:
                findings.append(
                    _finding(
                        "run_status_unknown",
                        "status_unknown",
                        subjects=[routine_id],
                        detail=f"scheduled_at={scheduled_at}",
                    )
                )
    deadline = routine.get("deadline")
    if deadline_complete and (not isinstance(deadline, dict) or "at" not in deadline):
        findings.append(
            _finding(
                "deadline_boundary_missing",
                "deadline_missing",
                subjects=[routine_id],
            )
        )
    elif isinstance(deadline, dict) and "at" in deadline:
        parsed_deadline = parse_aware(deadline.get("at"))
        if parsed_deadline is None:
            findings.append(
                _finding(
                    "deadline_boundary_missing",
                    "deadline_tz_missing",
                    subjects=[routine_id],
                    detail=f"deadline={deadline.get('at')}",
                )
            )
        elif as_of is not None and as_of > parsed_deadline and status != "confirmed":
            findings.append(
                _finding(
                    "deadline_exceeded",
                    "deadline_passed_without_receipt",
                    subjects=[routine_id],
                    detail=f"deadline={deadline.get('at')}",
                )
            )
    summary = {
        "delivery_status": status,
        "id": routine_id,
        "schedule_status": "resolved" if schedule["status"] == "resolved" else "unknown",
        "scope_status": "unknown" if missing_scope else "known",
    }
    return findings, schedule, summary


def _policy(routine):
    auth = routine.get("auth_recovery")
    if not isinstance(auth, dict):
        return None
    policy = auth.get("policy")
    if not _known(policy):
        return None
    return policy


def _identity_known(routine):
    identity = _group(routine, "identity")
    return _known(identity.get("account")) and _known(identity.get("profile"))


def _identity_key(routine):
    identity = _group(routine, "identity")
    return (identity.get("account"), identity.get("profile"))


def _scope_key(routine):
    values = []
    for group, field in SCOPE_FIELDS:
        values.append(_group(routine, group).get(field))
    return tuple(values)


def _target_note(left, right, duplicate_status):
    if duplicate_status != "not_duplicate":
        return ""
    left_target = _group(left, "target")
    right_target = _group(right, "target")
    if (
        _known(left_target.get("source"))
        and left_target.get("source") == right_target.get("source")
        and _known(left_target.get("deliverable"))
        and _known(right_target.get("deliverable"))
        and left_target.get("deliverable") != right_target.get("deliverable")
    ):
        return "different_deliverable"
    if (
        _known(left_target.get("resource_id"))
        and left_target.get("resource_id") == right_target.get("resource_id")
        and _known(left_target.get("topic"))
        and _known(right_target.get("topic"))
        and left_target.get("topic") != right_target.get("topic")
    ):
        return "different_topic"
    return ""


def _compare(left, right, resolved):
    left_missing = _unknown_scope_fields(left)
    right_missing = _unknown_scope_fields(right)
    if left_missing or right_missing:
        duplicate = "unknown"
    elif _scope_key(left) == _scope_key(right):
        duplicate = "candidate"
    else:
        duplicate = "not_duplicate"
    left_schedule = resolved[left["id"]]
    right_schedule = resolved[right["id"]]
    if left_schedule["status"] != "resolved" or right_schedule["status"] != "resolved":
        schedule = "unknown"
    elif overlaps(left_schedule, right_schedule):
        schedule = "collision"
    else:
        schedule = "no_collision"
    if not _identity_known(left) or not _identity_known(right):
        auth_policy = "unknown"
    elif _identity_key(left) != _identity_key(right):
        auth_policy = "not_applicable"
    else:
        left_policy = _policy(left)
        right_policy = _policy(right)
        if left_policy not in KNOWN_POLICIES or right_policy not in KNOWN_POLICIES:
            auth_policy = "unknown"
        elif left_policy != right_policy:
            auth_policy = "conflict"
        else:
            auth_policy = "no_conflict"
    return {
        "auth_policy": auth_policy,
        "duplicate": duplicate,
        "routines": [left["id"], right["id"]],
        "schedule": schedule,
        "target_note": _target_note(left, right, duplicate),
    }


def _pair_findings(routines, resolved):
    findings = []
    for index, left in enumerate(routines):
        for right in routines[index + 1 :]:
            compared = _compare(left, right, resolved)
            if compared["duplicate"] == "candidate":
                findings.append(
                    _finding(
                        "duplicate_candidate",
                        "same_known_scope",
                        subjects=[left["id"], right["id"]],
                    )
                )
            if compared["schedule"] == "collision":
                findings.append(
                    _finding(
                        "schedule_collision",
                        "shared_time",
                        subjects=[left["id"], right["id"]],
                        detail="collision_is_not_duplicate_function",
                    )
                )
            if compared["auth_policy"] == "conflict":
                findings.append(
                    _finding(
                        "auth_policy_conflict",
                        "conflicting_policies",
                        subjects=[left["id"], right["id"]],
                        fields=[_policy(left), _policy(right)],
                    )
                )
            elif compared["auth_policy"] == "unknown" and _identity_known(left) and _identity_known(right):
                findings.append(
                    _finding(
                        "auth_applicability_unknown",
                        "policy_unsupported",
                        subjects=[left["id"], right["id"]],
                    )
                )
    return findings


def _pairs(routines, resolved):
    pairs = []
    for index, left in enumerate(routines):
        for right in routines[index + 1 :]:
            pair = _compare(left, right, resolved)
            pair["routines"] = sorted(pair["routines"])
            pairs.append(pair)
    pairs.sort(key=lambda item: item["routines"])
    return pairs
