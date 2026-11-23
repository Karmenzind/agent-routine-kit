# Changelog

## 0.1.0 - 2026-11-22

First offline audit of normalized routine snapshots.

- Contract version 1, schema version 1, report version 1, and rules version 1.
- Read-only CLI and library checks for duplicate-target candidates, schedule collisions, auth-policy conflicts, notification ownership, delivery evidence, coverage, and deadlines.
- `rules_version` is included on every report. A rollback of the kit must use the same `rules_version` as the report being compared.

Breaking changes to `contract_version`, `schema_version`, `report_version`, or `rules_version` need owner approval and a note in this file before they land.

## Rules version 2

Owner approval recorded these blocking-rule changes. This note records rules version 2. `contract_version`, `schema_version`, and `report_version` stay 1, and the report fields stay the same.

- A missing `routines` list is a contract error. An explicit empty list remains a valid inventory.
- `--output` is refused when it identifies the snapshot, including a resolved path, an existing symlink, a hard link, or an alias swapped in before the output is opened. The opened file is checked against the snapshot that was read before truncation, including when the input path is later repointed. If that identity cannot be established, the command fails closed. The snapshot bytes stay unchanged.
- Explicit boolean `flexible: true` on cron is `schedule_unknown` with reason `flexible_cron` for every affected pair. `flexible: false` and an omitted flag stay fixed cron.
- A delivered state without a receipt, and a nonempty `last_alert` timestamp, are `delivery_not_confirmed`. A receipt id plus an aware `confirmed_at` still confirms. Honest pending without those signals stays nonblocking.
- An invalid time zone is `schedule_unknown` with reason `timezone_invalid` instead of aborting the audit.
- `notification.events` must be a list of objects, event `kind` must be a string, and run `status` must be a string. A non-object event element is blocking `malformed_field`. Other wrong types are blocking malformed-field or unknown-status findings.
