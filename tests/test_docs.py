"""Documentation and packaging checks for the public v1 kit."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocTests(unittest.TestCase):
    def test_readme_leads_with_goals_and_features(self):
        text = (ROOT / "README.md").read_text()
        self.assertTrue(text.startswith("# agent-routine-kit\n"))
        tagline = text.index("for my Grok Bot, Muse and other agents")
        goals = text.index("## Main goals")
        features = text.index("## Features")
        quick = text.index("## Quick start")
        self.assertLess(tagline, goals)
        self.assertLess(goals, features)
        self.assertLess(features, quick)
        self.assertIn("License TBD", text)
        self.assertIn("rules_version", text)
        self.assertIn("https://github.com/d4vinci/Scrapling", text)
        self.assertIn("not a required dependency", text)
        self.assertIn("Implemented", text)
        self.assertIn("Planned", text)

    def test_skill_frontmatter_names_when_to_use_it(self):
        text = (ROOT / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: agent-routine-audit", text)
        self.assertIn("description:", text)
        self.assertIn("approval", text.lower())
        self.assertIn("rollback", text.lower())

    def test_rules_and_contract_are_versioned(self):
        rules = (ROOT / "docs" / "rules.md").read_text()
        contract = (ROOT / "docs" / "contract.md").read_text()
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertIn("rules_version: 1", rules)
        self.assertIn("contract_version: 1", contract)
        self.assertIn("schema_version: 1", contract)
        self.assertIn("report_version: 1", contract)
        self.assertIn("rules_version", changelog)

    def test_runtime_dependencies_are_empty(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(project["project"]["dependencies"], [])
        source = "\n".join(path.read_text() for path in (ROOT / "src").rglob("*.py"))
        for banned in ("urllib", "requests", "http.client", "scrapling", "socket"):
            self.assertNotIn(banned, source)

    def test_adapters_do_not_invent_platform_apis(self):
        text = (ROOT / "docs" / "adapters.md").read_text()
        self.assertIn("manual", text.lower())
        self.assertIn("does not", text.lower())
        self.assertNotIn("Authorization: Bearer", text)


if __name__ == "__main__":
    unittest.main()
