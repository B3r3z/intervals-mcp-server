## Problem Statement

The live coach audit showed that useful Intervals.icu observations can be classified as incomplete for the wrong reasons. Optional secondary stream arrays trigger alignment failures, one unavailable fatigue selector hides valid power curves, and an explicitly unpaired activity is treated as an execution error. Recovery context requires several manual reads, while compact custom definitions omit the identifiers needed to request their data.

The coach needs a concise, evidence-preserving route from a completed session to trustworthy interpretation, without changing the athlete's account.

## Solution

Improve the existing read surface and add two focused reads: activity data quality and native power-versus-heart-rate analysis. Keep current defaults compatible, make additional context opt-in, preserve partial successes, and distinguish unavailable observations from malformed responses.

## User Stories

1. As a coach, I want optional null secondary arrays to be distinguished from missing primary observations, so that valid streams remain usable.
2. As a coach, I want genuine short or unequal arrays reported, so that I do not analyse missing samples as zeros.
3. As a coach, I want null, zero and absent stream values retained separately, so that missingness cannot change a conclusion.
4. As a coach, I want per-stream sample counts and null counts, so that I can assess coverage without transferring full arrays.
5. As a coach, I want time gaps, duplicate or reversed timestamps and irregular sampling identified, so that sample indices are not confused with seconds.
6. As a coach, I want recording stops reported separately from observed gaps, so that no unsupported cause is assigned.
7. As a coach, I want the available normal power curve preserved when another fatigue selector fails, so that optional configuration does not block basic analysis.
8. As a coach, I want each fatigue request's outcome and provenance, so that unconfirmed selector identity is explicit.
9. As a coach, I want missing selector echoes separated from missing power points, so that response completeness is meaningful.
10. As a coach, I want an explicitly unpaired activity represented as a normal fact, so that valid sessions do not appear broken.
11. As a coach, I want malformed or absent pairing identity distinguished from explicit null, so that ambiguity remains visible.
12. As a coach, I want an optional bounded wellness window before and after a session, so that I can inspect recovery context.
13. As a coach, I want all activities in that context available with pagination evidence, so that multiple recordings or other sports are not overlooked.
14. As a coach, I want contextual calendar events independently of workout pairing, so that races and availability notes inform interpretation.
15. As a coach, I want existing default context requests unchanged, so that clients incur no surprise historical reads.
16. As a coach, I want technical custom-field codes and FIT field declarations in compact responses, so that I can find a sensor without downloading scripts.
17. As a coach, I want documented native units and scale descriptions, so that I can interpret common fields consistently.
18. As a coach, I want unknown custom units and ambiguous activity HRV to remain unknown, so that plausible names do not become invented evidence.
19. As a coach, I want native power-versus-HR results including their time windows and HR lag, so that I can use the upstream analysis without silently reimplementing it.
20. As a coach, I want bounded compact power-versus-HR output and an exact full continuation, so that response size stays controllable.
21. As a client, I want structured failures and successful sections retained independently, so that one failed source does not discard other evidence.
22. As a maintainer, I want the discovered catalogue, compatibility imports and schemas to include the added reads in each mode, so that tooling stays consistent.
23. As an athlete, I want this work to use read-only account operations, so that evaluation and implementation do not modify my training.
24. As a maintainer, I want protocol regressions and a repeat live read, so that synthetic correctness and observed account behaviour remain separately documented.

## Implementation Decisions

- Preserve the versioned read envelope, source provenance, null/zero distinctions, snapshot semantics and existing write contracts.
- Keep stream observation quality in one reusable in-process module. Both the stream reader and dedicated quality tool use the same interpretation. Missing or null secondary arrays are optional; present secondary arrays still participate in alignment.
- Report finite-value counts, null/invalid counts, zero counts, array alignment and bounded time-gap diagnostics. Describe the algorithm and limits; no readiness score, physiological thresholds, interpolation or gap filling.
- The quality read obtains all returned upstream streams plus activity metadata. It reports recording stops and feedback availability as source facts. Failure of one source preserves usable results from the other.
- Request fatigue variants independently when more than one is requested, preserving source curves and a separate result per selector. Upstream errors remain redacted. An HTTP 422 is not labelled as a missing threshold unless verified by evidence; the response directs the caller to sport settings.
- Do not infer echoed selector identity from a curve ID or work value. Lack of an echo is a distinct verification state, not itself missing curve points; explicit contradictory selectors still degrade the result.
- An explicitly null paired-event ID produces an available unpaired fact. Missing or malformed identity retains the existing diagnostic distinction.
- Extend session context with optional activity-history and contextual-event sections and a bounded before/after window, defaulting to the current day. Keep the existing default section set and current plans separate from contextual events. Preserve pagination and exact continuation parameters.
- Retain custom technical codes and declared FIT record fields in a small content metadata object; never execute or interpret scripts as instructions.
- Extend descriptive native units and metric definitions only where supported. Activity HRV has a separate unknown-semantics definition; daily wellness HRV remains distinct.
- Add a native power-HR read using the documented power-versus-HR JSON endpoint. Preserve upstream numbers and unknown metadata; compact mode bounds series and curve payloads with explicit omissions and full continuation.
- Publication target is the repository's GitHub issue tracker, using the skill's ready-for-agent label. Keep an identical local spec when remote publication is unavailable.

## Testing Decisions

- Prefer the existing public tool/MCP boundary and existing controlled HTTP adapter. Do not add a new transport abstraction.
- Reproduce scalar streams with null data2, genuine missing primary data, shorter secondary arrays, zero values and irregular time axes through public read tools.
- Verify mixed successful/failed fatigue requests and echoed, absent and contradictory selector metadata.
- Verify explicit null pairing, malformed pairing, context date bounds across local days, pagination and independent section failures.
- Verify native power-HR empty, malformed, null, compact and full responses, including unknown-field preservation and unchanged upstream values.
- Check custom metadata without executing embedded content and verify catalogue/schema registration.
- Exercise one complete read scenario over MCP stdio, validate output schemas and ensure only upstream GET operations occur.
- Run pytest, ruff, mypy and the applicable OpenAPI contract checks. Repeat representative live read-only cases against the same completed activity; retain explicit live-verification limits.
- These seams use established protocol harnesses, stream/curve/context contract tests and the existing mock HTTP transport. The user was offered a check of these boundaries while independent work continued.

## Out of Scope

- Publishing or altering workouts, activity comments, athlete settings or sensor configuration.
- Inferring a workout pairing merely from date or title.
- Automated physiological conclusions, readiness scores, FTP/VO2 estimation or recommendations embedded in the connector.
- Automatic matching of planned steps to recorded efforts, complete strength/FIT extraction, weather and histogram tools. These remain separately scoped follow-ups.
- Changing global agent routing, adding an OpenSpec framework, committing, pushing or deploying.

## Further Notes

The implementation follows the preceding live audit and current official Intervals.icu API documentation. Synthetic fixtures use non-personal examples. Live records stay in ignored local runtime storage; issue text contains no athlete identifiers, credentials or personal workout results. Completion requires implementation and verification, not only this specification.

