# Intervals.icu MCP Server

Model Context Protocol (MCP) server for connecting Claude and ChatGPT with the Intervals.icu API. It provides tools for authentication and data retrieval for activities, events, wellness data, power curves, and custom items.

If you find the Model Context Protocol (MCP) server useful, please consider supporting its continued development with a donation.

## Requirements

- Python 3.12 or higher
- [Model Context Protocol (MCP) Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- httpx
- python-dotenv

## Setup

### 1. Install uv (recommended)

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installation, find the full path to `uv` — you'll need it later when configuring Claude Desktop:

```powershell
where.exe uv
# Example output: C:\Users\<USERNAME>\.local\bin\uv.exe
```

### 2. Clone this repository

```bash
git clone https://github.com/mvilanova/intervals-mcp-server.git
cd intervals-mcp-server
```

### 3. Create and activate a virtual environment

```bash
# Create virtual environment with Python 3.12
uv venv --python 3.12

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate
```

### 4. Sync project dependencies

```bash
uv sync
```

### 5. Set up environment variables

Make a copy of `.env.example` and name it `.env` by running the following command:

**macOS/Linux:**
```bash
cp .env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

Then edit the `.env` file and set your Intervals.icu athlete id and API key:

```
API_KEY=your_intervals_api_key_here
ATHLETE_ID=your_athlete_id_here
```

#### Getting your Intervals.icu API Key

1. Log in to your Intervals.icu account
2. Go to Settings > API
3. Generate a new API key

#### Finding your Athlete ID

Your athlete ID is typically visible in the URL when you're logged into Intervals.icu. It looks like:

- `https://intervals.icu/athlete/i12345/...` where `i12345` is your athlete ID

## Updating

This project is actively developed, with new features and fixes added regularly. To stay up to date, follow these steps:

### 1. Pull the latest changes from `main`

> ⚠️ Make sure you don't have uncommitted changes before running this command.

**macOS/Linux:**
```bash
git checkout main && git pull
```

**Windows (PowerShell):**
```powershell
git checkout main; git pull
```

### 2. Update Python dependencies

Activate your virtual environment and sync dependencies:

**macOS/Linux:**
```bash
source .venv/bin/activate
uv sync
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\activate
uv sync
```

### Troubleshooting

If Claude Desktop fails due to configuration changes, follow these steps:

1. Delete the existing `Intervals.icu` entry in `claude_desktop_config.json`.
2. Reconfigure Claude Desktop from the `intervals-mcp-server` directory.

**macOS/Linux:**
```bash
mcp install src/intervals_mcp_server/server.py --name "Intervals.icu" --with-editable . --env-file .env
```

**Windows:** Re-add the entry manually as described in the [Windows configuration section](#windows).

#### Common errors

**`spawn uv ENOENT`** — Claude Desktop cannot find the `uv` executable. Use the full path to `uv` in the `command` field. Run `which uv` (macOS/Linux) or `where.exe uv` (Windows) to get it.

**`spawn /Users/... ENOENT` on Windows** — The config file contains a macOS/Linux-style path. Replace it with the correct Windows path using backslashes as described in the [Windows configuration section](#windows) below.

**Windows Store install: config changes not taking effect** — You may be editing the wrong config file. Claude Desktop installed from the Microsoft Store reads from `AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`, not `AppData\Roaming\Claude\`.

## Usage with Claude

### 1. Configure Claude Desktop

To use this server with Claude Desktop, you need to add it to your Claude Desktop configuration.

#### macOS/Linux

1. Run the following from the `intervals-mcp-server` directory to configure Claude Desktop:

```bash
mcp install src/intervals_mcp_server/server.py --name "Intervals.icu" --with-editable . --env-file .env
```

2. If you open your Claude Desktop App configuration file `claude_desktop_config.json`, it should look like this:

```json
{
  "mcpServers": {
    "Intervals.icu": {
      "command": "/Users/<USERNAME>/.local/bin/uv",
      "args": [
        "run",
        "--with",
        "mcp[cli]",
        "--with-editable",
        "/path/to/intervals-mcp-server",
        "mcp",
        "run",
        "/path/to/intervals-mcp-server/src/intervals_mcp_server/server.py"
      ],
      "env": {
        "INTERVALS_API_BASE_URL": "https://intervals.icu/api/v1",
        "ATHLETE_ID": "<YOUR_ATHLETE_ID>",
        "API_KEY": "<YOUR_API_KEY>",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Where `/path/to/` is the path to the `intervals-mcp-server` code folder in your system.

#### Windows

The `mcp install` command may fail on Windows due to environment or permission issues. Instead, configure Claude Desktop manually:

1. Find the Claude Desktop config file. If Claude Desktop was installed from the **Microsoft Store**, the config is located at:

   ```
   C:\Users\<USERNAME>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
   ```

   If installed via the standard installer, it may be at:

   ```
   C:\Users\<USERNAME>\AppData\Roaming\Claude\claude_desktop_config.json
   ```

   If the file or folder does not exist, create it.

2. Add the following entry to `claude_desktop_config.json`, replacing the placeholders with your actual values:

```json
{
  "mcpServers": {
    "Intervals.icu": {
      "command": "C:\\Users\\<USERNAME>\\.local\\bin\\uv.exe",
      "args": [
        "run",
        "--with",
        "mcp[cli]",
        "--with-editable",
        "C:\\path\\to\\intervals-mcp-server",
        "mcp",
        "run",
        "C:\\path\\to\\intervals-mcp-server\\src\\intervals_mcp_server\\server.py"
      ],
      "env": {
        "INTERVALS_API_BASE_URL": "https://intervals.icu/api/v1",
        "ATHLETE_ID": "<YOUR_ATHLETE_ID>",
        "API_KEY": "<YOUR_API_KEY>",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

- Use double backslashes (`\\`) for all Windows paths in JSON.
- To find the full path to `uv.exe`, run `where.exe uv` in PowerShell.
- To find the full path to the cloned repository, run `pwd` from inside the `intervals-mcp-server` folder.

> **Note for Windows Store installs:** Claude Desktop installed from the Microsoft Store sandboxes its config under `AppData\Local\Packages\...`. Editing `AppData\Roaming\Claude\claude_desktop_config.json` will have no effect — make sure you edit the correct file.

3. Restart Claude Desktop.

### 2. Use the MCP server with Claude

Once the server is running and Claude Desktop is configured, you can use the following tools to ask questions about your past and future activities, events, and wellness data.

- `get_activities`: Retrieve a list of activities
- `get_activity_details`: Get detailed information for a specific activity
- `get_activity_intervals`: Get detailed interval data for a specific activity
- `get_session_context`: Compose requested session sections and optional wellness, activity-history and calendar context with explicit limits, provenance, and full-read follow-ups.
- `get_activity_streams`: Get compact stream previews by default; pass inclusive `start_index` and exclusive `end_index` together for exact full samples in a JSON range.
- `get_athlete_power_curves`: Get best power output curves for selected durations and time periods
- `get_activity_power_curves`: Read an activity's upstream watts curves; durations are seconds, curve indices are sample indices, and `detail="full"` preserves large raw arrays.
- `get_activity_interval_stats`: Read raw interval statistics for a half-open sample-index range; use the time stream to map indices to seconds.
- `get_activity_best_efforts`: Find upstream efforts by one duration-in-seconds or distance-in-metres selector without MCP FTP or VO2 calculations.
- `get_activity_data_quality`: Inspect every returned stream sample for numeric validity, alignment and time gaps, with independent recording metadata and feedback availability.
- `get_activity_power_hr`: Read native power-versus-HR analysis, including windows, lag and coefficients; compact output has an exact full-read continuation.
- `get_sport_settings`: Read current-at-fetch sport settings or a settings ID; FTP/power are W, W' is J, fatigue thresholds are kJ, heart rate is bpm, and threshold pace is m/s regardless of display pace units.
- `get_metric_definitions`: Read the local curated metric catalogue before interpreting streams, intervals, wellness, or custom definitions; unknown selectors remain explicit and no account data is fetched.
- `get_wellness_data`: Fetch wellness data
- `get_events`: Retrieve events overlapping a date range, including ongoing holidays, workouts and races
- `get_event_by_id`: Get detailed information for a specific event
- `add_or_update_event`: Create or update an event (workout, race, note, etc.)
- `delete_event`: Delete a specific event
- `delete_events_by_date_range`: Preview the exact event change set by default; deletion requires `confirm=true` and matching `expected_event_ids` from that fresh preview.
- `get_custom_items`: Get custom items (charts, custom fields, zones, etc.) for an athlete
- `get_custom_item_by_id`: Get detailed information for a specific custom item
- `create_custom_item`: Create a new custom item for an athlete
- `update_custom_item`: Update an existing custom item
- `delete_custom_item`: Delete a custom item

## Usage with ChatGPT

ChatGPT’s beta MCP connectors can also talk to this server over the SSE transport.

1. Start the server in SSE mode so it exposes the `/sse` and `/messages/` endpoints:

   ```bash
   export FASTMCP_HOST=127.0.0.1 FASTMCP_PORT=8765 MCP_TRANSPORT=sse FASTMCP_LOG_LEVEL=INFO
   python src/intervals_mcp_server/server.py
   ```

   The startup log prints the full URLs (for example `http://127.0.0.1:8765/sse`). ChatGPT needs that public URL, so forward the port with a tool such as `ngrok http 8765` if you are not exposing the server directly.

2. In ChatGPT, open **Settings → Features → Custom MCP Connectors** and click **Add**. Fill in:

   - **Name**: `Intervals.icu`
   - **MCP Server URL**: `https://<your-public-host>/sse`
   - **Authentication**: leave as _No authentication_ unless you have protected your tunnel.

   You can reuse the same `ngrok http 8765` tunnel URL here; just ensure it forwards to the host/port you exported above.

3. Save the connector and open a new chat. ChatGPT will keep the SSE connection open and POST follow-up requests to the `/messages/` endpoint announced by the server. If you restart the MCP server or tunnel, rerun the SSE command and update the connector URL if it changes.

## Development and testing

Install development dependencies and run the test suite with:

```bash
uv sync --all-extras
pytest -v tests
```

The deterministic V1 evaluation uses a real stdio `ClientSession` over a
synthetic `httpx.MockTransport`; it never reaches an Intervals account. Capture
the twelve scenarios and their private request/audit state with:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
uv run python -m tests.v1_scenario_harness `
  --output tests/evidence/v1_deterministic_protocol.json `
  --private-root .runtime/v1-deterministic-private
```

For a blind client, use the bridge with a separate persistent private state
directory. `list` writes the public tool catalogue; `call` writes the complete
MCP `CallToolResult` to the requested output path. Request logs, artifacts,
operation files, and byte/HTTP audits stay under `--state-dir`.

```powershell
uv run python -m tests.v1_client_bridge --state-dir .runtime/v1-blind-private `
  list --output .runtime/v1-tool-list.json
uv run python -m tests.v1_client_bridge --state-dir .runtime/v1-blind-private `
  --case S01 call get_session_context --args-file .runtime/args.json `
  --output .runtime/v1-result.json
```

The original six-call replay keeps its frozen inputs in
`tests/evidence/stage0_read_protocol_baseline.json`. Use the additive harness
flags to replay only those calls against either the current checkout or the
archived source without changing that baseline:

```powershell
New-Item -ItemType Directory -Force .runtime | Out-Null
git archive --format=zip --output=.runtime/stage0-source.zip `
  71381d42b2d9bae8c1f841cc55fd9b3ef3be0e53 src
Expand-Archive -LiteralPath .runtime/stage0-source.zip `
  -DestinationPath .runtime/stage0-source

uv run python -m tests.protocol_read_harness --baseline-only `
  --output .runtime/v1-baseline-current.json
uv run python -m tests.protocol_read_harness --baseline-only `
  --server-source .runtime/stage0-source/src `
  --output .runtime/v1-baseline-stage0.json
```

Create the archive directory once; an existing copy can be reused. This exports
source from Git without changing the checkout or index. Final local acceptance,
per-scenario costs and the independent agent evaluation are recorded in
[TATRA_V3_ACCEPTANCE.md](TATRA_V3_ACCEPTANCE.md); live verification is separate.

### Running the server locally

To start the server manually (useful when developing or testing), run:

```bash
mcp run src/intervals_mcp_server/server.py
```

### One shared Streamable HTTP server for TATRA_V3

If multiple Codex agents in the `TATRA_V3` project should use one MCP process,
run the server once as a Docker container. From the repository root in
PowerShell:

```powershell
uv sync --all-extras
Copy-Item .env.example .env
# Uzupełnij API_KEY i ATHLETE_ID w .env
.\scripts\start-mcp.ps1
```

The script builds the local image when needed, starts the named container, keeps
the runtime directory persistent, binds only to loopback, and waits until the
MCP port is accepting connections. It does not print secret values. The endpoint
is:

```text
http://127.0.0.1:8000/mcp
```

Normal invocation is idempotent: if the local MCP port is already accepting
connections, the script exits without rebuilding, restarting, or replacing the
container. Use `-Rebuild -Recreate` only when an explicit image update is
needed.

In the `TATRA_V3` project, use a project-local `.codex/config.toml` containing:

```toml
[mcp_servers.intervals]
url = "http://127.0.0.1:8000/mcp"
```

The Codex agents then connect to the already-running server instead of starting
their own STDIO processes or containers. After changing the image, recreate the
single container explicitly:

```powershell
.\scripts\start-mcp.ps1 -Rebuild -Recreate
```

Do not put `start-mcp.ps1` in the MCP server's `command` field. That field is for
a long-lived STDIO server process; this script is a separate HTTP bootstrap and
intentionally exits after ensuring the container is available. Run it before
Codex, at Windows logon, or from Docker Desktop startup, while Codex keeps only
the URL configuration above.

Keep the endpoint local: the current server does not provide separate inbound
HTTP authentication.

#### Enabling debug logging

To capture server logs for debugging, wrap the command in a shell and redirect stderr to a file.

**macOS/Linux** — modify your `claude_desktop_config.json` like this:

```json
{
  "mcpServers": {
    "Intervals.icu": {
      "command": "/bin/bash",
      "args": [
        "-c",
        "/Users/<USERNAME>/.local/bin/uv run --with 'mcp[cli]' --with-editable /path/to/intervals-mcp-server mcp run /path/to/intervals-mcp-server/src/intervals_mcp_server/server.py 2>> /path/to/intervals-mcp-server/mcp-server.log"
      ],
      "env": {
        "INTERVALS_API_BASE_URL": "https://intervals.icu/api/v1",
        "ATHLETE_ID": "<YOUR_ATHLETE_ID>",
        "API_KEY": "<YOUR_API_KEY>",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Then tail the log file to see output in real-time:

```bash
tail -f /path/to/intervals-mcp-server/mcp-server.log
```

**Windows** — modify your `claude_desktop_config.json` like this:

```json
{
  "mcpServers": {
    "Intervals.icu": {
      "command": "powershell",
      "args": [
        "-Command",
        "C:\\Users\\<USERNAME>\\.local\\bin\\uv.exe run --with 'mcp[cli]' --with-editable C:\\path\\to\\intervals-mcp-server mcp run C:\\path\\to\\intervals-mcp-server\\src\\intervals_mcp_server\\server.py 2>> C:\\path\\to\\intervals-mcp-server\\mcp-server.log"
      ],
      "env": {
        "INTERVALS_API_BASE_URL": "https://intervals.icu/api/v1",
        "ATHLETE_ID": "<YOUR_ATHLETE_ID>",
        "API_KEY": "<YOUR_API_KEY>",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Then monitor the log file in real-time using PowerShell:

```powershell
Get-Content C:\path\to\intervals-mcp-server\mcp-server.log -Wait
```

## License

The GNU General Public License v3.0

## Featured

### Glama.ai

<a href="https://glama.ai/mcp/servers/@mvilanova/intervals-mcp-server">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@mvilanova/intervals-mcp-server/badge" alt="Intervals.icu Server MCP server" />
</a>
# M1-M3 data contract

Read tools return the versioned Pydantic `ReadResponse` envelope (`schema_version`
`1.0`). Its JSON serialization is also the compatibility text representation;
clients should consume `structuredContent` and must distinguish `null`, missing
fields, and numeric zero. Date queries use a half-open interval: `start_date`
is inclusive and `end_date_exclusive` is exclusive, with an explicit timezone.

Large activity data is written only to the configured `INTERVALS_ARTIFACT_DIR`
(default `.runtime/artifacts`) by `export_activity_data`. Manifests include a
SHA-256 hash, snapshot, size, range, expiry, and local absolute path, never the
full samples. An MCP-only client can call `get_artifact_chunk` with the opaque
artifact ID, decode and concatenate the base64 byte chunks, verify the complete
SHA-256, and only then decode the UTF-8 JSON. A chunk can split a multibyte
character. The artifact combines separate stream and interval HTTP reads, so its
hash verifies local content rather than an atomic upstream snapshot; source
completeness remains unknown. With no stream-type filter, the export contains all
streams returned by the export request, including duplicate or custom streams.
Artifacts are temporary and should be re-created after expiry.

`get_activity_streams(mode="range")` accepts at most 10,000 sample indices per
call and rejects a larger range before requesting Intervals.icu. Use
`export_activity_data` and `get_artifact_chunk` for a larger complete transfer;
the range endpoint never silently trims the requested range.

Missing or null `data2` is optional for scalar streams. A present secondary array
still participates in alignment. `get_activity_data_quality(activity_id)` reads
all upstream streams and activity metadata independently, returning counts for
finite, null, invalid and zero samples, plus bounded time-gap examples. Gaps use
a one-second reference; duplicate, reversed and fractional time steps remain
explicit. Recording stops are separate upstream facts. No gap filling, sensor
diagnosis or readiness score is produced.

`get_activity_power_curves` requests each distinct fatigue selector separately.
`selector_results` retains each outcome when another variant fails. Missing
selector echoes remain unverified metadata; they alone do not make complete
power points partial. HTTP 422 directs the caller to inspect sport settings and
parameters without assuming its cause.

`get_activity_power_hr(activity_id)` preserves native Intervals.icu power-HR
results without recalculation. Compact mode retains at most 120 series rows and
eight curves, then omits whole fields if necessary to keep data within 32 KiB.
Omissions and `projection.full_read` are explicit; `detail="full"` preserves the
complete upstream JSON object. The returned analysis windows and HR lag must be
considered when interpreting its metrics.

Use `get_metric_definitions` as the local interpretation guide: it distinguishes
sample indices from seconds, elapsed from moving time, processed from raw watts
and heart rate, W/kg from Normalized Power, and upstream reported, calculated,
estimated, and unknown origins. Its catalogue is curated and non-exhaustive;
unknown selectors stay explicit and no account request is made. Stream alignment
is based on returned array lengths only, so null, duplicate, irregular, or
non-monotonic time values remain source data. Custom-item reads treat scripts and
descriptions as untrusted data: compact responses list omissions and provide a
full continuation, while full responses preserve parsed upstream fields and put
derived metadata warnings outside the raw item.
Compact custom items also expose declared `code`, `fit_record_field`, `type`
and units from content, without executing scripts. Activity `streams.hrv` has
unknown semantics and remains distinct from daily wellness HRV.

For respiratory data, `get_metric_definitions(names=["VT", "VE", "BR"])`
explains native fields, their interval averages and Tymewear FIT mappings.
`tidal_volume` is volume per breath; `tidal_volume_min` is minute ventilation;
`respiration` is breaths/min. When sourced from Tymewear, VT uses relative
`i.u.` and VE relative `vol/min`, with no supported universal conversion to
liters. VT is distinct from ventilatory thresholds VT1/VT2. Stream, interval-stat
and data-quality responses include conditional documentation under
`provenance.respiratory_interpretation`; samples and upstream unit declarations
remain unchanged. Device origin is not inferred from native names, and custom
`L/br` or `L/min` labels do not establish calibration. See the
[Tymewear documentation research](docs/research/2026-09-10-tymewear-tidal-volume.md)
for primary sources and the withdrawn `/100` conversion.

`get_session_context` fetches only requested sections. The default is activity
details with embedded intervals plus comments; a comments-only request does not
fetch activity details or require an athlete ID. Compact mode preserves upstream
order without claiming chronology and limits output to 20 comments, 100
intervals and 100 groups, 10 wellness rows, 4,000 characters per projected text
field, and a whole workout step tree of at most 32,768 UTF-8 bytes. A larger
step tree is omitted whole with a `detail="full"` continuation. Plan lookup
follows only a positive numeric `paired_event_id`, reads that raw event, derives
the event's own date, then selects exactly one same-ID row from the day's
`resolve=true` list. Failed resolution retains the raw event. The fetched plan
is the current stored version. Activity-assigned thresholds, stored event or
workout thresholds, and current sport settings remain distinct; this tool does
not fetch or substitute current settings.

An explicitly null `paired_event_id` is a successful `unpaired` fact. Optional
`activities`, `contextual_events` and `wellness` sections share a local-date
window controlled by `context_days_before` and `context_days_after` (0..31 each;
defaults are zero). For example, request seven days before and two days after
to inspect recovery context. Activities return 20 records per snapshot page;
compact events retain 20 records. Exact raw continuations retain the date
window, timezone and pagination cursor where applicable. Contextual calendar
events never establish a workout pairing.

`get_events` includes events that started before the requested window and are
still ongoing. The API selects event starts, so the default
`include_overlapping=true` fetches candidates from `0001-01-01` through the
requested end, without an upstream limit or category filter, then applies local
overlap selection. This avoids a fixed lookback missing a long holiday, but can
fetch more historical records than it returns. `end_date_local` is exclusive;
an event ending at midnight on September 21 does not overlap September 21.
Responses retain the requested window, expose `query.upstream_oldest` and
`overlap` selection counts, and preserve selected source records unchanged.
Missing or invalid boundaries that prevent deciding overlap retain unresolved
candidates with `partial` status and `EVENT_OVERLAP_UNRESOLVED`; unknown fields
such as `date` do not replace `start_date_local`. Source completeness remains
unverified. `get_session_context` uses the same selection for contextual events.
Explicit `include_overlapping=false` retains the API's original start-date
selection and is used internally to resolve an already identified paired event
on its exact start day.

`get_capabilities` reports implementation, configuration, and live verification
separately. No live Intervals account verification is claimed by fixture tests;
conditional writes, external-id semantics, and settings history remain
unverified/unavailable until a dedicated integration check.

## M4-M5 writes

`apply_workout_changes` accepts one or more intents and executes them
sequentially under one account lock. The package is not transactional: execution
stops at the first non-confirmed result and remaining operations are
`not_attempted`. Every mutation is journaled as `prepared`, `in_flight`, then a
final outcome. `get_write_status` is local-only by default; `reconcile=true`
performs read-only verification and never sends a mutation.
Workout dates carry an explicit IANA timezone and default to `Europe/Warsaw`.

Structured workout read-back compares the prescribed values, units, ranges and
target modes for power, heart rate, pace and cadence, including nested repeats.
A change from `50 %ftp` to `999 w` returns `mismatch` with exact
`workout_doc.steps[...]` difference paths. API-derived target metadata is not
compared as a prescription, and equivalent numeric `50`/`50.0` values are
accepted. Booleans are not accepted as matching numbers. `checked_fields`
reports the step tree and total duration when those checks were performed.

`INTERVALS_ACCESS_MODE=admin` exposes legacy and safe writes, `coach` exposes
only the safe write surface, and `readonly` hides mutation tools while retaining
`get_write_status` and `get_analysis_comment_status`. Live account verification is not implied by
these capabilities; uncertain writes remain explicitly subject to
reconciliation.

## Coach catalogue and analysis comments

One declared catalogue supplies registration, access modes and the exhaustive
`get_capabilities.data.tool_catalogue`. The running server resolves its mode at
startup: admin exposes 34 tools, coach 26, readonly 24. An invalid mode falls back
to readonly. Changing the environment requires a new server instance. Each entry
describes upstream and local effects; readonly prohibits upstream mutations,
while artifact export and journal reconciliation can still write local files.

`publish_analysis_comment(activity_id, analysis_uid, content)` is available in
coach and admin. Use a stable `analysis_uid` for one version of an activity's
analysis. The tool binds it to the configured athlete, activity and exact content;
the content is preserved, with a local limit of 100,000 characters. Repeating that
intent returns its recorded result without another POST. Reusing the UID with
different content or activity returns a conflict. A deliberately new analysis
version uses a new UID and appends a comment, preserving the earlier history.

For example, publish `activity_id="i123456"`, `analysis_uid="i123456-analysis-v1"`
and the analysis as `content`. Retain all three values for any repeat call. Inspect
the outcome with `get_analysis_comment_status(analysis_uid="i123456-analysis-v1",
reconcile=True)`.

Confirmation requires a separate activity-message GET containing the acknowledged
numeric message ID and exact content. The POST acknowledgement alone cannot
confirm publication. Timeout, a lost or malformed ID, unavailable read-back or
absence from a bounded list stays `unknown`; conflicting content, activity identity
or a deletion marker produces `mismatch`. Reconciliation performs reads only and
returns historical confirmation separately from current observation. It cannot
recover a lost ID by matching prose or timestamps, or automatically publish again.
Use the status result to resolve uncertainty; changing the UID to retry an
uncertain publication can create a duplicate.

Comment records live under `INTERVALS_OPERATION_DIR/analysis-comments`, separate
from existing workout records, and use the same account lock as workout writes.
All processes writing for one account must share and retain that operation
directory. The replay guarantee depends on those records; upstream idempotency
and live account behavior remain unverified.

`get_activity_messages` preserves returned identity, deletion metadata and content,
but its default upstream list is limited to 100 messages. Full history coverage
remains unknown. Compact session context also preserves documented message identity
and deletion fields, and exposes full-read continuations for projected omissions.

The three architecture changes and their acceptance criteria are described in
[`docs/architecture/coach-tools-design.md`](docs/architecture/coach-tools-design.md).
The synthetic coach-cycle test uses actual MCP discovery and calls to read the
session and linked plan, publish/replay/revise analysis, verify a subsequent
workout, and repeat calls after process restarts.

The scenario-by-scenario fixture and live-verification status is recorded in
[`TATRA_V3_ACCEPTANCE.md`](TATRA_V3_ACCEPTANCE.md).
