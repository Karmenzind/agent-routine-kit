# Adapter boundary

This kit audits a local JSON file that already uses the normalized contract in `docs/contract.md`. That file is the Muse export contract for this repository: a manual, offline normalization into contract version 1. The kit does not define or call a Muse API, a Grok Bot API, or any other product API.

## Manual export

1. Use an official, supported surface you are already authorized to read. This repository does not grant that authorization and does not list private endpoints.
2. Save the export outside any credential store. Remove tokens, cookies, and private message text before normalization.
3. Map only the facts you actually have into the contract fields. Use a known string only when the export states it.
4. Leave a field null or `unknown` when the export does not say. Do not copy a display name into account, profile, resource, or deliverable to fill a gap.
5. Set `export.coverage` and `export.pagination.complete` from the export you finished. Partial pages are `partial` or false, not `complete`.
6. Set `export.deadline_coverage` the same way. Missing deadline bounds stay missing.
7. Run `python3 -m agent_routine_kit audit` on that local file.

The kit does not log in, refresh sessions, send messages, or change routines. A future mutation, if one is ever built, needs a separate approval, a fresh audit, and a rollback of the previous live definition. This version does not perform that mutation.

## What not to add

Do not invent permission names, request bodies, or authentication headers for Muse or Grok Bot in this repository. Do not commit live configuration.

Scrapling (https://github.com/d4vinci/Scrapling) may later be considered as an optional web-fetch adapter. It is not a required dependency, and official supported APIs come before a scraper. This kit does not install or import it.
