# Audit rules

rules_version: 1

These are the rules the v1 auditor applies. A report names this `rules_version`. Do not compare a blocking decision across two rules versions without reading the changelog.

## Coverage

- `export.coverage` must be `complete` and `export.pagination.complete` must be true. Anything else is `coverage_unknown` and blocks all-clear.
- `export.deadline_coverage` must be `complete`. A missing or other value is `deadline_boundary_missing` and blocks all-clear.
- `audit.as_of` must be a timezone-aware instant. A missing or naive value blocks all-clear.
- The auditor never fills in missing routines, pages, or deadlines, and it never reports all-clear for an incomplete export.

## Scope and duplicates

- A duplicate candidate requires every scope field to be known and equal: account, CLI, profile, resource id, topic, action, source, deliverable, and output scope.
- A value is unknown when it is missing, blank, null, or the string `unknown`.
- Unknown scope is not a candidate and is not proof that two routines differ. It blocks all-clear.
- Display names are ignored.
- The same resource id with a different known topic is not a duplicate.
- The same source with a different known deliverable is not a duplicate.
- A schedule collision is a separate finding. It does not make a duplicate candidate.

## Auth recovery

- Auth-policy comparison applies only when both routines have a known account and a known profile, and those two pairs are equal.
- Unknown account or profile means applicability is unknown. The auditor does not assume the routines belong to one identity and does not select a login policy.
- Known policies are `auto-login`, `no-login`, and `manual`. Different known policies on one known identity conflict and block all-clear.
- An unsupported or missing policy on a known shared identity is unknown, not "no conflict".

## Schedules

- Instants are compared after conversion to UTC. A local time and another zone's time can collide when they are the same instant.
- The supported cron subset is five whitespace-separated fields: minute, hour, day of month, month, day of week.
- A field may be `*`, one integer, or an inclusive range such as `1-5`. Day of week uses 0 for Sunday through 6 for Saturday.
- Steps, lists, names, seconds, years, and expressions that restrict both day of month and day of week are unsupported.
- Missing time zone, invalid time zone, unsupported cron, a flexible window, an unspecified flexible flag on a window, or a DST gap or ambiguous local time is `schedule_unknown`. That result is not "no collision".
- A non-flexible window uses an inclusive start and an exclusive end.
- Comparison is limited to the timezone-aware audit window. Windows longer than 62 days are unknown.
- More than 100 routines skips pair comparison, reports `snapshot_too_large`, and does not claim that no duplicates exist.
- A resolved overlap blocks all-clear with `schedule_collision` and still does not mark the pair as a duplicate.

## Notification and delivery

- Confirmed delivery requires a receipt `id` and a timezone-aware `confirmed_at`.
- `pending` is not delivered. It is reported and does not by itself block all-clear.
- `last_alert`, `notify`, a claimed delivered state, process `exit_0`, HTTP `http_200`, and `started` do not confirm delivery. Without a real receipt they block all-clear as `delivery_not_confirmed`.
- A repeated idempotency key is retry evidence. It blocks all-clear when no real receipt is present. A real receipt can still confirm delivery, and the retry stays visible as a non-blocking finding.
- When a notification or delivery object is present, a known notification owner is required. A missing owner blocks all-clear.
- A run with status `missed` and a timezone-aware `scheduled_at` blocks all-clear. A missing time zone or unknown run status blocks all-clear and is not treated as a successful run.

## Deadlines

- When deadline coverage is complete, every routine needs `deadline.at` as a timezone-aware instant.
- A naive timestamp is a missing boundary, not an on-time deadline.
- The deadline is exceeded when `audit.as_of` is later than that instant and delivery is not confirmed. Comparison uses the real UTC instant, so offsets are honored.

## Unknown fields

- Fields outside the contract whitelist are `unknown_field` findings and block all-clear. They are not silently ignored and they are not given a meaning.
