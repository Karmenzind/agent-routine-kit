---
name: agent-routine-audit
description: Use when auditing a local normalized agent-routine snapshot for duplicate-target candidates, schedule collisions, auth-policy conflicts, notification ownership, or delivery evidence before any routine is changed.
---

# Agent routine audit

Audit the local snapshot with the kit before interpreting it. The script is the deterministic check. The model reads the report and explains it. The model does not override unknown coverage, unknown scope, or a missing receipt.

## When to use

Use this skill for an offline review of routines that were exported and normalized into contract version 1. Do not use it to log in, send a notification, merge a routine, or guess a platform API.

## Steps

1. Confirm the file is a local synthetic or authorized export with secrets removed.
2. Run `python3 -m agent_routine_kit audit SNAPSHOT.json --format both`.
3. Treat exit 2 as "no audit". Treat exit 1 as "read every blocking finding". Treat exit 0 as all-clear under rules_version 1 only.
4. Preserve unknown results. Missing account, profile, topic, deliverable, time zone, cron support, DST meaning, pagination, or deadline boundary is unknown, not healthy.
5. Do not call a schedule collision a duplicate, and do not call `last_alert`, `notify`, exit 0, or an HTTP start a delivery.
6. Stop when a finding blocks all-clear. Changing a live routine needs a separate approval, a new audit of the replacement, and a rollback path that records this `rules_version`.

## Authorization

Reading a snapshot does not authorize a write. This skill does not grant access to Muse, Grok Bot, or any account. If coverage is not complete, say that the audit cannot clear routines that were not in the file.
