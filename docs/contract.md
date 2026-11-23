# Snapshot and report contract

contract_version: 1

schema_version: 1

report_version: 1

The snapshot contract is the only input this kit accepts. It is a normalized local file. It is not a copy of a Muse, Grok Bot, or other vendor API.

## Snapshot

Top-level fields:

- `contract_version`: must be the string `1`. Any other value is rejected before an audit report is produced.
- `export.source`: a short label such as `manual-normalized`.
- `export.coverage`: `complete`, `partial`, or `unknown`.
- `export.pagination.complete`: boolean. True only when every page was included.
- `export.deadline_coverage`: `complete`, `partial`, or `unknown`.
- `export.exported_at`: optional aware timestamp for the export itself.
- `audit.as_of`: aware timestamp used for deadline checks.
- `audit.window.start` and `audit.window.end`: aware instants. The end is exclusive. This bounds schedule comparison.
- `routines`: required list of routine objects. A missing key or a non-list is rejected before a report is produced. An explicit empty list is a valid inventory.

Routine fields:

- `id`: required string, unique in the snapshot.
- `name`: display text only. Not used for identity.
- `identity.account`, `identity.cli`, `identity.profile`.
- `target.resource_id`, `target.topic`, `target.action`, `target.source`, `target.deliverable`, `target.output_scope`.
- `schedule.kind`: `instants`, `cron`, or `window`.
- `schedule.scope`: required known string. Different scopes do not erase a time overlap, and a missing scope makes the schedule unknown.
- `schedule.instants`: list of aware timestamps.
- `schedule.expression` and `schedule.timezone`: used by cron. Time zone is an IANA name. An invalid name is `schedule_unknown` with reason `timezone_invalid`.
- `schedule.flexible`: a window resolves only when this is false. On cron, explicit boolean `flexible: true` is `schedule_unknown` with reason `flexible_cron`. `false` or an omitted flag keeps that cron fixed.
- `schedule.window.start` and `schedule.window.end`: aware instants.
- `auth_recovery.policy`: `auto-login`, `no-login`, or `manual`.
- `notification.owner`: required when notification or delivery data is present.
- `notification.events`: a list of objects with `at`, `idempotency_key`, and `kind`. `kind` is a string. A non-object element, such as null, or a non-string kind is blocking `malformed_field`.
- `delivery.state`: `pending`, `attempted`, or other text. A state is not a receipt. `delivered`, `sent`, and `notified` without a receipt are `delivery_not_confirmed`.
- `delivery.attempts[]`: `at`, `result`, `receipt_id`, `idempotency_key`.
- `delivery.last_alert`, `delivery.notify`, `delivery.claimed`: flags, labels, or a nonempty `last_alert` timestamp. None of them confirm delivery.
- `delivery.receipt.id` and `delivery.receipt.confirmed_at`: the only confirmation pair.
- `deadline.at`: aware timestamp. `deadline.timezone` may repeat the zone name but does not replace an offset on `at`.
- `runs[]`: `scheduled_at`, `status` (`missed`, `ran`, or `skipped`). A non-string status is blocking `run_status_unknown`.

Unknown keys anywhere in the document are reported and block all-clear.

## Cron subset

Five fields, in order: minute, hour, day of month, month, day of week.

Each field is `*`, a single number, or a range `low-high`. Day of week is 0 (Sunday) through 6 (Saturday). An expression that restricts both day of month and day of week is unsupported. `*/15`, comma lists, month names, seconds, and macros such as `@daily` are unsupported and stay unknown.

Schedule math uses the audit window only, and only when that window is timezone-aware and no longer than 62 days.

## Report

The report always includes:

- `report_version`, `contract_version`, `schema_version`, `rules_version`, `kit_version`
- `all_clear`: true only when no finding has `blocks_all_clear` set
- `coverage.status`: `complete` or `unknown`
- `summary.routine_count`, `summary.finding_count`, `summary.by_code`
- `findings[]` with `code`, `severity`, `blocks_all_clear`, `subjects`, `reason`, `fields`, `detail`
- `routines[]` with `id`, `delivery_status`, `schedule_status`, `scope_status`
- `pairs[]` with sorted routine ids, `duplicate` (`candidate`, `not_duplicate`, `unknown`), `schedule` (`collision`, `no_collision`, `unknown`), `auth_policy` (`conflict`, `no_conflict`, `unknown`, `not_applicable`), and `target_note`

JSON object key order in the file does not matter. The auditor sorts routines, pairs, and findings so the same snapshot contents produce the same JSON bytes.

Human text prints `all_clear` and one `finding:` line per finding, in the same order as the JSON `findings` array.

## Exit codes

- `0`: a report was produced and `all_clear` is true.
- `1`: a report was produced and `all_clear` is false.
- `2`: the file could not be read, the JSON is invalid, `contract_version` is missing or unsupported, `routines` is missing or not a list, `--output` identifies the snapshot file, or the output identity cannot be established. The opened output is checked again before it is truncated, against the file that was read, including when the input path is later repointed and when the output path is replaced by a same-path alias, symlink, or hard link after the first check. No success report is printed and the snapshot bytes stay unchanged. A failed output write also exits 2 and prints no success report.
