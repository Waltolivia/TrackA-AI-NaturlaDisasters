# AI Probe Runner

This folder contains the AI-facing half of the Track A natural-disaster data
collection project. It asks a versioned question bank of configured AI APIs and
archives timestamped responses for later comparison with official ground truth.

It is intentionally self-contained. It does **not** import from or modify a
ground-truth collector. Its preferred integration boundary is a schema 3 JSON
message written by `disaster_monitor-v5`; schema 2 messages remain supported.

## What it does

- Accepts a trigger JSON or manual hazard/event/location input.
- Combines a general question bank with one hazard-specific bank.
- Runs every rendered question against every enabled target configuration.
- Treats browsing on/off as separate experimental conditions.
- Saves readable Markdown and compact JSON alongside raw and normalized
  triggers, rendered questions, provider responses, timestamps, model
  identifiers, citations, token usage, errors, and hashes.
- Includes a mock provider so the full pipeline can be tested without API keys.

## Folder layout

```text
ai_probe_runner/
  config/
    question_banks/
      README.md
      general.json
      hazards/
    question_banks_v3/
      README.md
      general.json
      hazards/
    README.md
    targets.mock.json
    targets.example.json
  examples/
    trigger.flash-flood.json
  src/ai_probe_runner/
  tests/
  .env.example
  pyproject.toml
  requirements.txt
```

## Install for the first time

You need Git and [uv](https://docs.astral.sh/uv/). You do not need to create or
activate a virtual environment manually; `uv sync` creates `.venv` and installs
the locked project dependencies.

Check whether uv is already installed:

```bash
uv --version
```

If that command is not found, install uv using Astral's official instructions:

**macOS or Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows PowerShell:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen the terminal after installation, then run `uv --version`
again. The full installation guide is at
<https://docs.astral.sh/uv/getting-started/installation/>.

Clone the shared repository if it is not already on your computer:

```bash
git clone https://github.com/Waltolivia/TrackA-AI-NaturlaDisasters.git
cd TrackA-AI-NaturlaDisasters/ai_probe_runner
```

Install the runner, tests, and provider SDKs:

```bash
uv sync --extra dev --extra providers
```

## Quick no-cost test

From `TrackA-AI-NaturlaDisasters/ai_probe_runner`:

```bash
uv run pytest
```

Run a no-cost mock cycle from the example trigger:

```bash
uv run ai-probe-runner \
  --trigger examples/trigger.flash-flood.json \
  --targets config/targets.mock.json \
  --question-bank-dir config/question_banks_v3
```

You can also test without creating a trigger file:

```bash
uv run ai-probe-runner \
  --hazard-family flood \
  --event "Flash Flood Warning" \
  --area "Salt Lake County, Utah" \
  --targets config/targets.mock.json \
  --question-bank-dir config/question_banks_v3
```

Integrated output is written under
`pipeline_data/results/YYYY/Month/Week/EVT-.../EVT-..._AI/runs/MSG-.../`.
Standalone manual output uses the same structure with an inferred event/date.
Collected data directories are ignored by Git.

## API keys and real providers

Copy the environment template:

```bash
cp .env.example .env
```

Add keys to the local `.env` file:

```dotenv
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
```

The runner loads `.env` automatically. Never put keys in target JSON and never
commit `.env`; it is ignored by Git.

Copy the active target configuration for isolated local testing:

```bash
cp config/targets.study-v3-search.json config/targets.local.json
```

`targets.study-v1.json` preserves the original Sonnet baseline and
`targets.study-v2.json` preserves the lower-cost no-search condition. The
current condition is `targets.study-v3-search.json`:

| Provider | Model ID | Experimental condition |
| --- | --- | --- |
| OpenAI | `gpt-5.4-nano-2026-03-17` | Live search; one tool-call cap |
| Anthropic | `claude-haiku-5-5` | Live search; one-search cap; low effort |
| Google | `gemini-3.5-flash-lite` | Live Google Search grounding |

These models were selected to emphasize speed, cost, and broad API availability
rather than maximum benchmark performance. They are inexpensive API models, but
they are **not guaranteed to be identical** to the models, system prompts, or
tools used in the providers' free consumer chat products.

Each V3 target has an explicit 640-token output ceiling. Anthropic also requests
low effort. Every V3 prompt asks for one focused search; OpenAI and Anthropic
receive an API-level cap of one search/tool call. Gemini does not expose the
same cap in this integration and may execute multiple queries. The runner saves
the requested and resolved model, citations, provider usage, and recorded
search-call count for every probe.

V2 and V3 are different experimental conditions. Preserve both configurations
and never combine their responses as though only the date changed. See
`config/README.md` for target fields, billing notes, and isolated-provider
testing.

Verify that every configured model is available to the team's API account.
Model availability and names can change. Disable unavailable or unapproved
conditions with `"enabled": false`. Before real collection, commit the exact
approved target file and record the date on which the IDs were verified.

Run a real pilot:

```bash
uv run ai-probe-runner \
  --trigger examples/trigger.flash-flood.json \
  --targets config/targets.study-v3-search.json \
  --question-bank-dir config/question_banks_v3 \
  --delay-seconds 1 \
  --fail-on-probe-error
```

The example new flood event renders two general questions and one flood
question. With three targets, a successful V3 pilot expects
`3 questions x 3 targets = 9 probes`. A status/severity update renders one
question per model, or three probes. Check the printed
`expected_probe_count`, `completed_probe_count`, and `failed_probe_count` rather
than assuming that the run succeeded because the command exited.

`--fail-on-probe-error` makes the process exit with status 1 if any provider
request fails. Use it for scripts and future automation. Without the flag,
provider failures are still saved in `probes.jsonl`, but the CLI completes so a
researcher can inspect partial results.

## Trigger contract from Disaster Monitor

The preferred input is the schema 3 queue message written by
`disaster_monitor-v5/disaster_monitor/services/prompter.py`:

```json
{
  "schema_version": 3,
  "message_id": "MSG-unique-id",
  "action": "NEW_EVENT",
  "event_id": "EVT-00000001",
  "disaster": {
    "type": "flash flood",
    "name": null,
    "location": "Garfield County, Colorado"
  },
  "severity": "Severe",
  "status": "WARNING",
  "event_lifecycle": "ACTIVE",
  "headline": "Flash Flood Warning for Garfield County",
  "source": "NWS",
  "source_alert_id": "official-alert-id",
  "sent_at": "2026-09-28T16:00:00Z",
  "generated_at": "2026-09-28T16:01:00Z",
  "archive": {
    "year": "2026",
    "month": "September",
    "week": "Sep_28-Sep_30",
    "event_id": "EVT-00000001",
    "relative_prefix": "2026/September/Sep_28-Sep_30/EVT-00000001"
  }
}
```

The adapter adds the canonical names used by the question templates while
preserving every original collector field:

| Disaster Monitor | AI runner name | Purpose |
| --- | --- | --- |
| `event_id` | retained as `event_id` | Stable grouped incident ID |
| `message_id` | retained as `message_id` | Stable worker job and cycle ID |
| `action` | `trigger` | Identifies the meaningful live change |
| `disaster.type` | `hazard_family` | Selects a hazard question bank |
| `disaster.name` or `.type` | `event` | Event placed in prompts |
| `disaster.location` | `area` | Human-readable area placed in prompts |
| `source_alert_id` | `source_id` | Links results to the source alert |
| `sent_at`, then `generated_at` | `timestamp` | Gives prompts a clear reference time |
| `archive.relative_prefix` | retained | Places GT and AI under the same event folder |

Schema 3 `NEW_EVENT`, `STATUS_CHANGED`, and `SEVERITY_CHANGED` actions can start
AI probes. Schema 2 `NEW_EVENT` and `ESCALATION` remain supported. Lifecycle
messages such as `EVENT_ENDED` and `COLLECTION_COMPLETE` are rejected
intentionally.

V3 has specific question banks for:

- `flood`
- `wildfire`
- `tropical_cyclone`
- `tornado`
- `earthquake`
- `tsunami`
- `volcano`
- `landslide`

The adapter recognizes these event-type terms:

| Question bank | Recognized `event_type` or headline terms |
| --- | --- |
| `flood` | `flood`, `flash flood`, `floods`, `storm surge` |
| `wildfire` | `wildfire`, `wildfires`, `fire weather`, `red flag` |
| `tropical_cyclone` | `hurricane`, `typhoon`, `tropical cyclone`, `tropical storm` |
| `tornado` | `tornado`, `tornadoes` |
| `earthquake` | `earthquake`, `earthquakes` |

Aliases such as `typhoon` are routed to the matching family. A
collector-approved natural-disaster type without a specific V3 hazard file
receives only the general questions and retains its normalized family label in
the output; it is never silently routed to an incorrect hazard bank.

### Test one claimed queue file directly

First use the mock target so no API credits are consumed:

```bash
cd ai_probe_runner
uv run ai-probe-runner \
  --trigger ../disaster_monitor-v5/outbox/processing/REPLACE_WITH_FILE.json \
  --targets config/targets.mock.json \
  --cycle-id manual-direct-test \
  --resume \
  --fail-on-probe-error
```

For normal integrated operation, use the root `pipeline_worker` instead of
manually selecting files. It claims messages, selects stable cycle IDs, passes
`--resume`, verifies complete manifests, and acknowledges the v5 queue.

## Question banks

The legacy `question_banks/` directory remains frozen for V1/V2
reproducibility. V3 uses `question_banks_v3/`:

- A recognized `NEW_EVENT` receives two general questions plus one matching
  hazard-specific question: three questions per model.
- `STATUS_CHANGED`, `SEVERITY_CHANGED`, and `ESCALATION` receive one
  consolidated current-status/action question per model.
- A collector-approved family without a specific hazard file receives the
  applicable general questions rather than being skipped.

Templates can use any normalized trigger field. The intended common placeholders
are:

- `{event}`: the normalized event type or name, such as `flash flood`.
- `{area}`: the normalized collector location, such as `Test County, Utah`.
- `{location_context}`: a named area, or an explicit longitude/latitude label
  when EONET supplied only coordinates.
- `{timestamp}`: `sent_at`, falling back to `generated_at`.
- `{severity}`, `{urgency}`, and `{certainty}`: source classifications when present.
- `{source}` and `{source_id}`: provenance fields; use carefully because including
  them in a prompt gives the model information a normal user might not have.

Questions are rendered deterministically; an AI is not used to generate research
questions. Each entry must be a JSON object with a unique `question_id`, a
`category`, and a `template`. V3 entries may add `trigger_types` to select
new-event or update prompts:

```json
{
  "question_id": "flood-example-001",
  "category": "protective-action",
  "trigger_types": ["NEW_EVENT"],
  "template": "What should someone in {area} do during the reported {event}?"
}
```

Question IDs must be unique across the two selected banks. Treat changes to
wording, IDs, model configurations, browsing conditions, and retry policy as
research-protocol changes that should be committed and documented.

## Output and reproducibility

Each cycle contains:

- `AI_RESULTS.md`: readable event/model/question/answer report; open this first.
- `responses.json`: compact machine-readable prompts and answers.
- `manifest.json`: cycle timing, counts, hashes, runtime, and Git commit.
- `trigger.raw.json`: exact object received from the collector or manual caller.
- `trigger.json`: normalized trigger used to select and render questions.
- `questions.json`: exact rendered prompts.
- `probes.jsonl`: one normalized record for every question/target attempt.
- `raw/*.json`: complete successful provider responses.

Errors are retained as data instead of being silently discarded. Pass `--resume`
with the same cycle ID to retry only failed or missing question/target pairs.
Resume is rejected if the trigger, target file, question banks, or expected
probe count changed. Without `--resume`, existing cycles are never overwritten.

## Coordinate-only locations

NWS supplies a human-readable `areaDesc`. NASA EONET sometimes supplies only
`coordinates=[longitude, latitude]`. V3 no longer skips those events. It keeps
the raw coordinates, renders them as labeled longitude and latitude, and tells
the searched model to acknowledge uncertainty rather than invent a locality.
Future ground-truth enrichment may add a reviewed place name, but it is not a
prerequisite for collecting an AI response.

The runner intentionally does not claim queue files or upload to S3. Those
responsibilities belong to the root `pipeline_worker`, which uploads complete
cycles and retries storage separately from paid probes.

## Common problems

- `uv: command not found`: install uv above, reopen the terminal, and retry.
- Missing API key: copy `.env.example` to `.env` and fill only the local file.
- Unrecognized event type: V3 uses general questions; add a reviewed hazard
  file in the next version if hazard-specific coverage is required.
- `EVENT_ENDED` rejected: select a supported live-change message or use the
  worker, which records and acknowledges lifecycle messages automatically.
- Existing cycle directory: choose a new explicit manual `cycle_id`; the runner
  refuses to overwrite collected data unless `--resume` is supplied with
  identical research inputs.
- Some probes failed but the command continued: inspect `probes.jsonl`, or run
  with `--fail-on-probe-error` for a nonzero automation exit status.

## Team test checklist

1. Run `uv run pytest`.
2. Run the example trigger with `targets.mock.json`.
3. Confirm the manifest reports all expected probes completed.
4. Inspect `trigger.raw.json`, `trigger.json`, `questions.json`, and `probes.jsonl`.
5. Copy `targets.example.json` to ignored `targets.local.json`.
6. Run one provider at a time by disabling the other local targets.
7. Run all three V3 targets and verify 9/9 completed for a recognized new event.
8. Record and resolve any model, billing, quota, or interface errors.
9. Preserve the exact target file, question banks, Git commit, and collection date.
10. Pass a real supported v5 queue file through the mock target.
11. Run the root worker end-to-end and verify queue acknowledgement.
