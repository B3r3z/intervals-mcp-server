# TATRA V3 acceptance status

This report maps the SDD scenarios to automated evidence in this repository.
Unless stated otherwise, all checks use fixtures or local subprocesses: they do
not establish live Intervals.icu behavior.

| ID | Status | Automated evidence or limitation |
| --- | --- | --- |
| T01 | Automated | Empty activity period is distinct from an error and reports complete coverage. |
| T02 | Automated | Local snapshot pagination preserves unnamed activities, stable ordering, and continuation. |
| T03 | Automated | Half-open dates, legacy inclusive adaptation, invalid ranges, and DST-aware UTC boundaries. |
| T04 | Automated | Raw `null` and zero values are preserved; stream work is labelled in joules without a false kJ conversion. |
| T05 | Automated | Missing requested streams and curve durations produce explicit warnings. |
| T06 | Automated | Preview spans, exact range reads, and full local artifact export. |
| T07 | Automated | Unequal arrays, missing indices, irregular time, duplicates, and `null` stay explicit. |
| T08 | Automated | A changed stream snapshot is rejected with `SNAPSHOT_CHANGED`. |
| T09 | Automated | Generated paths remain inside the configured root; hashes, limits, sidecars, retention, and expiry are tested. |
| T10 | Automated | Message identity/timestamps are preserved and content edits change the stable fingerprint. |
| T11 | Automated | HTML 502, 401/403, 429, invalid JSON, and read timeout classification/retry are covered. |
| T12 | Automated | Conflicting structured steps and manually supplied derived fields fail validation before HTTP. |
| T13 | Automated | Missing/changed parsed steps, targets, and durations cannot become `confirmed`. |
| T14 | Automated | Mutation responses never replace the independent GET; mismatch and incomplete states are preserved. |
| T15 | Automated | Unsupported running, wrong target identity/category, and mismatched IDs fail before mutation. |
| T16 | Partial | Fresh fingerprint conflicts are tested; atomic upstream conditional writes remain `unverified`. |
| T17 | Automated | An uncertain create is reconciled by deterministic identity without a second mutation. |
| T18 | Automated | Same-intent replay, reused operation UID, and existing session conflicts are covered. |
| T19 | Automated | Persisted `in_flight` state survives restart semantics and requires reconciliation. |
| T20 | Automated | A confirmed/conflict/not-attempted package stops without rollback. |
| T21 | Automated | The account lock is exercised across a separate local Python process. |
| T22 | Automated | Historical confirmation is preserved after a current manual mismatch; replay never restores it. |
| T23 | Automated | Event 404 plus failed account-list access remains `unknown`, never a confirmed delete. |
| T24 | Automated | Absence from the original narrow date range after uncertain create remains `unknown`. |
| T25 | Automated | Real stdio MCP listing hides legacy writes in coach/readonly modes. |
| T26 | Automated | Real MCP initialize/list/call checks output schema, structured/text identity, `isError`, and stderr redaction. |
| T27 | Not live-verified | Artifact files and hashes are opened locally in tests; the actual TATRA Coach module/path mapping was not run. |
| T28 | Not run | No live create/update/delete was authorized or performed. |

`get_capabilities` therefore keeps `live_verified=false`, conditional event
writes and external-ID semantics `unverified`, and settings history
`unavailable`. A dedicated M6 run with a disposable test event is still required
before autonomous calendar writes can be described as live-ready.
