# Workout history, activity exports and interval evidence

The 2026-09-10 architecture review found that a syntactically valid workout
journal could replay `confirmed` with another operation's result identity, while
an incomplete nested result escaped as a validation exception. The repair makes
the journal own trustworthy record interpretation. The same change set removes
duplicate export hashing and consolidates activity interval interpretation.

## Workout operation history

`OperationJournal` owns the supported record schema, account and filename
identity, validated intent/result models, fingerprint consistency and retained
history fields. Its interface returns validated records; callers no longer
decode raw dictionaries. A record with inconsistent identity or fingerprint is
`JOURNAL_CORRUPT` on replay, status, session lookup and attempted overwrite.
Changing the account label cannot hide a record whose filename still identifies
an operation belonging to the current account. Genuinely foreign records retain
their existing isolation from this account's nested-model validation.

`save` returns the persisted result and leaves its input unchanged. It preserves
prior non-null values for preparation/sending timestamps, event identity,
external identity, intent/expected fingerprints and target date when the new
result omits them. A non-null observed event ID can differ from the intended ID:
that is useful mismatch evidence. Saving cannot rebind an existing operation to
a different intent or decision.

Disk filenames, version `1.0`, field names and `created_at` are preserved.
Existing records with `decision_uid=None` or an empty string, absent optional
result fingerprints/timestamps, and event ID zero remain readable without
migration. Stored external identity is not recalculated using today's namespace.

Replay and status use the same interpretation behind the journal seam. A failed
local save after reconciliation returns an uncertain result while retaining
historical evidence and the independent upstream observation. It does not retry
or publish. Workout and coach analysis comment journals remain separate, as
required by [the settled design](coach-tools-design.md#4-verified-coach-analysis-comments).

Locality: record validity and preservation have one implementation. Leverage:
replay, session protection and status share that implementation. Existing file
and cross-process lock tests remain; new regressions exercise corrupt records
through the public tool interface. Internal consistency checks do not authenticate
arbitrary local file edits or recover deleted history.

## Activity export identity

The existing artifact module serializes the payload once, derives SHA-256 from
those bytes and uses that digest for both the artifact hash and local snapshot
identity. Export callers and test setup no longer need to reproduce canonical
JSON rules. The manifest format, exact source evidence, retention, failed-write
cleanup and chunk retrieval remain unchanged.

Tests independently hash bytes read back from storage and reconstruct the export
through an actual MCP client. The content hash describes a local composite of
separate stream and interval reads; upstream atomicity and completeness remain
unknown. Locality improves without an additional storage adapter.

## Activity interval evidence

`intervals.py` owns source-container validation, null/missing distinctions,
compact field selection, omissions and their coverage effects. Its interface
returns preserved data with presentation facts. Raw reads, activity exports and
session context use the same interpretation. Session context no longer
reinterprets omitted-record counts to decide interval coverage.

Source selection stays in session context: use valid embedded intervals, fetch
dedicated intervals when embedded intervals are absent, reject malformed
embedded intervals, and retain available groups when the dedicated read fails.
A raw groups-only container is a complete raw response; its composed interval
section still reports missing interval evidence. This distinction is preserved.

The private `_projection.py` implementation holds the existing field-copy and
bounded-record primitives also used by comments, wellness and plan presentation.
It introduces no new public tool or configurable projection framework. No new
HTTP adapter is needed: real HTTP and the existing synthetic adapter already
exercise the transport seam.

Contract tests compare standalone, exported and composed evidence, and verify
compact omissions and full continuation for both embedded and dedicated inputs.
They preserve unknown fields, ordering, zeroes, nulls, legacy flat lists and the
existing public response schemas.

## Verification

Actual completion results are recorded in
[TATRA_V3_ACCEPTANCE.md](../../TATRA_V3_ACCEPTANCE.md#architecture-repair-2026-09-10).
All checks use local files and synthetic transports. `live_verified=false`.
