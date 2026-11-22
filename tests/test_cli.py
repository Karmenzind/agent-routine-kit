"""CLI tests for the local read-only audit command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
