"""CLI tests for the local read-only audit command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def run_audit(snapshot, *args, cwd=None):
    command = [sys.executable, "-m", "agent_routine_kit", "audit", str(snapshot), *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_healthy_fixture_exits_zero_and_prints_json(self):
        result = run_audit(FIXTURES / "healthy_minimal.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["all_clear"])
        self.assertEqual(result.stderr, "")

    def test_auth_conflict_exits_one_and_both_formats_agree(self):
        result = run_audit(FIXTURES / "auth_maintenance_conflict.json", "--format", "both")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        listed = [line.split()[1] for line in result.stderr.splitlines() if line.startswith("finding: ")]
        self.assertEqual(listed, [item["code"] for item in report["findings"]])
        self.assertIn("auth_policy_conflict", listed)
        self.assertIn("all_clear: false", result.stderr)

    def test_bad_json_exits_two(self):
        result = run_audit(FIXTURES / "not_json.txt")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_unsupported_contract_exits_two(self):
        result = run_audit(FIXTURES / "unsupported_contract.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("contract_version", result.stderr)

    def test_output_flag_writes_only_the_requested_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "report.json"
            result = run_audit(
                FIXTURES / "healthy_minimal.json",
                "--format",
                "text",
                "--output",
                str(destination),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [destination])
            report = json.loads(destination.read_text())
            self.assertTrue(report["all_clear"])
            self.assertIn("all_clear: true", result.stdout)

    def test_missing_snapshot_exits_two(self):
        result = run_audit(ROOT / "fixtures" / "does-not-exist.json")
        self.assertEqual(result.returncode, 2)

    def test_omitted_routines_exits_two_without_a_success_report(self):
        data = json.loads((FIXTURES / "healthy_minimal.json").read_text())
        del data["routines"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            payload = json.dumps(data).encode("utf-8")
            path.write_bytes(payload)
            result = run_audit(path)
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("routines", result.stderr)
            self.assertNotIn("all_clear", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_wrong_type_routines_still_exits_two_without_a_success_report(self):
        data = json.loads((FIXTURES / "healthy_minimal.json").read_text())
        data["routines"] = {}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = run_audit(path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("routines", result.stderr)

    def test_output_same_path_is_rejected_and_bytes_survive(self):
        self._assert_snapshot_output_rejected(lambda directory, source: source)

    def test_output_resolved_alias_is_rejected_and_bytes_survive(self):
        def alias(directory, source):
            nested = directory / "nested"
            nested.mkdir()
            return nested / ".." / source.name

        self._assert_snapshot_output_rejected(alias)

    def test_output_relative_and_absolute_alias_is_rejected_and_bytes_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, payload = self._snapshot_copy(directory)
            result = run_audit(Path(source.name), "--output", str(source.resolve()), cwd=directory)
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)

    def test_output_symlink_is_rejected_and_bytes_survive(self):
        def alias(directory, source):
            link = directory / "linked-snapshot.json"
            link.symlink_to(source)
            return link

        self._assert_snapshot_output_rejected(alias)

    def test_output_hardlink_is_rejected_and_bytes_survive(self):
        def alias(directory, source):
            link = directory / "hard-snapshot.json"
            os.link(source, link)
            return link

        self._assert_snapshot_output_rejected(alias)

    def test_output_alias_swap_before_open_preserves_snapshot(self):
        for label, swap in (
            ("hardlink", self._swap_in_hardlink),
            ("symlink", self._swap_in_symlink),
        ):
            with self.subTest(label):
                self._assert_swapped_alias_rejected(swap)

    def test_repointed_input_symlink_does_not_truncate_opened_snapshot(self):
        import agent_routine_kit.cli as cli

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            content_a = (FIXTURES / "healthy_minimal.json").read_bytes()
            content_b = content_a.replace(
                b'"synthetic-routine-1"',
                b'"synthetic-routine-b"',
                1,
            )
            file_a = directory / "snapshot-a.json"
            file_b = directory / "snapshot-b.json"
            file_a.write_bytes(content_a)
            file_b.write_bytes(content_b)
            link = directory / "current.json"
            link.symlink_to(file_a)
            real_audit = cli.audit_snapshot
            seen = {}

            def audit_then_repoint(data):
                seen["data"] = data
                link.unlink()
                link.symlink_to(file_b)
                seen["repointed"] = True
                return real_audit(data)

            cli.audit_snapshot = audit_then_repoint
            stdout, stderr = StringIO(), StringIO()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = cli.main(["audit", str(link), "--output", str(file_a)])
            finally:
                cli.audit_snapshot = real_audit
            self.assertEqual(seen.get("data"), json.loads(content_a))
            self.assertTrue(seen.get("repointed"))
            self.assertEqual(link.resolve(), file_b.resolve())
            self.assertEqual(file_a.read_bytes(), content_a)
            self.assertEqual(file_b.read_bytes(), content_b)
            self.assertEqual(code, 2, stderr.getvalue())
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_output_identity_oserror_fails_closed_without_truncating(self):
        for label, patch in (
            ("resolve", self._resolve_raises),
            ("samefile", self._samefile_raises),
            ("opened file", self._fstat_raises),
        ):
            with self.subTest(label):
                self._assert_identity_failure_writes_nothing(patch)

    def test_distinct_output_still_writes_a_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, payload = self._snapshot_copy(directory)
            destination = directory / "report.json"
            result = run_audit(source, "--output", str(destination))
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(destination.is_file())
            self.assertTrue(json.loads(destination.read_text(encoding="utf-8"))["all_clear"])

    def test_relative_timezone_exits_one_with_a_report(self):
        item = {
            "id": "synthetic-bad-zone",
            "name": "synthetic bad zone",
            "identity": {
                "account": "synthetic-account-alpha",
                "cli": "synthetic-cli-alpha",
                "profile": "synthetic-profile-alpha",
            },
            "target": {
                "resource_id": "synthetic-resource-zone",
                "topic": "synthetic-topic-zone",
                "action": "inspect",
                "source": "synthetic-source-zone",
                "deliverable": "synthetic-deliverable-zone",
                "output_scope": "synthetic-output-zone",
            },
            "schedule": {
                "kind": "cron",
                "scope": "daily",
                "expression": "0 1 * * *",
                "timezone": "A/../B",
            },
            "auth_recovery": {"policy": "no-login"},
            "deadline": {"at": "2026-11-22T06:00:00Z"},
        }
        other = json.loads(json.dumps(item))
        other["id"] = "synthetic-utc-zone"
        other["schedule"] = {
            "kind": "cron",
            "scope": "daily",
            "expression": "0 9 * * *",
            "timezone": "UTC",
        }
        data = json.loads((FIXTURES / "healthy_minimal.json").read_text())
        data["routines"] = [item, other]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = run_audit(path)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["all_clear"])
        finding = next(
            entry
            for entry in report["findings"]
            if entry["code"] == "schedule_unknown" and entry["subjects"] == ["synthetic-bad-zone"]
        )
        self.assertEqual(finding["reason"], "timezone_invalid")
        pair = next(
            entry
            for entry in report["pairs"]
            if entry["routines"] == ["synthetic-bad-zone", "synthetic-utc-zone"]
        )
        self.assertEqual(pair["schedule"], "unknown")

    def test_malformed_evidence_exits_one_with_a_report(self):
        cases = {
            "events object": (
                {"owner": "synthetic-owner-a", "events": {"kind": "notify"}},
                {"state": "pending"},
                None,
                "malformed_field",
            ),
            "event kind list": (
                {"owner": "synthetic-owner-a", "events": [{"kind": []}]},
                {"state": "pending"},
                None,
                "malformed_field",
            ),
            "null event": (
                {"owner": "synthetic-owner-a", "events": [None]},
                {"state": "pending"},
                None,
                "malformed_field",
            ),
            "run status list": (
                {"owner": "synthetic-owner-a"},
                {"state": "pending"},
                [{"scheduled_at": "2026-11-22T01:00:00Z", "status": []}],
                "run_status_unknown",
            ),
        }
        for label, (notification, delivery, runs, code) in cases.items():
            with self.subTest(label):
                data = json.loads((FIXTURES / "healthy_minimal.json").read_text())
                data["routines"][0]["notification"] = notification
                data["routines"][0]["delivery"] = delivery
                if runs is not None:
                    data["routines"][0]["runs"] = runs
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "snapshot.json"
                    payload = json.dumps(data).encode("utf-8")
                    path.write_bytes(payload)
                    result = run_audit(path)
                    self.assertEqual(path.read_bytes(), payload)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                report = json.loads(result.stdout)
                self.assertFalse(report["all_clear"])
                finding = next(entry for entry in report["findings"] if entry["code"] == code)
                self.assertTrue(finding["blocks_all_clear"])

    def _snapshot_copy(self, directory):
        source = directory / "snapshot.json"
        payload = (FIXTURES / "healthy_minimal.json").read_bytes()
        source.write_bytes(payload)
        return source, payload

    def _assert_snapshot_output_rejected(self, alias_for):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, payload = self._snapshot_copy(directory)
            destination = alias_for(directory, source)
            result = run_audit(source, "--output", str(destination))
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((directory / "report.json").exists())

    def _assert_swapped_alias_rejected(self, swap):
        import agent_routine_kit.cli as cli

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, payload = self._snapshot_copy(directory)
            destination = directory / "report.json"
            destination.write_text("distinct-output", encoding="utf-8")
            real_identify = cli._output_identifies_snapshot
            state = {"swapped": False}

            def identify_then_swap(snapshot, output):
                identified = real_identify(snapshot, output)
                if identified is False and not state["swapped"]:
                    state["swapped"] = True
                    swap(source, destination)
                return identified

            cli._output_identifies_snapshot = identify_then_swap
            stdout, stderr = StringIO(), StringIO()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = cli.main(["audit", str(source), "--output", str(destination)])
            finally:
                cli._output_identifies_snapshot = real_identify
            self.assertTrue(state["swapped"])
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(code, 2, stderr.getvalue())
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn("Traceback", stderr.getvalue())

    def _assert_identity_failure_writes_nothing(self, install_patch):
        import agent_routine_kit.cli as cli

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, payload = self._snapshot_copy(directory)
            destination = directory / "report.json"
            sentinel = "sentinel-output"
            destination.write_text(sentinel, encoding="utf-8")
            restore = install_patch(destination)
            stdout, stderr = StringIO(), StringIO()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = cli.main(["audit", str(source), "--output", str(destination)])
            finally:
                restore()
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(destination.read_text(encoding="utf-8"), sentinel)
            self.assertEqual(code, 2, stderr.getvalue())
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn("Traceback", stderr.getvalue())

    def _resolve_raises(self, destination):
        real_resolve = Path.resolve

        def resolve(self, *args, **kwargs):
            if _same_path(self, destination):
                raise OSError("resolve unavailable")
            return real_resolve(self, *args, **kwargs)

        Path.resolve = resolve
        return lambda: setattr(Path, "resolve", real_resolve)

    def _samefile_raises(self, destination):
        real_samefile = Path.samefile

        def samefile(self, other):
            if _same_path(other, destination):
                raise OSError("samefile unavailable")
            return real_samefile(self, other)

        Path.samefile = samefile
        return lambda: setattr(Path, "samefile", real_samefile)

    def _fstat_raises(self, destination):
        del destination
        real_fstat = os.fstat

        def fstat(fd):
            raise OSError("fstat unavailable")

        os.fstat = fstat
        return lambda: setattr(os, "fstat", real_fstat)

    def _swap_in_hardlink(self, source, destination):
        os.unlink(destination)
        os.link(source, destination)

    def _swap_in_symlink(self, source, destination):
        os.unlink(destination)
        destination.symlink_to(source)


def _same_path(path, destination):
    if isinstance(path, int):
        return False
    try:
        return os.path.abspath(path) == os.path.abspath(destination)
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    unittest.main()
