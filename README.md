# agent-routine-kit

for my Grok Bot, Muse and other agents

## Main goals

Make agent routines reliable enough to review offline, and cut avoidable model work by doing the deterministic checks in a script. The kit compares a normalized local snapshot against explicit rules and returns the same result every time. It does not run the routines.

## Features

- Read a versioned local snapshot and reject an unsupported contract before reporting success.
- Flag unknown and unsupported fields instead of ignoring them.
- Report duplicate-target candidates only when account, CLI, profile, resource, topic, action, source, deliverable, and output scope are all known and equal.
- Report schedule collisions from real UTC instants, including different time zones, and keep that result separate from duplicate detection.
- Report unknown schedules for missing or invalid zones, unsupported cron, flexible windows, explicit flexible cron, and DST gaps or ambiguous times.
- Report auth-policy conflicts for a known shared account and profile, and leave unknown identities unresolved.
- Check notification ownership and whether delivery evidence is a real receipt.
- Block all-clear when export coverage, pagination, or deadline boundaries are incomplete.
- Print stable JSON and a human report that lists the same findings. Exit codes are 0, 1, and 2.

## Quick start

Python 3.11 or newer. No install and no runtime dependencies.

```bash
PYTHONPATH=src python3 -m agent_routine_kit audit fixtures/healthy_minimal.json
PYTHONPATH=src python3 -m agent_routine_kit audit fixtures/auth_maintenance_conflict.json --format text
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

`--format json` writes JSON to stdout and is the default. `--format text` writes the human report to stdout. `--format both` writes JSON to stdout and the human report to stderr. `--output report.json` is the only file write. The command refuses an output path that is the snapshot, including a resolved path, an existing symlink, a hard link, or an alias swapped in before the file is opened. It checks the opened file against the snapshot that was read before truncating, including when the input path is later repointed, and fails closed when that identity cannot be established. Exit 2 leaves the snapshot unchanged and prints no success report. A separate output path still receives the report.

Exit `0` means a report was produced and `all_clear` is true. Exit `1` means a report was produced and `all_clear` is false. Exit `2` means the file, JSON, contract, or `routines` list could not be audited, the output path identifies the snapshot, the output identity could not be established, or the output write failed.

## Implemented

Version 0.1.0 implements the local audit described above:

- contract, schema, and report version `1`; rules version `2`
- duplicate scope, schedule subset, auth policy, delivery receipts, missed runs, and deadlines
- synthetic fixtures under `fixtures/`
- portable instructions in `SKILL.md`
- the normalized ingest contract in `docs/contract.md` and the rules in `docs/rules.md`

`all_clear` is true only when no finding blocks it. A listed schedule collision blocks it and is still not a duplicate. An honest `pending` delivery is reported as pending and does not by itself block all-clear. `last_alert` (including a nonempty timestamp), `notify`, a delivered claim without a receipt, process exit 0, and an HTTP start do block all-clear unless a receipt id and aware `confirmed_at` are both present. Explicit boolean `flexible: true` on cron is unknown. A missing `routines` list is rejected. Invalid zones and malformed notification or run values produce a blocking report instead of aborting.

## Planned

Not in this version:

- calling Muse, Grok Bot, or any other platform
- loading credentials, logging in, or refreshing a session
- sending notifications or running a scheduler, cron job, or background service
- merging, editing, deleting, or replacing live routines
- a full delivery-state service
- resolving DST to a single instant
- cron syntax beyond the subset in `docs/contract.md`
- an optional web-fetch adapter

Any later mutation must be a separate change. It needs its own approval, a new audit, and a rollback of the previous live definition.

## Limitations

- Pair comparison covers at most 100 routines. Larger files return `snapshot_too_large` and do not claim there are no duplicates.
- Schedule comparison uses only the audit window, which must be timezone-aware and at most 62 days.
- Unsupported cron and unresolved DST are unknown, which blocks all-clear. They are not treated as free of collisions.
- The kit does not prove that a platform delivered a message. It only checks the evidence in the snapshot.
- No token, cost, or runtime-savings number is claimed.

## Compatibility and versioning

| Name | Current value | Changes when |
| --- | --- | --- |
| `contract_version` | 1 | the snapshot fields change incompatibly |
| `schema_version` | 1 | the report fields change incompatibly |
| `report_version` | 1 | the report document changes incompatibly |
| `rules_version` | 2 | a blocking rule changes |

A breaking change to any of those values needs owner approval and a changelog note. Reports record all four values so a later reader can see which rules produced the decision.

Input key order does not matter. Findings, pairs, and JSON bytes are sorted.

## Examples

Auth maintenance with two synthetic identities on one fake account. Their policies are `auto-login` and `no-login`. They are not duplicates, and their instants do not collide.

```bash
PYTHONPATH=src python3 -m agent_routine_kit audit fixtures/auth_maintenance_conflict.json --format text
```

```text
agent-routine-kit
report_version: 1
contract_version: 1
schema_version: 1
rules_version: 2
kit_version: 0.1.0
all_clear: false
coverage_status: complete
routine_count: 2
finding_count: 1
finding: auth_policy_conflict severity=warning subjects=synthetic-auth-a,synthetic-auth-b reason=conflicting_policies blocks=true fields=auto-login,no-login detail=
routine: synthetic-auth-a delivery=not_applicable schedule=resolved scope=known
routine: synthetic-auth-b delivery=not_applicable schedule=resolved scope=known
pair: synthetic-auth-a,synthetic-auth-b duplicate=not_duplicate schedule=no_collision auth_policy=conflict
```

That command exits 1. Other fixtures cover duplicate candidates, same-source different deliverables, cross-zone schedule overlap, unsupported cron, false delivery signals, repeated notification keys, missed runs, deadline zones, and incomplete pagination.

## Contribution and concurrent edits

Work on a feature branch. Before editing, fetch and reread the latest base branch and keep changes that landed there. Do not rewrite or discard another branch.

If two edits touch the contract or the rules, stop and reconcile them. An incompatible `contract_version`, `schema_version`, `report_version`, or `rules_version` needs owner approval and a changelog note. Do not silently mix reports from different rules versions.

Keep examples synthetic. Do not commit real account names, user ids, tokens, credential stores, private paths, or live routine exports.

## Changelog and rollback

See `CHANGELOG.md`. To roll back this kit, check out the previous commit and use the `rules_version` printed on the report you still rely on. A report from rules version 1 is not a decision under a later rules version. Rolling back the kit does not change live platform routines; this version never writes to them.

## License

License TBD. The owner has not selected a distribution license. This repository does not add one.

## Optional future adapters

Scrapling (https://github.com/d4vinci/Scrapling) may be considered later as an optional web-fetch adapter. It is not a required dependency and is not installed or imported. Prefer an official API or another supported export surface first. See `docs/adapters.md` for the manual normalization steps. The only ingest contract in this repository is `docs/contract.md`.
