# Changelog

## 0.1.0 - 2026-11-22

First offline audit of normalized routine snapshots.

- Contract version 1, schema version 1, report version 1, and rules version 1.
- Read-only CLI and library checks for duplicate-target candidates, schedule collisions, auth-policy conflicts, notification ownership, delivery evidence, coverage, and deadlines.
- `rules_version` is included on every report. A rollback of the kit must use the same `rules_version` as the report being compared.

Breaking changes to `contract_version`, `schema_version`, `report_version`, or `rules_version` need owner approval and a note in this file before they land.
