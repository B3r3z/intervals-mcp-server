# Coach tool completeness: architecture and verified analysis comments

Status: implemented locally, 2026-09-09. The user's instruction to continue authorized implementation of this scope. Final verification is recorded in [TATRA_V3_ACCEPTANCE.md](../../TATRA_V3_ACCEPTANCE.md#coach-catalogue-and-analysis-comments-2026-09-09).

## Settled scope

- Deepen all three architecture candidates, beginning with the coach tool catalogue.
- Coach tool completeness means coverage of agreed coach scenarios, not all Intervals.icu operations.
- Include verified publication of coach analysis comments in coach mode.
- A new analysis version creates a new comment. Repeating the same version returns its existing publication outcome; it does not publish again.
- Preserve the existing cycling and strength workout contract, established read contracts, and existing durable workout records.

The domain terms are defined in [CONTEXT.md](../../CONTEXT.md). Existing scenario and write guarantees are recorded in [TATRA_V3_ACCEPTANCE.md](../../TATRA_V3_ACCEPTANCE.md).

## Evidence and completion baseline

Fresh synthetic stdio discovery found 30 tools in admin, 22 in coach and 21 in readonly. An invalid mode exposes the readonly set. All advertised read and safe tools are present in their modes; the problem is duplicated declarations and incomplete re-export lists, not missing runtime registration.

The preceding architecture scan ran 105 selected tests successfully on Python 3.12.13. Existing scenario evidence covers S01-S12, while verified workouts have separate write-contract tests. That does not yet test a complete coach cycle with verified analysis-comment publication.

All checks for this design use repository code, synthetic transports or the supplied OpenAPI snapshot. Live account behavior remains unverified.

## 1. Deepen the coach tool catalogue

The catalogue module owns tool identity, callable, availability by access mode, capability grouping and effects. Its interface lets startup install the declared tools and lets capabilities describe the same resolved catalogue. Resolve the effective mode once for a running server.

Registration must be explicit. Imported handlers alone must not silently expand the installed tool set. A missing access classification or duplicate tool identity is a startup error. The existing FastMCP adapter supplies descriptions, input schemas and output schemas from the handlers.

Retain callable imports that existing callers use through `server.py` and `tools/__init__.py`; their re-export lists do not independently determine runtime availability. Preserve existing capability fields and add an exhaustive per-tool catalogue, including the names of admin legacy tools currently represented only by a boolean.

Distinguish upstream effects from local effects. Readonly prohibits upstream mutations; artifact export, directory creation and journal reconciliation can still change local state. Keep implemented, configured and live-verified facts separate.

Locality: tool availability is declared and checked in one place. Leverage: registration, discovery and capability descriptions use the same facts. This is an in-process seam; no additional SDK abstraction is required.

Acceptance:

- Compare complete declared and registered inventories, and the exhaustive capability catalogue, for admin, coach, readonly and invalid mode.
- Verify actual invocation rejection for tools excluded by the selected mode.
- Preserve existing public names, descriptions, schemas and compatibility imports; additions are explicit.
- Verify that changing process environment after startup cannot make capabilities contradict the installed catalogue.

## 2. Deepen HTTP ownership

The HTTP module has one owner for its client and lifespan. The request interface remains the existing place where reads and mutations cross the transport seam. Remove reverse lookup of `server.httpx_client` through `sys.modules` and the requirement that fixtures assign the client in two modules.

Production HTTP and the existing `httpx.MockTransport` are real adapters at this seam. Fixtures configure their adapter once. Keep lifecycle and transport concerns inside the HTTP implementation; tool callers do not need to coordinate client creation, reuse or shutdown.

Locality: client ownership and shutdown have one implementation. Leverage: all tools and protocol fixtures use the same request behavior.

Acceptance:

- Exercise client reuse, recreation when closed, and cleanup through its lifecycle and request interface.
- Preserve status-before-JSON error handling, redacted diagnostics, read retry rules and a single mutation attempt.
- Run existing verified-workout regressions and protocol scenarios against the synthetic adapter.

## 3. Deepen power-curve projection

The projection module receives original source curves and owns their interpretation, exact duration selection, aligned evidence, compact omissions, full continuations and unchanged raw data. Athlete and activity reads retain their distinct requests and domain meaning.

Remove the caller protocol that aliases `watts` into `values`, coordinates eight extra policy arguments and repairs `raw` afterward. Moving the same flags into a settings object would not satisfy the change. Internal implementation can distinguish the two real curve origins without exposing their representation rules to callers.

Locality: source shape and evidence preservation are verified together. Leverage: both existing curve reads benefit. Projection is in-process and needs no new adapter.

Acceptance:

- Preserve existing null/zero, sparse-duration, W/kg, alignment, missingness and compact/full contracts.
- Add the missing public-read case with `watts` and no `values`: selected points are correct and `raw` is identical to the original object.
- Preserve unknown source metadata and per-curve limitations. Do not interpolate or introduce physiological calculations.

## 4. Verified coach analysis comments

A dedicated comment-publication module owns analysis identity, durable publication state, one POST attempt and independent read-back. It does not model an activity comment as a workout session or place comment intents in the existing workout journal format.

Implemented public interface:

- `publish_analysis_comment(activity_id, analysis_uid, content)` publishes one analysis version. The caller keeps `analysis_uid` stable for that version; the module derives its internal operation identity.
- `get_analysis_comment_status(analysis_uid, reconcile=False)` returns the recorded outcome and can perform read-only upstream reconciliation.

Publication is available in coach and admin. Status inspection is also available in readonly. Actual stdio discovery verifies 32 tools in admin, 24 in coach and 22 in readonly.

The public interface hides fingerprints, journal paths, locks and the read-back sequence. Reuse the existing account lock and appropriate hashing primitives. Store comment records separately so existing workout records remain readable without migration. Share small durable primitives only when needed; do not introduce a universal mutation framework.

### Identity and repeated calls

- Scope an analysis UID to the configured account and bind it to one activity and exact content.
- The same UID with the same intent returns its durable result, including unresolved outcomes, without another POST.
- The same UID with different activity or content is a conflict.
- A new UID represents a deliberately new analysis version and appends a new comment.
- Do not edit or delete old comments, deduplicate by equal prose, or insert identity markers into the user-visible comment.

### Publication and verification

1. Validate the intent and available configuration, acquire the existing account write lock, and inspect durable state.
2. Check read access to the target activity and its messages before publication; a limited list does not establish absence of prior messages.
3. Durably record prepared and in-flight state before the single POST.
4. If the acknowledgement contains a valid numeric message ID, independently GET activity messages and compare that exact ID and content. Reject inconsistent activity identity when supplied and any returned deletion marker.
5. Record confirmed, rejected, conflict, unknown or mismatch as supported by evidence. A POST acknowledgement alone is insufficient for confirmed.
6. Reconciliation performs GETs only and preserves historical confirmation separately from current observation.

An interrupted in-flight record remains uncertain and prevents a second POST for that version. Publication guarantees depend on retaining the durable records and using this tool's identity contract; the upstream system does not provide documented exactly-once publication.

### Constraints from the supplied OpenAPI

The reference snapshot has SHA-256 `2adb2740529e1add18e790eca75d17fa9d28d700dc464791db5bd6767c1c7b50`.

- Activity-message POST accepts only `content` and returns `NewMsg`, whose optional fields include numeric `id` and `new_chat`. It does not return the stored message content.
- Activity-message GET returns `Message[]` and documents optional `sinceId` and `limit`, with a default limit of 100. It documents no completeness indicator or reliable cursor ordering semantics.
- There is no documented idempotency key, external ID, conditional header, or direct activity-message GET by message ID.
- If the POST ID is lost or malformed, matching text, timestamps or display names cannot prove that a listed comment was created by this operation. Keep unknown and do not retry publication.
- A known ID missing from a limited read also remains unknown; it does not establish failure, deletion or permission to publish again.
- Missing required verification evidence is not a successful read-back. Immediate visibility after POST is unverified.

### Related read-contract corrections

These are required for reliable comment evidence, not a new general chat-management feature:

- Correct the existing claim that `get_activity_messages` retrieves all messages; preserve unknown coverage for bounded upstream lists.
- Preserve documented message identity and deletion fields in full reads and make their compact omission explicit where applicable.
- Use raw documented message fields for publication verification instead of treating the existing display fingerprint as an upstream identity token.
- Pin relevant `Message` and `NewMsg` response shapes in local contract fixtures and use numeric message IDs in examples and synthetic responses.

Acceptance:

- One successful POST plus an independent exact-ID/content read-back confirms publication.
- Repeated same-version calls, changed-intent conflicts and process restarts never trigger a duplicate POST.
- Timeout, malformed or missing acknowledgement ID, limited reads, missing verification fields, deleted messages, duplicate-content decoys and content mismatch preserve the appropriate non-confirmed outcome.
- Reconciliation cannot POST, PUT or DELETE and cannot promote a text-only match to confirmation.
- Comment history remains intact when a new analysis version is published.
- Interrupted or corrupted journals and simultaneous account writers fail safely.

## Coach scenarios and final validation

Retain the existing twelve analytic scenarios and verified-workout regressions. Add a synthetic stdio coach cycle that discovers capabilities, retrieves session evidence and linked plan, publishes and verifies an analysis version, replays it without a second POST, and writes and verifies a subsequent workout. The fixture checks target identities, content and the allowed upstream operations at each step.

Also cover an uncertain comment publication followed by a restarted process and read-only status reconciliation. Successful session evidence and other independently valid observations must remain available alongside uncertain write outcomes.

Run the full Python 3.12 pytest suite, ruff and `mypy src tests`, plus the relevant OpenAPI and stdio contract checks. Record actual results and limitations. Passing local fixtures does not change `live_verified=false`.

## Implementation order

1. Catalogue and exact discovery/availability tests (original proposal 2).
2. HTTP ownership and transport/lifecycle regressions (original proposal 3).
3. Curve projection and evidence-preservation regression (original proposal 1).
4. Verified analysis comments, related read evidence corrections and the complete synthetic coach cycle.
5. Full verification, diff review and an updated acceptance record.

Existing unrelated worktree changes remain part of the starting state. This design does not require a commit, push, deployment or an account mutation.
