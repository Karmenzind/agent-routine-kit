# Routine audit v1 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Ship an offline, read-only Python kit that audits normalized local agent-routine snapshots for duplicate-target candidates, schedule collisions, auth-policy conflicts, notification ownership, and delivery evidence.

**Architecture:** A versioned JSON snapshot is loaded locally, validated against an explicit field whitelist, and audited by pure functions. The CLI prints a deterministic JSON report and a human rendering of the same findings. No network, credentials, schedulers, or routine mutation.

**Tech Stack:** Python 3.11+ standard library, `unittest`, no runtime dependencies.

## Global Constraints

- Contract, schema, rules, and report versions are `"1"`.
- Python standard library only. Do not install or import Scrapling.
- Read-only by default. The only write is an optional local `--output` report file.
- No network, credential loading, login, refresh, messaging, or platform mutation.
- Unknown account, CLI, profile, resource, action, source, deliverable, or output scope stays unknown. Never treat unknown as safe to merge or healthy.
- Same resource id with a different topic, or the same source with a different deliverable, is not a duplicate. Names are not identity.
- Unknown account or profile means auth-policy applicability is unknown. Never assume the same identity or select a login policy.
- Compare real instants across time zones. Missing time zone, unsupported cron, flexible windows, and DST gap/ambiguity are unknown, not "no conflict".
- A schedule collision is not a duplicate.
- `pending`, `last_alert`, `notify`, process exit 0, and HTTP 200 "started" are not confirmed delivery. Only a receipt id plus `confirmed_at` counts.
- Missing notification owner is an explicit blocking risk when notification or delivery data is present.
- Incomplete export coverage, incomplete pagination, or a missing deadline boundary prevents `all_clear`.
- Never report all-clear when required input is missing.
- Findings, pair order, and JSON bytes are deterministic under input reordering. Human output lists the same finding codes in the same order.
- Synthetic fixtures only. No real user names, ids, tokens, paths, or private snapshots.
- Breaking contract, schema, or rules changes need owner approval and a changelog note. Rollback guidance names `rules_version`.
- License stays TBD. Do not add a license file.
- The only ingest contract is the documented normalized snapshot. Do not invent Muse or Grok Bot APIs.

---

### Task 1: Contract, validation, and report shell

**Files:**
- Create: `src/agent_routine_kit/versions.py`
- Create: `src/agent_routine_kit/errors.py`
- Create: `src/agent_routine_kit/audit.py`
- Create: `src/agent_routine_kit/report.py`
- Test: `tests/test_audit.py`

- [x] Write failing tests for version echoes, malformed input, unknown fields, exit behavior, and deterministic ordering.
- [x] Run `PYTHONPATH=src python -m unittest tests.test_audit -v` and confirm failure because the package is missing.
- [x] Implement the smallest loader, whitelist, and report object that satisfies those tests.

### Task 2: Duplicate scope and auth policy

**Files:**
- Modify: `src/agent_routine_kit/audit.py`
- Create: `fixtures/duplicate_candidate.json`
- Create: `fixtures/not_duplicates.json`
- Create: `fixtures/auth_maintenance_conflict.json`
- Test: `tests/test_audit.py`

- [x] Tests: equal full scope is a candidate; names do not match; same resource/different topic is not a duplicate; same source/different deliverable is not a duplicate; missing scope is unknown.
- [x] Tests: `auto-login` versus `no-login` conflicts on a known shared account and profile; unknown account or profile does not assume identity or choose a policy.
- [x] Implement pair comparison. Collision and duplicate stay separate fields.

### Task 3: Schedules

**Files:**
- Create: `src/agent_routine_kit/schedule.py`
- Create: `fixtures/schedule_overlap_timezones.json`
- Test: `tests/test_audit.py`

- [x] Tests: equal UTC instants from different zones collide; non-overlapping local times do not; missing zone, unsupported cron, flexible window, DST ambiguity, and DST gap are unknown rather than no-collision.
- [x] Document and implement the five-field cron subset (single value, range, or `*`; not both day-of-month and day-of-week restricted).

### Task 4: Delivery, ownership, coverage, deadlines, missed runs

**Files:**
- Modify: `src/agent_routine_kit/audit.py`
- Create: `fixtures/delivery_false_signals.json`
- Create: `fixtures/repeated_notification.json`
- Create: `fixtures/missed_run.json`
- Create: `fixtures/deadline_timezone.json`
- Create: `fixtures/coverage_incomplete.json`
- Create: `fixtures/healthy_minimal.json`
- Test: `tests/test_audit.py`

- [x] Tests for receipt versus pending, attempted, last_alert, notify, exit 0, and HTTP start.
- [x] Tests for duplicate idempotency keys, missing owner, missed runs, deadline instants across zones, and coverage/pagination gates.

### Task 5: CLI, skill, and docs

**Files:**
- Create: `src/agent_routine_kit/cli.py`
- Create: `src/agent_routine_kit/__main__.py`
- Create: `SKILL.md`
- Create: `docs/contract.md`
- Create: `docs/rules.md`
- Create: `docs/adapters.md`
- Modify: `README.md`
- Create: `CHANGELOG.md`
- Test: `tests/test_cli.py`
- Test: `tests/test_docs.py`

- [x] CLI exit codes: 0 all-clear, 1 findings, 2 usage or contract error.
- [x] README keeps the title and tagline, then Main goals and Features, and separates implemented behavior from planned work.
- [x] Run `PYTHONPATH=src python -m unittest discover -s tests -v` and the documented CLI commands. Record the actual results.
