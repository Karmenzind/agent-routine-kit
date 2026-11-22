"""Behavior tests for the offline routine-snapshot audit."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from agent_routine_kit.audit import audit_snapshot
from agent_routine_kit.errors import ContractError
from agent_routine_kit.report import render_json, render_text
from agent_routine_kit.versions import (
    CONTRACT_VERSION,
    REPORT_VERSION,
    RULES_VERSION,
    SCHEMA_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def envelope(routines, **changes):
    data = {
        "contract_version": "1",
        "export": {
            "source": "manual-normalized",
            "coverage": "complete",
            "pagination": {"complete": True},
            "deadline_coverage": "complete",
            "exported_at": "2026-11-22T00:00:00Z",
        },
        "audit": {
            "as_of": "2026-11-22T02:00:00Z",
            "window": {
                "start": "2026-11-22T00:00:00Z",
                "end": "2026-11-23T00:00:00Z",
            },
        },
        "routines": routines,
    }
    for key, value in changes.items():
        if key in {"export", "audit"}:
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return data


def routine(routine_id, **overrides):
    item = {
        "id": routine_id,
        "name": f"synthetic name {routine_id}",
        "identity": {
            "account": "synthetic-account-alpha",
            "cli": "synthetic-cli-alpha",
            "profile": "synthetic-profile-alpha",
        },
        "target": {
            "resource_id": f"synthetic-resource-{routine_id}",
            "topic": f"synthetic-topic-{routine_id}",
            "action": "inspect",
            "source": f"synthetic-source-{routine_id}",
            "deliverable": f"synthetic-deliverable-{routine_id}",
            "output_scope": f"synthetic-output-{routine_id}",
        },
        "schedule": {
            "kind": "instants",
            "scope": "one-shot",
            "instants": ["2026-11-22T01:00:00Z"],
        },
        "auth_recovery": {"policy": "no-login"},
        "deadline": {"at": "2026-11-22T06:00:00Z"},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(item.get(key), dict):
            item[key] = {**item[key], **value}
        else:
            item[key] = value
    return item


def codes(report):
    return [finding["code"] for finding in report["findings"]]


def pair_of(report, left, right):
    wanted = tuple(sorted((left, right)))
    for pair in report["pairs"]:
        if tuple(pair["routines"]) == wanted:
            return pair
    raise AssertionError(f"missing pair {wanted}")


class ContractTests(unittest.TestCase):
    def test_healthy_snapshot_is_all_clear_and_versioned(self):
        report = audit_snapshot(json.loads((FIXTURES / "healthy_minimal.json").read_text()))
        self.assertTrue(report["all_clear"])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertEqual(report["schema_version"], SCHEMA_VERSION)
        self.assertEqual(report["rules_version"], RULES_VERSION)
        self.assertEqual(report["report_version"], REPORT_VERSION)
        self.assertEqual(report["coverage"]["status"], "complete")
        self.assertEqual(report["routines"][0]["delivery_status"], "not_applicable")
        self.assertEqual(report["routines"][0]["schedule_status"], "resolved")
        self.assertEqual(report["routines"][0]["scope_status"], "known")

    def test_unsupported_contract_version_is_rejected(self):
        with self.assertRaises(ContractError):
            audit_snapshot({"contract_version": "999", "routines": []})

    def test_missing_contract_version_is_rejected(self):
        with self.assertRaises(ContractError):
            audit_snapshot({"routines": []})

    def test_non_object_snapshot_is_rejected(self):
        with self.assertRaises(ContractError):
            audit_snapshot([])

    def test_unknown_field_blocks_all_clear(self):
        data = envelope([routine("synthetic-routine-1")])
        data["unexpected_note"] = "synthetic"
        report = audit_snapshot(data)
        finding = next(item for item in report["findings"] if item["code"] == "unknown_field")
        self.assertIn("unexpected_note", finding["fields"])
        self.assertTrue(finding["blocks_all_clear"])
        self.assertFalse(report["all_clear"])

    def test_malformed_routine_without_id_is_reported(self):
        item = routine("synthetic-routine-1")
        del item["id"]
        report = audit_snapshot(envelope([item]))
        self.assertIn("malformed_routine", codes(report))
        self.assertFalse(report["all_clear"])

    def test_audit_does_not_mutate_input(self):
        data = envelope([routine("synthetic-routine-1")])
        original = copy.deepcopy(data)
        audit_snapshot(data)
        self.assertEqual(data, original)

    def test_reordering_input_does_not_change_report_bytes(self):
        first = routine("synthetic-b", schedule={"instants": ["2026-11-22T02:00:00Z"]})
        second = routine("synthetic-a")
        left = audit_snapshot(envelope([first, second]))
        right = audit_snapshot(envelope([second, first]))
        self.assertEqual(render_json(left), render_json(right))

    def test_human_output_lists_the_same_findings_as_json(self):
        data = envelope([routine("synthetic-routine-1")])
        data["export"]["coverage"] = "partial"
        report = audit_snapshot(data)
        text = render_text(report)
        parsed = render_json(report)
        self.assertEqual(json.loads(parsed), report)
        listed = [line.split()[1] for line in text.splitlines() if line.startswith("finding: ")]
        self.assertEqual(listed, codes(report))
        self.assertIn(f"all_clear: {str(report['all_clear']).lower()}", text)
        self.assertIn("rules_version: 1", text)


class DuplicateTests(unittest.TestCase):
    def test_equal_scope_is_duplicate_candidate_even_when_names_and_schedules_differ(self):
        report = audit_snapshot(json.loads((FIXTURES / "duplicate_candidate.json").read_text()))
        pair = pair_of(report, "synthetic-dup-a", "synthetic-dup-b")
        self.assertEqual(pair["duplicate"], "candidate")
        self.assertEqual(pair["schedule"], "no_collision")
        self.assertIn("duplicate_candidate", codes(report))
        self.assertFalse(report["all_clear"])
        self.assertNotEqual(report["routines"][0]["id"], report["routines"][1]["id"])

    def test_same_resource_with_distinct_topic_is_not_duplicate(self):
        report = audit_snapshot(json.loads((FIXTURES / "not_duplicates.json").read_text()))
        pair = pair_of(report, "synthetic-topic-a", "synthetic-topic-b")
        self.assertEqual(pair["duplicate"], "not_duplicate")
        self.assertNotIn("duplicate_candidate", codes(report))

    def test_same_source_with_different_deliverable_is_not_duplicate(self):
        report = audit_snapshot(json.loads((FIXTURES / "not_duplicates.json").read_text()))
        pair = pair_of(report, "synthetic-topic-a", "synthetic-deliverable-c")
        self.assertEqual(pair["duplicate"], "not_duplicate")
        self.assertEqual(pair["target_note"], "different_deliverable")

    def test_equal_names_do_not_create_a_duplicate(self):
        left = routine("synthetic-name-a", name="shared synthetic label")
        right = routine("synthetic-name-b", name="shared synthetic label")
        report = audit_snapshot(envelope([left, right]))
        self.assertEqual(pair_of(report, "synthetic-name-a", "synthetic-name-b")["duplicate"], "not_duplicate")

    def test_missing_scope_is_unknown_not_safe(self):
        left = routine("synthetic-unknown-a", target={"topic": None})
        right = routine(
            "synthetic-unknown-b",
            target={
                "resource_id": "synthetic-resource-synthetic-unknown-a",
                "topic": None,
            },
        )
        report = audit_snapshot(envelope([left, right]))
        pair = pair_of(report, "synthetic-unknown-a", "synthetic-unknown-b")
        self.assertEqual(pair["duplicate"], "unknown")
        self.assertNotEqual(pair["duplicate"], "candidate")
        self.assertNotEqual(pair["duplicate"], "not_duplicate")
        finding = next(item for item in report["findings"] if item["code"] == "scope_unknown")
        self.assertIn("target.topic", finding["fields"])
        self.assertTrue(finding["blocks_all_clear"])
        self.assertFalse(report["all_clear"])


class AuthTests(unittest.TestCase):
    def test_auto_login_versus_no_login_conflicts_for_known_identity(self):
        report = audit_snapshot(json.loads((FIXTURES / "auth_maintenance_conflict.json").read_text()))
        pair = pair_of(report, "synthetic-auth-a", "synthetic-auth-b")
        self.assertEqual(pair["auth_policy"], "conflict")
        self.assertEqual(pair["duplicate"], "not_duplicate")
        finding = next(item for item in report["findings"] if item["code"] == "auth_policy_conflict")
        self.assertEqual(finding["subjects"], ["synthetic-auth-a", "synthetic-auth-b"])
        self.assertCountEqual(finding["fields"], ["auto-login", "no-login"])
        self.assertTrue(finding["blocks_all_clear"])
        self.assertFalse(report["all_clear"])
        self.assertNotIn("selected_policy", json.dumps(report))

    def test_unknown_profile_does_not_assume_identity_or_pick_login(self):
        left = routine("synthetic-auth-unknown", identity={"profile": None}, auth_recovery={"policy": "auto-login"})
        right = routine("synthetic-auth-known", auth_recovery={"policy": "no-login"})
        report = audit_snapshot(envelope([left, right]))
        pair = pair_of(report, "synthetic-auth-unknown", "synthetic-auth-known")
        self.assertEqual(pair["auth_policy"], "unknown")
        self.assertNotIn("auth_policy_conflict", codes(report))
        self.assertIn("auth_applicability_unknown", codes(report))
        self.assertNotIn("selected_policy", json.dumps(report))
        self.assertFalse(report["all_clear"])

    def test_distinct_known_identities_are_not_an_auth_conflict(self):
        left = routine("synthetic-auth-left", auth_recovery={"policy": "auto-login"})
        right = routine(
            "synthetic-auth-right",
            identity={"account": "synthetic-account-beta", "profile": "synthetic-profile-beta"},
            auth_recovery={"policy": "no-login"},
            schedule={"instants": ["2026-11-22T03:00:00Z"]},
        )
        report = audit_snapshot(envelope([left, right]))
        self.assertEqual(
            pair_of(report, "synthetic-auth-left", "synthetic-auth-right")["auth_policy"],
            "not_applicable",
        )
        self.assertNotIn("auth_policy_conflict", codes(report))
        self.assertTrue(report["all_clear"])


class ScheduleTests(unittest.TestCase):
    def test_cross_zone_instants_that_match_in_utc_collide_without_being_duplicates(self):
        report = audit_snapshot(json.loads((FIXTURES / "schedule_overlap_timezones.json").read_text()))
        pair = pair_of(report, "synthetic-schedule-sg", "synthetic-schedule-utc")
        self.assertEqual(pair["schedule"], "collision")
        self.assertEqual(pair["duplicate"], "not_duplicate")
        self.assertIn("schedule_collision", codes(report))
        self.assertNotIn("duplicate_candidate", codes(report))

    def test_different_local_times_do_not_collide(self):
        left = routine(
            "synthetic-sg",
            schedule={
                "kind": "cron",
                "scope": "morning",
                "expression": "0 9 * * *",
                "timezone": "Asia/Singapore",
            },
        )
        right = routine(
            "synthetic-la",
            schedule={
                "kind": "cron",
                "scope": "morning",
                "expression": "0 9 * * *",
                "timezone": "America/Los_Angeles",
            },
        )
        report = audit_snapshot(envelope([left, right]))
        self.assertEqual(pair_of(report, "synthetic-sg", "synthetic-la")["schedule"], "no_collision")
        self.assertNotIn("schedule_collision", codes(report))

    def test_missing_timezone_is_unknown_not_no_collision(self):
        left = routine(
            "synthetic-missing-tz",
            schedule={"kind": "cron", "scope": "morning", "expression": "0 9 * * *"},
        )
        right = routine(
            "synthetic-utc",
            schedule={"kind": "cron", "scope": "evening", "expression": "0 21 * * *", "timezone": "UTC"},
        )
        report = audit_snapshot(envelope([left, right]))
        pair = pair_of(report, "synthetic-missing-tz", "synthetic-utc")
        self.assertEqual(pair["schedule"], "unknown")
        self.assertNotEqual(pair["schedule"], "no_collision")
        self.assertIn("schedule_unknown", codes(report))
        self.assertFalse(report["all_clear"])

    def test_unsupported_cron_is_unknown_not_no_collision(self):
        report = audit_snapshot(json.loads((FIXTURES / "schedule_unknown_cron.json").read_text()))
        pair = pair_of(report, "synthetic-step-cron", "synthetic-plain-cron")
        self.assertEqual(pair["schedule"], "unknown")
        self.assertNotIn("schedule_collision", codes(report))
        finding = next(item for item in report["findings"] if item["code"] == "schedule_unknown")
        self.assertEqual(finding["reason"], "cron_unsupported")
        self.assertFalse(report["all_clear"])

    def test_dst_ambiguous_local_time_is_unknown(self):
        left = routine(
            "synthetic-dst-fold",
            schedule={
                "kind": "cron",
                "scope": "fold-hour",
                "expression": "30 1 * * *",
                "timezone": "America/New_York",
            },
        )
        right = routine(
            "synthetic-dst-other",
            schedule={"kind": "instants", "scope": "other", "instants": ["2026-11-01T18:00:00Z"]},
        )
        report = audit_snapshot(
            envelope(
                [left, right],
                audit={
                    "as_of": "2026-11-01T00:00:00Z",
                    "window": {"start": "2026-11-01T00:00:00Z", "end": "2026-11-02T00:00:00Z"},
                },
            )
        )
        self.assertEqual(pair_of(report, "synthetic-dst-fold", "synthetic-dst-other")["schedule"], "unknown")
        reasons = [item["reason"] for item in report["findings"] if item["code"] == "schedule_unknown"]
        self.assertIn("dst_semantics", reasons)

    def test_dst_gap_is_unknown(self):
        item = routine(
            "synthetic-dst-gap",
            schedule={
                "kind": "cron",
                "scope": "gap-hour",
                "expression": "30 2 * * *",
                "timezone": "America/New_York",
            },
        )
        report = audit_snapshot(
            envelope(
                [item],
                audit={
                    "as_of": "2026-03-08T00:00:00Z",
                    "window": {"start": "2026-03-08T00:00:00Z", "end": "2026-03-09T00:00:00Z"},
                },
            )
        )
        self.assertEqual(report["routines"][0]["schedule_status"], "unknown")
        reasons = [item["reason"] for item in report["findings"] if item["code"] == "schedule_unknown"]
        self.assertIn("dst_semantics", reasons)

    def test_clear_local_time_on_a_dst_day_still_resolves(self):
        item = routine(
            "synthetic-dst-safe",
            schedule={
                "kind": "cron",
                "scope": "morning",
                "expression": "0 9 * * *",
                "timezone": "America/New_York",
            },
        )
        report = audit_snapshot(
            envelope(
                [item],
                audit={
                    "as_of": "2026-11-01T00:00:00Z",
                    "window": {"start": "2026-11-01T00:00:00Z", "end": "2026-11-02T00:00:00Z"},
                },
            )
        )
        self.assertEqual(report["routines"][0]["schedule_status"], "resolved")
        self.assertNotIn("schedule_unknown", codes(report))

    def test_flexible_window_is_unknown_even_without_overlap(self):
        left = routine(
            "synthetic-flex",
            schedule={
                "kind": "window",
                "scope": "flex",
                "flexible": True,
                "window": {"start": "2026-11-22T01:00:00Z", "end": "2026-11-22T02:00:00Z"},
            },
        )
        right = routine(
            "synthetic-later",
            schedule={"kind": "instants", "scope": "later", "instants": ["2026-11-22T05:00:00Z"]},
        )
        report = audit_snapshot(envelope([left, right]))
        self.assertEqual(pair_of(report, "synthetic-flex", "synthetic-later")["schedule"], "unknown")
        self.assertNotEqual(pair_of(report, "synthetic-flex", "synthetic-later")["schedule"], "no_collision")

    def test_touching_windows_do_not_collide(self):
        left = routine(
            "synthetic-window-a",
            schedule={
                "kind": "window",
                "scope": "early",
                "flexible": False,
                "window": {"start": "2026-11-22T01:00:00Z", "end": "2026-11-22T02:00:00Z"},
            },
        )
        right = routine(
            "synthetic-window-b",
            schedule={
                "kind": "window",
                "scope": "later",
                "flexible": False,
                "window": {"start": "2026-11-22T02:00:00Z", "end": "2026-11-22T03:00:00Z"},
            },
        )
        report = audit_snapshot(envelope([left, right]))
        self.assertEqual(pair_of(report, "synthetic-window-a", "synthetic-window-b")["schedule"], "no_collision")

    def test_missing_audit_window_does_not_claim_no_collision(self):
        data = envelope([routine("synthetic-routine-1"), routine("synthetic-routine-2")])
        del data["audit"]["window"]
        report = audit_snapshot(data)
        self.assertEqual(pair_of(report, "synthetic-routine-1", "synthetic-routine-2")["schedule"], "unknown")
        self.assertFalse(report["all_clear"])


class DeliveryTests(unittest.TestCase):
    def test_false_delivery_signals_are_not_confirmed(self):
        report = audit_snapshot(json.loads((FIXTURES / "delivery_false_signals.json").read_text()))
        by_id = {item["id"]: item["delivery_status"] for item in report["routines"]}
        self.assertEqual(by_id["synthetic-pending"], "pending")
        self.assertEqual(by_id["synthetic-http-start"], "not_delivered")
        self.assertEqual(by_id["synthetic-exit-zero"], "not_delivered")
        self.assertEqual(by_id["synthetic-last-alert"], "not_delivered")
        self.assertEqual(by_id["synthetic-receipt"], "confirmed")
        blocking = [
            item["subjects"][0]
            for item in report["findings"]
            if item["code"] == "delivery_not_confirmed" and item["blocks_all_clear"]
        ]
        self.assertCountEqual(
            blocking,
            ["synthetic-http-start", "synthetic-exit-zero", "synthetic-last-alert"],
        )
        self.assertNotIn("synthetic-receipt", blocking)
        self.assertNotIn("synthetic-pending", blocking)
        self.assertFalse(report["all_clear"])

    def test_retry_key_without_receipt_is_not_delivery(self):
        report = audit_snapshot(json.loads((FIXTURES / "repeated_notification.json").read_text()))
        finding = next(item for item in report["findings"] if item["code"] == "repeated_notification")
        self.assertIn("synthetic-key-1", finding["detail"])
        self.assertTrue(finding["blocks_all_clear"])
        self.assertEqual(report["routines"][0]["delivery_status"], "not_delivered")
        self.assertFalse(report["all_clear"])

    def test_retry_with_real_receipt_stays_confirmed(self):
        item = routine(
            "synthetic-retry-confirmed",
            notification={"owner": "synthetic-owner-a"},
            delivery={
                "state": "attempted",
                "last_alert": True,
                "attempts": [
                    {"at": "2026-11-22T01:00:00Z", "result": "started", "idempotency_key": "synthetic-key-2"},
                    {"at": "2026-11-22T01:05:00Z", "result": "http_200", "idempotency_key": "synthetic-key-2"},
                ],
                "receipt": {"id": "synthetic-receipt-2", "confirmed_at": "2026-11-22T01:06:00Z"},
            },
        )
        report = audit_snapshot(envelope([item]))
        self.assertEqual(report["routines"][0]["delivery_status"], "confirmed")
        finding = next(item for item in report["findings"] if item["code"] == "repeated_notification")
        self.assertFalse(finding["blocks_all_clear"])
        self.assertNotIn("delivery_not_confirmed", codes(report))

    def test_missing_notification_owner_is_explicit_risk(self):
        item = routine(
            "synthetic-unowned",
            delivery={"state": "pending"},
        )
        report = audit_snapshot(envelope([item]))
        finding = next(item for item in report["findings"] if item["code"] == "notification_owner_missing")
        self.assertTrue(finding["blocks_all_clear"])
        self.assertEqual(report["routines"][0]["delivery_status"], "pending")
        self.assertFalse(report["all_clear"])

    def test_missed_run_uses_explicit_timestamp(self):
        report = audit_snapshot(json.loads((FIXTURES / "missed_run.json").read_text()))
        finding = next(item for item in report["findings"] if item["code"] == "missed_run")
        self.assertIn("2026-11-22T01:00:00Z", finding["detail"])
        self.assertTrue(finding["blocks_all_clear"])
        self.assertFalse(report["all_clear"])

    def test_deadline_compares_real_instants_across_zones(self):
        report = audit_snapshot(json.loads((FIXTURES / "deadline_timezone.json").read_text()))
        self.assertIn("deadline_exceeded", codes(report))
        self.assertFalse(report["all_clear"])

    def test_deadline_ahead_of_as_of_is_not_exceeded(self):
        item = routine("synthetic-deadline-ok", deadline={"at": "2026-11-22T10:00:00+08:00"})
        report = audit_snapshot(
            envelope([item], audit={"as_of": "2026-11-22T01:30:00Z", "window": {
                "start": "2026-11-22T00:00:00Z",
                "end": "2026-11-23T00:00:00Z",
            }})
        )
        self.assertNotIn("deadline_exceeded", codes(report))
        self.assertTrue(report["all_clear"])

    def test_naive_deadline_blocks_all_clear(self):
        item = routine("synthetic-naive-deadline", deadline={"at": "2026-11-22T10:00:00"})
        report = audit_snapshot(envelope([item]))
        self.assertIn("deadline_boundary_missing", codes(report))
        self.assertFalse(report["all_clear"])

    def test_incomplete_coverage_prevents_all_clear(self):
        report = audit_snapshot(json.loads((FIXTURES / "coverage_incomplete.json").read_text()))
        reasons = [item["reason"] for item in report["findings"] if item["code"] == "coverage_unknown"]
        self.assertIn("export_coverage_not_complete", reasons)
        self.assertIn("pagination_incomplete", reasons)
        self.assertEqual(report["coverage"]["status"], "unknown")
        self.assertFalse(report["all_clear"])
        self.assertGreater(report["summary"]["finding_count"], 0)

    def test_missing_deadline_coverage_prevents_all_clear(self):
        data = envelope([routine("synthetic-routine-1")])
        del data["export"]["deadline_coverage"]
        report = audit_snapshot(data)
        self.assertIn("deadline_boundary_missing", codes(report))
        self.assertFalse(report["all_clear"])

    def test_snapshot_over_routine_limit_does_not_claim_no_duplicates(self):
        routines = [routine(f"synthetic-limit-{index}") for index in range(101)]
        report = audit_snapshot(envelope(routines))
        self.assertIn("snapshot_too_large", codes(report))
        self.assertEqual(report["pairs"], [])
        self.assertNotIn("duplicate_candidate", codes(report))
        self.assertFalse(report["all_clear"])


if __name__ == "__main__":
    unittest.main()
