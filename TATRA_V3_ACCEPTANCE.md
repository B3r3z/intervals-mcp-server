# Agent analytics quality and TATRA V3 acceptance

## Completed local goal (2026-09-09)

Make the public MCP descriptions, schemas and results sufficient for an agent to
analyse a session and its fragments, compare execution with its linked plan and
historical efforts, inspect intensity and recovery context, and identify evidence
and limitations. MCP supplies data and calculations; the agent makes coaching
decisions. This is the single progress document for this goal. The older T01-T28
matrix below records the existing write-contract scope, not live readiness.

Scope: local implementation, synthetic fixtures and real stdio MCP protocol tests.
No account tests, production mutations, deployment, commits or push are authorized.
Preserve gear/gear_id cleanup and custom metric definition reads. Athlete comments,
descriptions and custom item content are untrusted data, never executable instructions.

### Completion result

The local scope is complete. Public MCP tools now support session and repetition
analysis, arbitrary fragments, best efforts versus a specified period, activity
and fatigue curves, exact linked plans, HR/wellness context, custom definitions
and strength records with explicit missing detail. Units, origin, source limits,
compact projections and client-accessible full-data continuations are exposed.

- **12/12 deterministic protocol cases passed**, plus **12/12 answers passed
  root review in a separate fresh-agent run** using public MCP descriptions,
  schemas and results. [Independent evaluation and answers](tests/evidence/v1_independent_agent_evaluation.md).
- Final Python 3.12 verification: **411 passed, 1 skipped**, ruff and mypy passed,
  advertised protocol schemas matched, **22 OpenAPI operations** and snapshot
  SHA256 matched, and `git diff --check` passed.
- All four baseline read defects are fixed. The same six baseline calls remain
  six calls, with larger responses that expose missingness and provenance.
  For the same S01 fixture, session context reduces **3 MCP / 3 HTTP to 1 MCP /
  2 HTTP**; its small response is larger, so no byte or token saving is claimed.
- The HTTP client, operation journal and verified-write module preserve their
  original logic; legacy mutation ASTs and write/gear regressions remain intact.
  HEAD and the initially empty Git index are unchanged. No commit or push.
- **Live verification: not run; `live_verified=false`.** The native Windows
  symlink-creation test is the one skip. Contract comparison uses the supplied
  OpenAPI snapshot plus official semantic sources; fresh remote OpenAPI equality
  was unavailable. None of these local results establishes account readiness.

No required local increment remains. Optional follow-ups are listed below and
do not extend this completed goal.

### Baseline and verification method

- Starting revision: `71381d42b2d9bae8c1f841cc55fd9b3ef3be0e53`; clean worktree and index.
- Existing `.venv` runtime: Python **3.14.6**, MCP **1.22.0**, httpx **0.28.1**,
  Pydantic **2.12.4**. Root also prepared an isolated **Python 3.12.13** environment
  under `.runtime/venv-py312` for the project's requested Python 3.12 verification:
  set `UV_PROJECT_ENVIRONMENT=.runtime/venv-py312` and
  `UV_PYTHON_INSTALL_DIR=.runtime/python`, then `uv --cache-dir .uv-cache sync --all-extras --python 3.12`.
  The original environment remains intact. Final checks passed on Python 3.12.
- Reference OpenAPI: `C:\Users\BartoszBerezowski\Downloads\openapi-spec (1).json`,
  SHA-256 `2adb2740529e1add18e790eca75d17fa9d28d700dc464791db5bd6767c1c7b50`.
- Baseline: `uv --cache-dir .uv-cache run pytest -p no:cacheprovider --basetemp=.pytest-goal-baseline`
  returned **182 passed, 1 failed** (artifact expiry test assumed a 1-second TTL
  while local dotenv configuration supplied 3600 seconds). Repeating the artifact
  tests with `PYTHON_DOTENV_DISABLED=1` gave **5 passed**. Final verification
  isolates test configuration and the expiry check now uses deterministic timing.
  `uv --cache-dir .uv-cache run ruff check .` and `uv --cache-dir .uv-cache run mypy src tests`
  passed (44 files; existing untyped-body notes).
- Four audit findings were present in the starting revision: default stream
  omissions were hidden; Hidden/Strava activities lacked source warnings; power
  duration omissions were aggregated across curves; malformed event results
  could become empty success.
- Additional baseline inspection found activity/messages/wellness shape coercion
  hiding bad payloads, lossy text custom reads, artifacts exposing only a server
  file path, and analytical descriptions missing units or continuation instructions.
  AST inspection of the starting revision found **8 read tools with no docstring**:
  activities, details, intervals, messages, streams, events, event-by-id and athlete
  power curves. Registered output schemas alone do not establish discoverability.
- Protocol baseline and final scenario measurements record MCP calls,
  upstream attempts, UTF-8 response bytes, completeness and schema validity.
  Synthetic expected tool selection is deterministic; it is not an independent
  agent evaluation. Live and independent-agent checks remain separate statuses.
- Existing OpenAPI checker: **18-operation surface and source SHA256 match** the
  supplied snapshot. The new stdio fixture subprocess disables dotenv and uses
  synthetic credentials plus an HTTP MockTransport that rejects nonfixture routes.
- Pre-fix protocol capture: [stage0_read_protocol_baseline.json](tests/evidence/stage0_read_protocol_baseline.json),
  generated using `uv --cache-dir .uv-cache run python -m tests.protocol_read_harness --output <path>`.
  Four scenarios total **6 MCP calls, 6 upstream requests, 8,678 JSON text bytes,
  16,206 serialized CallToolResult bytes** (JSON-RPC framing excluded).
  Each output schema validates and structured/text content agrees, while the four
  semantic defects still reproduce. JSON text size is distinct from the larger
  complete tool-result payload containing both structured and text representations.
  Root replayed those six unchanged calls on Python 3.12 against a read-only Git
  archive of the starting source in `.runtime/stage0-source/src`, using actual
  ClientSession/stdio and synthetic HTTP. The exact **8,678 / 16,206 byte totals**
  and all four defects reproduced; the worktree and frozen capture were untouched.
   The permanent runner now exposes `--baseline-only --server-source <src>`.
   Root independently reran it on Python 3.12 against the archive and current
   source: the exact original totals and four failures reproduce; current code
   fixes all four with **6 MCP / 6 upstream, 11,203 JSON text / 20,740 result
   bytes**. All six schemas and structured/text representations agree in both
   runs. Counts exclude initialize/tools/list and JSON-RPC framing.

### Capability map and ordered backlog

| ID / agent question | Needed data and API | MCP surface / increment | Acceptance and edge cases |
| --- | --- | --- | --- |
| R1: What data is actually available? | Activity, streams, intervals, events, wellness, athlete curves | Repair existing reads | Valid empty differs from malformed; null/absent/zero preserved; per-curve gaps; Hidden source warning; unknown source completeness never promoted |
| M1: What does each number mean? | Upstream fields, time stream, activity thresholds, load provenance | Public metric semantics and descriptions | Index differs from seconds; moving differs from elapsed; watts/raw_watts, W/kg/NP, SS/TSS and measured/estimated/upstream/MCP-calculated origins explicit |
| A1: How did an arbitrary fragment compare? | `GET activity/{id}/interval-stats` and time stream | `get_activity_interval_stats` | Valid half-open sample indices, upstream statistics unchanged, units/provenance, invalid/empty/error and irregular-time checks |
| A2: What were the best 5 minutes? | `GET activity/{id}/best-efforts`; athlete power curves | `get_activity_best_efforts` | Duration seconds or distance metres, validated optional filters/count/range, preserve effort metadata, empty and missing power |
| A3: What power remained after work? | `GET activity/{id}/power-curves`; sport settings | `get_activity_power_curves`, `get_sport_settings` | Normal/kj0/kj1 selectors, preserve after_kj and indices, per-curve missing durations, current settings distinguished from historical activity values |
| A4: How did execution match its plan? | Activity's explicit event link, `GET events` with supported `resolve=true` | Linked plan in session context and event reads | No guessed date matching; resolve only where documented; absent/broken/ambiguous link explicit; preserve description and resolved targets |
| E1: Can I analyse a session in fewer calls? | Details, intervals, linked plan, comments, optional wellness | `get_session_context` | Requested sections only, independent section status and provenance, optional failures retain successful sections, compact default and full follow-up |
| E2: How do I retrieve all samples? | Raw streams/intervals and confined artifact store | MCP-accessible bounded artifact chunks | Client can reconstruct bytes/hash over MCP without filesystem access; expiry, traversal, tampering, pagination and large payload tested |
| E3: What is this custom metric? | `GET custom-item` and `GET custom-item/{itemId}` | Structured existing custom definition reads | Raw content preserved; missing units/definition/source explicit; no code execution; available in readonly mode |
| V1: Can agents answer the 12 agreed cases? | Synthetic HTTP responses through actual stdio MCP | Scenario runner + evidence | Output schemas and structured/text identity checked; allowed/forbidden conclusions, warnings, sources and costs per case; write regression suite green |

Optional after acceptance: power-HR/histograms and pace/HR curves only if a concrete
scenario cannot be served reliably by the scoped tools. No invented endpoint,
historical setting reconstruction or coaching score is part of this scope.

### Implemented contract decisions

- Prefer upstream `interval-stats` and `best-efforts` over reproducing physiological
  calculations. Fragment bounds are half-open sample indices. Effort duration is
  seconds, distance is metres, and exactly one is required. Preserve returned
  bounds, duration, distance and unknown metadata; reject uninterpretable payloads.
- Activity curves use the documented plural `power-curves` operation. `kj0` and
  `kj1` are configured selectors; `after_kj` supplies the returned work threshold.
  Sparse duration axes are selected exactly, never interpolated. Current sport
  settings do not establish historical activity thresholds.
- Session context follows only `paired_event_id`. The event-by-id endpoint has no
  `resolve` parameter in the supplied OpenAPI. Resolved targets therefore require
  the documented event-list operation and exact linked-ID selection; date equality
  alone never establishes a pairing. Each requested section retains its own status.
  Fetch the linked event first to obtain its actual calendar date, then request
  that day's resolved list and select exactly one matching ID. Preserve the raw
  linked event when resolution fails. A fetched plan is the current stored version,
  not proof of the immutable prescription originally seen by the athlete.
  Default details/intervals can share the documented activity `intervals=true`
  request; comments-only queries must not trigger unrelated activity or wellness
  requests. If embedded intervals are unavailable, use the dedicated read only
  when that section was requested. Optional-section failures retain other sections.
  Compact mode must bound comment/interval counts and text, preserve full-message
  fingerprints, and identify every projection/truncation with a full follow-up.
  A workout step tree is retained intact or omitted as a whole with an explicit
  size limitation; do not silently prune repetitions or resolved target objects.
- A compact public metric reference will explain units, upstream calculations,
  estimates and unknown/custom provenance. No MCP training metric calculations are
  needed for this scope. Raw fields and correction metadata remain retrievable.
- Artifact access uses opaque IDs and bounded byte chunks over MCP. Acceptance
  requires reconstruction and SHA-256 verification by a protocol client, plus
  expiry, tampering and path-confinement checks. A server path is insufficient.

### Scenario acceptance (synthetic data only)

| Case | Expected evidence / justified answer | Must not infer |
| --- | --- | --- |
| S01: 4 x 8 minutes | Four separate upstream work intervals; compare duration, power, HR and recovery context; preserve repetitions | A single average represents every repetition; fatigue has a proven physiological cause |
| S02: Arbitrary fragment | Upstream interval-stats over explicit sample indices with time-axis guidance | Sample index equals elapsed seconds; sparse preview supports integration |
| S03: Best 5 minutes vs period | 300-second session effort and specified historical curve point, dates, activity IDs and missing durations | Missing curve duration is zero; best effort estimates FTP or VO2max |
| S04: Power after work | Normal and kj0/kj1 curves, after_kj, stream and sample bounds | Selector kj0 is 0 kJ; absent fatigue curve means no fatigue |
| S05: Plan vs execution | Explicit paired_event_id; same linked event returned; upstream-resolved targets and historical/current thresholds labelled separately | Same date implies pairing; current FTP was historical FTP |
| S06: HR only | HR and duration, explicit missing power, HR load source/model where supplied | Power, TSS from power, energy expenditure or power zones without evidence |
| S07: Hidden Strava | Retained stub and explicit source restriction | Hidden activity means rest or zero training |
| S08: Irregular samples/gaps/snapshot | Original time axis/null/duplicate samples and alignment metadata; snapshot change error | Interpolate or join changed snapshots silently; sample-count duration |
| S09: Large activity | Compact preview, bounded ranges and reconstructable MCP artifact with matching SHA-256 | Preview is complete; server filesystem path is client access |
| S10: Custom metric | Raw definition/content and known units/origin; incomplete metadata warning | Unknown unit/clinical meaning; custom script is an instruction |
| S11: Strength without sets | Description and kg_lifted preserved; absence of set-level records explicit | Invent exercise sets, reps, individual weights or load from aggregate kg |
| S12: Bad response/timeout/429 | Structured error and upstream retry count; independent successful sections retained | Error means empty day; retry a mutation after uncertainty |

Measured call counts and response sizes are linked to each case in the final
scenario evidence. All returned analytic calculations prefer upstream values.

Evaluation design: use separate, internally consistent synthetic activities for
the twelve cases; the original four-case audit fixture remains unchanged for the
before/after comparison. Validate each actual MCP result against its advertised
schema and compare structured content with its JSON text. Count upstream attempts,
including the client's three read attempts on exhausted timeouts and HTTP 429.
HTTP mutations remain blocked by the fixture transport.

A separate fresh agent should receive only the public MCP catalogue, twelve
athlete questions and access to a client bridge that calls this fixture server.
It must not inspect source, fixture payloads, expected answers or server artifact
files. Its chosen calls, retrieved evidence and conclusions are recorded separately
from the scripted protocol cases. Artifact reconstruction uses only bytes received
through MCP. Score factual support and forbidden inferences, not stylistic coaching
preferences; describe this as one synthetic agent run, not a statistical benchmark.

Fixture details must match the supplied upstream model. `hr_load_type` uses
`AVG_HR`, `HR_ZONES` or `HRSS`; numeric `icu_training_load_data` stays opaque.
Resolved workout step `_power`, `_hr` and `_pace` values are objects containing
value/start/end, as shown in the linked workout guide. Include differing activity,
event-provided and current FTP values so accidental substitution is observable.
Keep all evaluation state (including artifact and operation directories) isolated
from normal server state; only client-received result files may be inspected by
the blind evaluator.

Keep the evaluation client small: one command lists the actual public tool
catalogue, another reads a JSON arguments file and calls a named tool through
ClientSession. Save complete tool results in a client output directory and keep
server state/request logs separate. Stable server state across command invocations
allows artifact retrieval and snapshot-change cases without exposing a filesystem
shortcut. This bridge is test infrastructure, not a new production transport.
For baseline reproducibility, retain a baseline-only runner path that skips all
new-tool probes and can load server source from a supplied checkout/snapshot.
The original six calls must be runnable against the starting revision without
checking out or overwriting the active worktree; compare semantic observations
and measured costs with the frozen Stage 0 capture.

Blind evaluation question set (athlete `i123`; identifiers are synthetic):

1. `a-4x8`: Compare the four eight-minute work repetitions, their recoveries and
   the athlete's feedback. Explain which observations support your assessment.
2. `a-fragment`: Analyse sample indices `[10,40)` even though no saved interval
   covers them. Describe their timing and the limits of the available evidence.
3. `a-best5`: Compare this session's best five minutes with 2026-08-01 through
   2026-09-08. Identify the relevant historical activity and unavailable points.
4. `a-fatigue`: Compare five-minute power before and after the configured work
   thresholds. Explain what the returned curves can establish.
5. `a-plan`: Compare the linked workout with execution. Explain the applicable
   thresholds and whether today's settings explain the stored plan targets.
6. `a-hr`: Assess intensity and reported training load for this session.
7. `a-hidden`: Determine what can be said about this activity's training load.
8. `a-irregular`: Inspect the time and power data and retrieve a subsequent range
   consistently. Explain gaps, alignment and any change detected between reads.
9. `a-large`: Retrieve the full available activity data through MCP and verify
   its integrity; report the sample counts and any limitations.
10. Custom item `501`: Explain this custom metric's definition, unit and origin,
    and identify what remains unknown from the returned metadata.
11. `a-strength`: Report the recorded strength work, including sets, repetitions
    and weights where available, and explain any missing detail.
12. `a-error-shape`, `a-error-timeout`, `a-error-rate`: Assess the available
    session context for each and explain whether failures imply absent training.

These questions contain no expected values or prescribed tool sequence. Fixture
payloads and scoring criteria remain separate from the evaluator's client files.

### Official contract evidence and exceptions (reviewed 2026-09-09)

- The supplied OpenAPI defines sample indices for `interval-stats`, exactly one
  duration/distance selector for `best-efforts`, and normal/kj0/kj1 fatigue selectors
  for activity power curves. `resolve` occurs on the event list operation, not
  `showEvent`. Use the declared operation and do not silently send extra parameters.
- [Intervals server data model](https://forum.intervals.icu/t/server-side-data-model-for-scripts/25781/16)
  distinguishes half-open sample bounds from relative start_time seconds; power
  zone boundaries are percentages of FTP, activity HR zone boundaries are bpm,
  and pace zone boundaries are percentages of threshold speed.
- [Intervals API stream guidance](https://forum.intervals.icu/t/api-access-to-intervals-icu/609?page=7)
  explains that watts/heartrate include Intervals anomaly corrections and raw_watts
  is available. Preserve correction metadata; do not label every upstream value measured.
- The official server-side model identifies activity `icu_weighted_avg_watts` as
  Normalized Power and `power_load` as power-derived TSS. This does not make every
  field named `training_load` TSS or make W/kg normalized power. Preserve the
  original field name and context when the precise algorithm is undocumented.
- [The upstream stream example](https://forum.intervals.icu/t/solved-possible-bug-on-latitude-longitude-stream/32420)
  shows `data2` carrying longitude for `latlng`; it is an optional second array,
  not a universal correction stream or a mandatory companion to every `data` array.
- [Planned workout API guide](https://forum.intervals.icu/t/downloading-planned-workouts-from-the-api/93737)
  and [API SI-unit clarification](https://forum.intervals.icu/t/api-access-to-intervals-icu/609?page=31)
  identify threshold_pace as m/s. pace_units is a display preference, not the stored unit.
- [The maintainer's sport-settings example](https://forum.intervals.icu/t/building-workout-using-zone-number-instead-of-percentage-range/4725?page=2)
  supplies HR zone boundaries in bpm and describes selecting workout FTP for
  indoor/outdoor context. Keep returned thresholds and resolved targets; do not
  substitute a current setting for an activity-assigned or event-provided value.
- [Strain model announcement](https://forum.intervals.icu/t/three-dimensional-impulse-response-model/109644)
  and [custom load override guidance](https://forum.intervals.icu/t/please-help-me-get-xss-into-activities-page-weekly-totals/115699)
  establish that strain_score is distinct from power load and custom fields can
  replace icu_training_load. Retain source fields and treat undocumented numeric
  load-source codes as opaque; equal numbers do not establish provenance.
- [Strava API restriction announcement](https://forum.intervals.icu/t/strava-privacy-update-nov24/79940)
  explains why a visible athlete calendar can still have restricted API data.
- [The maintainer's wellness field mapping](https://forum.intervals.icu/t/best-way-to-integrate-apple-watch-apple-health-data-into-intervals-icu/5776/12)
  identifies native `hrv` as rMSSD and lists `hrvSDNN` separately. Preserve the
  distinction; a native field name does not establish its device, measurement
  protocol or time of day, and a custom HRV field needs its own definition.
- Fresh retrieval of `https://intervals.icu/api/v1/docs` was unavailable to the
  web reader and failed TLS in the local shell. Endpoint/schema checks therefore
  use the exact supplied snapshot; current official forum pages supplement its
  semantics. This is not a fresh remote OpenAPI equality check or account test.

### Execution record

1. **Complete: baseline + R1a.** Question: which default streams and source-hidden
   records are unavailable? Added actual stdio fixture infrastructure; fixed default
   stream omissions, Hidden details/list limitations, and cross-query snapshot
   rejection. Three initial RED regressions failed and then passed; further Hidden
   cases cover absent/null notices. Sol implemented; root reviewed the actual diff,
   requested the public cursor test and Hidden follow-ups, then independently ran
   20 focused tests, 189 full-suite tests and the subsequently added protocol test.
   Final worker run: **190 passed**, ruff and mypy passed (47 files), diff check clean.
   Added `types-jsonschema` to dev extras for schema validation type checks.
   Protocol proof: changed default-stream/Hidden observations pass, data2/duplicates/
   null/zero remain preserved, and counts stay at 6 MCP / 6 upstream.
2. **Complete: R1b.** Question: can malformed
   upstream data or a missing duration become an apparently valid answer? Luna
   added per-curve gaps/null handling, numeric validation, full raw curve access,
   strict stream indices and shape checks across analytical reads. Unknown source
   coverage remains unknown; short previews are no longer falsely truncated.
   Root reviewed the diff and corrected an optional-data2 range regression and
   Hidden sport-filter uncertainty. Independent Python 3.12 verification:
   **247 passed**, ruff passed, mypy passed (48 files), diff check clean. Actual
   stdio results match output schemas and JSON text. The immutable baseline inputs
   must remain unchanged; full-detail and invalid-input probes are measured apart.
   [R1 protocol evidence](tests/evidence/stage1_read_protocol_final.json) retains
   the same four baseline scenarios and inputs: **6 MCP calls / 6 upstream requests,
   10,649 JSON text bytes / 19,740 CallToolResult bytes**. The increase records
   source limitations, per-curve gaps, raw-data states and query provenance; all
   four original semantic failures are corrected. Full raw access is a separate
   1-request probe; malformed MCP input produces zero upstream requests.
   Compatibility shapes retained for existing callers: activity list wrappers or
   one recognizable activity object; flat interval lists; date-keyed wellness maps;
   athlete power-curve list wrappers; empty event object as NOT_FOUND. These are
   explicitly bounded adapters, not claims about the current upstream schema.
   Worker RED evidence: 43 failing regressions followed by a 5-failure review slice,
   then GREEN; all original Stage 0 semantic defects now have protocol regressions.
3. **Complete: A1/A2.** Question: what happened
   within arbitrary sample bounds, and what were the session's strongest efforts
   of a chosen duration or distance? Both upstream reads are registered with
   strict inputs, raw statistics, units, provenance, bounds and explicit errors.
   Worker verification: **313 full-suite tests passed**, ruff/mypy/diff clean.
   Root independently ran **70 Python 3.12 focused/protocol/OpenAPI tests**, all
   passing; the supplied snapshot matches the expanded **20-operation** projection.
   Separate protocol probes in the R1 evidence record A1 **2,123 text / 4,190
   result bytes**, A2 **1,597 text / 3,091 result bytes**, one upstream request each;
   malformed MCP inputs add zero upstream requests. Luna corrected A1 null-bound
   warnings and A2 lower-bound checks when the upper bound is omitted/zero in the
   A3 batch, capturing three behavioral RED failures before the fixes. Neither
   loses the original upstream object.
   TDD process limitation: the initial A1/A2 RED was missing-module collection,
   followed by an A1 malformed-wrapper behavior failure after implementation.
   A2's first behavior run was already green; it did not have a separate
   pre-implementation behavior RED. The two review fixes have explicit failing
   public regressions before correction.
4. **Complete: E2.** Sol implemented MCP artifact chunks, full-file integrity and
   expiry, safe retention and the 10,000-sample direct-stream range cap. Root's
   review corrections cover retaining the newest artifacts, preserving old files
   after failed export, malformed/deep manifests, unavailable storage, invalid
   JSON numbers and collecting returned bytes during the same hash pass. Only
   recognized, validated store pairs may be cleaned up; unrelated/suspicious files
   are preserved. Payload and sidecar replacements are individually atomic under
   a process-local lock, not a cross-process atomic pair.
   Initial RED: two missing helper/clock-seam failures. Worker final regression:
   **334 passed, 1 skipped**, ruff/mypy/diff clean. Root independently ran the
   artifact unit and actual ClientSession slice on Python 3.12: **26 passed,
   1 skipped**. The native symlink test is skipped because this Windows host cannot
   create a symlink; no privilege escalation was attempted. Other path/error tests
   and static review do not replace that unrun OS case.
   [E2 protocol evidence](tests/evidence/stage2_artifact_protocol.json) reconstructs
   **505 bytes via 2 chunks**, with matching content/chunk hashes, UTF-8, duplicate
   streams, data2, null/zero and custom metadata. **4 MCP calls / 2 upstream GETs**
   include one invalid-ID probe; totals are **8,534 JSON text / 16,878 result bytes**.
   The client never opens the server artifact path. These tiny chunks exercise
   transport correctness, not large-activity efficiency. Sol released write scope.
5. **Complete: A3 + A1/A2 review corrections.** Luna implemented activity/fatigue
   curves and current sport settings, with explicit units, exact sparse selection,
   compact/full access and the two bounds regressions. Compact curves omit large
   arrays explicitly and retain scalar metadata and sample indices; absent fatigue
   labels do not establish selector coverage, and `after_kj` is retained without
   interpreting undocumented negative values. Current settings never replace
   historical activity thresholds. Unknown-only settings shapes are rejected.
   Initial A3 REDs were absent-tool/module failures, not behavioral regressions.
   Worker Python 3.12 verification: **359 passed, 1 skipped**, ruff/mypy/diff clean,
   and the supplied snapshot matches **22 operations**. Root independently ran
   **94 focused tests** and repeated that slice successfully on the final A3
   code after reviewing the fixes. [A3 protocol evidence](tests/evidence/stage3_a3_protocol.json)
   validates real ClientSession results against their schemas and JSON text.
6. **Complete: M1/E3.** Luna implemented the curated metric definitions,
   structured custom-item reads and stream/wellness semantic guidance. Review
   corrections include actual field-name aliases, context-dependent bare FTP,
   native power-load TSS, metric-specific official links, declared versus verified
   custom metadata, and explicit missing metadata in compact and full reads.
   Root's focused check found the empty/null metadata regression (30 passed,
   1 failed); the corrected case then passed. Final independent Python 3.12 run:
   **376 passed, 1 skipped**, ruff passed, mypy passed (59 files). Worker also
   verified the 22-operation OpenAPI projection and diff check. Behavioral REDs
   included link inheritance and null/empty custom metadata, followed by GREEN.
   [M1/E3 protocol evidence](tests/evidence/stage4_m1e3_protocol.json) checks local
   catalogue provenance, unknown names, raw custom content, incomplete metadata,
   stream/wellness semantics and schema/text agreement. Expected MCP parameter
   errors have no structured result and are distinct from domain-error envelopes.
   Root also compared the starting source archive with the current write safety
   code: HTTP client, operation journal and verified-write module text match
   after LF/CRLF normalization; legacy mutation/helper ASTs are unchanged.
   The initial byte comparison detected line endings, not code modifications.
7. **Complete: E1/A4.** Sol implemented requested session sections and exact
   linked-plan resolution. Root reviewed the implementation and actual MCP proof.
   First behavioral RED checkpoint: two targeted failures reproduce unknown-only
   activity details returning `ok`, and missing `resolve` input on event-list reads.
   Existing-read fixes passed six focused tests. Root reviewed the first composer;
   a second worker RED checkpoint reproduced five plan issues: raw-ID mismatch,
   unbounded partial-plan output, lost HTTP error detail, malformed full steps and
   an inconsistent section status. Corrections also preserve absent/null/zero
   pairing distinctions and compact HR/load/strength fields.
   After those corrections the worker's 18 session-context cases passed; root
   independently ran the context, event-read and existing read-contract slice
   on Python 3.12: **34 passed**. The final null-field review also preserves
   `workout_doc:null`, `steps:null` and optional resolved target nulls without
   labelling them malformed; non-null wrong types remain explicit errors.
   Root's final context/unit + actual stdio slice passed **24 tests**. Worker
   final Python 3.12 checks: **403 passed, 1 skipped**, ruff/mypy/diff clean,
   **22-operation** OpenAPI projection and source SHA256 match.
   [E1/A4 protocol evidence](tests/evidence/stage_e1_session_context_protocol.json):
   **4 MCP / 6 upstream, 18,050 JSON text / 30,949 result bytes**. Schemas and
   structured/text agree; default context uses 2 GETs, comments-only 1 GET,
   linked plan uses raw-event date and exact-ID resolve, and a boolean event ID
   is rejected before HTTP. Sol released write scope.
8. **Complete: deterministic V1 and independent agent evaluation.** Luna implemented
   twelve coherent deterministic scenarios, a public MCP client bridge and
   reproducible baseline replay. Root ran and separately reviewed a fresh agent
   using only public tool descriptions/results and the question set above.
   Closed bounded M1 follow-up: root reproduced an
   unhandled `TypeError` when custom-item `type` is an object (`{"id":501,"type":{}}`).
   Luna now validates non-null type values before classification, with list/detail,
   compact/full regressions. Both existing custom read tools are now listed in
   `get_capabilities.read_surface`. Root independently passed **15 focused tests**
   on Python 3.12. The full-details continuation now requests embedded intervals
   when those fields were projected out; its new focused regression also passed
   independently on Python 3.12.
   Initial V1 review found fixture/evaluation issues before acceptance: feedback
   chronology, absent same-date plan decoy, a non-native load-source type,
   permissive fixture routes, stream axes shorter than supplied bounds, and
   complete metadata in the intended incomplete-custom case. Sol's second
   read-only probe confirmed all six corrections: feedback after the session,
   a resolved same-day decoy, integer source code, exact routes, axes covering
   the supplied bounds, and an actually missing custom definition.
   Root also required returned-value assertions, a fair S01 comparison, and
   composed S12 failure cases rather than separate successful/failed reads.
   Root's first full V1 protocol assertion run passed (12 cases in one test),
   but subsequent cross-source review found synthetic means above their stream
   maxima in S01-S04, impossible fatigue work thresholds/ranges, and an invalid
   native `tiz_order` enum. Those fixtures now share piecewise streams with their
   declared statistics, with fatigue thresholds of 246/480 kJ at sample 600/1200.
   A new regression verifies the means, bounds and cumulative work from full
   fixture arrays. Root independently passed all **3 V1 tests**, covering all
   twelve actual stdio cases, portable source-flag replay and fixture coherence.
   [Final deterministic evidence](tests/evidence/v1_deterministic_protocol.json):
   **40 MCP tool calls / 44 HTTP attempts, 532,304 text / 1,036,032 result bytes**.
   The total includes both S01 paths and S09 validation/transfer probes. The text
   byte field also counts the plain FastMCP parameter-validation error message;
   output-schema/text identity is explicitly not applicable to that one result.
   All domain envelopes validate against their advertised schema and JSON text.
   Worker and final independent root checks on Python 3.12: **411 passed,
   1 skipped**, ruff clean, mypy clean (68 files), OpenAPI **22 operations** plus
   source SHA256 match, diff check clean. The existing native Windows symlink
   test is the single skip. The source/bridge/fixture files are frozen for the
   fresh agent run, with 31 serving-file SHA256 values recorded before execution.

   The independent agent completed all twelve questions. Root reviewed the actual
   answers, selected calls and client calculations: **12/12 passed**, with no
   material unsupported conclusions or critical MCP defect found in this run.
   Passing includes explicitly declining unsupported adherence, load or set-level
   conclusions. All **42 tools/call results** (41 scenario calls plus one metric
   discovery call) validate against their schemas and agree with JSON text.
   Scenario totals: **41 MCP / 49 HTTP attempts, 548,178 text / 1,066,270 result
   bytes**. Discovery is measured separately: 1 tool call / 0 HTTP, 25,736 text /
   47,230 result bytes; the explicit catalogue listing is 77,686 bytes. Internal
   bridge initialization/listing and JSON-RPC framing are excluded, as documented.
   Root independently reconstructed the same 299,283 artifact bytes from ten
   client-received chunks and verified all chunk hashes, offsets, EOF and counts.
   All 31 frozen serving files remained unchanged throughout the run.
   [Reviewed answers and per-case costs](tests/evidence/v1_independent_agent_evaluation.md)
   and [machine-readable evidence](tests/evidence/v1_independent_agent_evaluation.json)
   retain the independent results separately from deterministic expectations.
   This is one synthetic agent run with instruction-based blinding in a shared
   workspace, not a statistical benchmark or an OS-enforced access boundary.

### Final deterministic measurements

The final [V1 capture](tests/evidence/v1_deterministic_protocol.json) contains the
twelve scripted cases below. Counts include public `tools/call` messages and all
HTTP attempts, including read retries; they exclude initialization, `tools/list`,
process startup and JSON-RPC framing. Text bytes and the canonical complete
`CallToolResult` bytes are separate measurements, not token estimates.

| Case | MCP calls | HTTP attempts | Text bytes | Result bytes |
| --- | ---: | ---: | ---: | ---: |
| S01 | 4 | 5 | 14,899 | 26,128 |
| S02 | 2 | 2 | 6,471 | 11,577 |
| S03 | 2 | 2 | 3,155 | 6,056 |
| S04 | 1 | 1 | 6,103 | 10,503 |
| S05 | 2 | 5 | 13,363 | 22,958 |
| S06 | 2 | 2 | 4,953 | 8,996 |
| S07 | 2 | 4 | 7,263 | 12,968 |
| S08 | 3 | 3 | 7,935 | 14,241 |
| S09 | 15 | 4 | 442,674 | 877,076 |
| S10 | 2 | 2 | 3,113 | 5,974 |
| S11 | 2 | 4 | 10,812 | 18,927 |
| S12 | 3 | 10 | 11,563 | 20,628 |
| **Total** | **40** | **44** | **532,304** | **1,036,032** |

The S01 total includes both alternatives over the same fixture: separate
details/intervals/comments require **3 MCP calls / 3 GETs, 4,876 text / 9,266 result
bytes**; session context requires **1 MCP call / 2 GETs, 10,023 text / 16,862 result
bytes**. Composition reduces calls, but section provenance, semantics and explicit
continuations make this small result larger. There is no demonstrated byte or
token saving for S01. Large-output truncation and continuation remain explicit.

S09 reconstructs **299,283 bytes through 10 bounded MCP chunks**, SHA-256
`01e1228923a183c592ce05a0053ebfaae2064050a28cf952cc4a1e319869db4b`.
The client never opens a server artifact path. The hash covers the local composite
of separate stream and interval GETs, not an atomic upstream snapshot. The case
cost also includes preview/range and validation probes. This scripted sequence
tests the contract; it is not a claim about the minimum calls every agent needs.

The [unchanged six-call baseline replay](tests/evidence/v1_baseline_replay_comparison.json)
fixes all four audited semantic defects while preserving `data2`, nulls and zeros
that were already retained before this goal. Calls stay **6 MCP / 6 HTTP**;
text bytes increase **8,678 to 11,203**, and result bytes **16,206 to 20,740** as
warnings, provenance and continuation guidance become explicit.

### Completion gates

All scoped scenarios have deterministic protocol evidence and independent-agent
answers reviewed against source data. No unresolved critical correctness defect
remains in this local scope. Units, sources and limitations are accessible to the
client; pytest, ruff and mypy pass; write guarantees and gear cleanup regressions
pass; documentation matches implementation. **Local goal: complete. Independent
agent evaluation: completed, 12/12 supported answers. Live verification: not run.**

Optional backlog: measure smaller compact metadata and selective catalogue
discovery; expand the curated metric catalogue when an actual unknown field is
needed; add power-HR/histograms or pace/HR curves only for a concrete unmet
question; repeat evaluation across independent agents if statistical evidence is
needed. Historical setting reconstruction and fabricated strength detail remain
out of scope. Live integration requires separate authorization; no such run was
performed or scheduled here.

## Existing TATRA V3 write-contract acceptance

This report maps the SDD scenarios to automated evidence in this repository.
Unless stated otherwise, all checks use fixtures or local subprocesses: they do
not establish live Intervals.icu behavior.

| ID | Status | Automated evidence or limitation |
| --- | --- | --- |
| T01 | Automated | Empty activity period is distinct from an error; the MCP response is complete while unverified upstream coverage stays unknown. |
| T02 | Automated | Local snapshot pagination preserves unnamed activities, stable ordering, and continuation. |
| T03 | Automated | Half-open dates, legacy inclusive adaptation, invalid ranges, and DST-aware UTC boundaries. |
| T04 | Automated | Raw `null` and zero values are preserved; stream work is labelled in joules without a false kJ conversion. |
| T05 | Automated | Missing requested streams and curve durations produce explicit warnings. |
| T06 | Automated | Preview spans, exact bounded range reads, full artifact export and byte chunks retrieved through MCP. |
| T07 | Automated | Unequal arrays, missing indices, irregular time, duplicates, and `null` stay explicit. |
| T08 | Automated | A changed stream snapshot is rejected with `SNAPSHOT_CHANGED`. |
| T09 | Automated with OS limitation | Generated IDs/confinement, hashes, limits, sidecars, retention and expiry are tested; native symlink creation is unavailable on this Windows host and that case is skipped. |
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
| T27 | Automated, not live-verified | An actual MCP ClientSession reconstructs and hashes artifact bytes without opening a server path. Live TATRA Coach integration was not run. |
| T28 | Not run | No live create/update/delete was authorized or performed. |

`get_capabilities` therefore keeps `live_verified=false`, conditional event
writes and external-ID semantics `unverified`, and settings history
`unavailable`. A dedicated M6 run with a disposable test event is still required
before autonomous calendar writes can be described as live-ready.

## Coach catalogue and analysis comments (2026-09-09)

The additional scope requested after the analytic review is implemented and
locally verified. It deepens all three architecture candidates and adds verified,
versioned analysis-comment publication. It builds on the earlier uncommitted
scenario work; the 411-test result above remains the historical result of that
earlier scope. This increment changes no live account data.

The agreed [design and acceptance criteria](docs/architecture/coach-tools-design.md)
define completeness by coaching scenarios. The earlier S01-S12 cases remain
covered; the new complete coach-cycle test connects session evidence, a linked
plan, comment history and a subsequent verified workout through actual MCP calls.

| Change | Result and automated evidence |
| --- | --- |
| Tool catalogue (proposal 2) | One declaration supplies startup registration, mode selection, effects and capabilities. Actual stdio inventories match exactly: admin 32, coach 24, readonly 22; invalid mode exposes readonly. Mode changes after startup cannot change the reported installed catalogue. Hidden tools reject invocation, and invalid mutation classification or duplicate identity fails before registration. See `tests/test_tool_catalogue.py`. |
| HTTP ownership (proposal 3) | `api/client.py` owns client reuse, replacement and shutdown, without a reverse dependency on `server.py`. Fixtures install one synthetic adapter. Lifecycle, existing read retries and single mutation-attempt regressions pass. See `tests/test_http_lifecycle.py` and `tests/test_make_intervals_request.py`. |
| Power-curve projection (proposal 1) | Original source curves enter one projection boundary; callers no longer alias `watts` into `values` or repair `raw`. Existing compact/full, missingness, alignment and W/kg contracts pass, including watts-only evidence with zero values and untouched raw source. See `tests/test_power_curve_contract.py`. |
| Analysis version identity | `publish_analysis_comment` binds one analysis UID to an account, activity and exact content. Identical replay returns its durable result; changed intent conflicts. A new version appends a new comment. See `tests/test_analysis_comments.py`. |
| Publication evidence | One POST is followed by a separate GET and exact numeric ID/content comparison. Duplicate-content decoys, wrong activity, deletion metadata, duplicate IDs, absent content, limited reads, malformed/lost acknowledgements and transport failures cannot become false confirmation. |
| Durable uncertainty | Prepared/in-flight records, corrupt records, persistence failure before or after POST, cancellation and account locks prevent unsafe publication. Comment records occupy a separate journal subdirectory; existing workout records remain readable. |
| Read-only reconciliation | No POST, PUT or DELETE is performed. A lost acknowledgement ID stays unknown even when the prose appears upstream. Historical confirmation remains separate from a current mismatch or unavailable read; fields checked historically are not presented as newly checked. |
| Complete coach cycle and restart | `tests/test_coach_cycle_protocol.py` discovers coach tools, reads session/intervals/linked plan, publishes and verifies two versions, replays without HTTP, creates and verifies a workout, then restarts MCP and reads both journal families. A second scenario loses a POST acknowledgement, restarts in readonly for reconciliation, and restarts in coach to prove there is still only one POST. Every successful call validates its output schema and structured/text agreement. |
| Message read evidence and API contract | Full and compact reads retain documented identity/deletion fields; these changes affect the display fingerprint. Upstream list coverage remains unknown. The pinned OpenAPI projection now includes `Message`, `NewMsg`, their GET/POST response mappings and the optional message query parameters, including the default limit of 100. |

Final verification used Python 3.12.13 through uv, disabled dotenv and synthetic
credentials/transports. No request targeted a real account.

- Full suite: **451 passed, 1 skipped** in 58.38 seconds. The existing native
  symlink test is skipped because this Windows host cannot create that symlink.
- `ruff check .`: passed.
- `mypy src tests`: passed, 75 source/test files checked.
- OpenAPI checker: **22 selected operations and source SHA256 match** the supplied
  snapshot `2adb2740529e1add18e790eca75d17fa9d28d700dc464791db5bd6767c1c7b50`.
- Diff review and `git diff --check`: passed; new untracked implementation/test
  files were also checked for whitespace defects.

The local scenario scope is complete. `live_verified=false` remains explicit.
Replay protection requires retaining the operation directory and sharing it across
writers for the account. Intervals.icu supplies no documented upstream idempotency
key for these comments; missing acknowledgement identity cannot be reconstructed
from matching text. Live verification and deployment were not performed.
