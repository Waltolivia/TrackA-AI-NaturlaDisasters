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
- Saves the raw and normalized triggers, rendered questions, normalized records, raw responses,
  timestamps, model identifiers, citations, token usage, errors, and hashes.
- Includes a mock provider so the full pipeline can be tested without API keys.

## Folder layout

```text
ai_probe_runner/
  config/
    question_banks/
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
  --targets config/targets.mock.json
```

You can also test without creating a trigger file:

```bash
uv run ai-probe-runner \
  --hazard-family flood \
  --event "Flash Flood Warning" \
  --area "Salt Lake County, Utah" \
  --targets config/targets.mock.json
```

Output is written under `data/YYYY-MM-DD/<cycle-id>/`. The `data/` directory is
ignored by Git because collected research data should not be mixed with source
code.

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

Copy the example target configuration:

```bash
cp config/targets.example.json config/targets.local.json
```

`targets.example.json` is the project's inexpensive baseline, reviewed on
2026-09-28. It contains one fast, cost-conscious target from each supported
provider:

| Provider | Model ID | Experimental condition |
| --- | --- | --- |
| OpenAI | `gpt-5.6-luna` | No web search |
| Anthropic | `claude-sonnet-5-5` | No web search |
| Google | `gemini-3.5-flash-lite` | No web search |

These models were selected to emphasize speed, cost, and broad API availability
rather than maximum benchmark performance. They are inexpensive API models, but
they are **not guaranteed to be identical** to the models, system prompts, or
tools used in the providers' free consumer chat products.

The initial baseline deliberately disables browsing. Browsing changes the
information available to a model and may add tool-use charges, so search-enabled
probes should be introduced later as a separately named experimental condition,
not silently added to these targets. See `config/README.md` for every target
field, one-provider testing, model lifecycle guidance, and the procedure for
adding a search condition.

Verify that every configured model is available to the team's API account.
Model availability and names can change. Disable unavailable or unapproved
conditions with `"enabled": false`. Before real collection, commit the exact
approved target file and record the date on which the IDs were verified.

Run a real pilot:

```bash
uv run ai-probe-runner \
  --trigger examples/trigger.flash-flood.json \
  --targets config/targets.local.json \
  --delay-seconds 1 \
  --fail-on-probe-error
```

The example event currently renders five general questions and four flood
questions. With the three enabled baseline targets, a successful flood pilot
therefore expects `9 questions x 3 targets = 27 probes`. Check the printed
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
  "generated_at": "2026-09-28T16:01:00Z"
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

Schema 3 `NEW_EVENT`, `STATUS_CHANGED`, and `SEVERITY_CHANGED` actions can start
AI probes. Schema 2 `NEW_EVENT` and `ESCALATION` remain supported. Lifecycle
messages such as `EVENT_ENDED` and `COLLECTION_COMPLETE` are rejected
intentionally.

The AI module currently has question banks for:

- `flood`
- `wildfire`
- `tropical_cyclone`
- `tornado`
- `earthquake`

The adapter recognizes these event-type terms:

| Question bank | Recognized `event_type` or headline terms |
| --- | --- |
| `flood` | `flood`, `flash flood`, `floods`, `storm surge` |
| `wildfire` | `wildfire`, `wildfires`, `fire weather`, `red flag` |
| `tropical_cyclone` | `hurricane`, `tropical cyclone`, `tropical storm` |
| `tornado` | `tornado`, `tornadoes` |
| `earthquake` | `earthquake`, `earthquakes` |

Other natural-disaster types collected by Disaster Monitor, such as volcanoes,
landslides, blizzards, and severe thunderstorms, fail with an explicit
unsupported-type error. Add and review a matching hazard bank before enabling
one of those categories; never silently route it to a generic or incorrect bank.

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

Every trigger receives five questions from `general.json` plus four questions
from the matching hazard file. The general bank covers current status, immediate
protective action, official referrals, evacuation/shelter decisions, and
uncertainty. Hazard banks add risks and actions specific to floods, wildfires,
tropical cyclones, tornadoes, or earthquakes.

Templates can use any normalized trigger field. The intended common placeholders
are:

- `{event}`: the normalized event type or name, such as `flash flood`.
- `{area}`: the normalized collector location, such as `Test County, Utah`.
- `{timestamp}`: `sent_at`, falling back to `generated_at`.
- `{severity}`, `{urgency}`, and `{certainty}`: source classifications when present.
- `{source}` and `{source_id}`: provenance fields; use carefully because including
  them in a prompt gives the model information a normal user might not have.

Questions are rendered deterministically; an AI is not used to generate research
questions. Each entry must be a JSON object with a unique `question_id`, a
`category`, and a `template`:

```json
{
  "question_id": "flood-example-001",
  "category": "protective-action",
  "template": "What should someone in {area} do during the reported {event}?"
}
```

Question IDs must be unique across the two selected banks. Treat changes to
wording, IDs, model configurations, browsing conditions, and retry policy as
research-protocol changes that should be committed and documented.

## Output and reproducibility

Each cycle contains:

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

## Known boundary before wiring

NWS supplies a human-readable `areaDesc`, so its location works well in AI
prompts. The current NASA EONET adapter uses a string such as
`coordinates=[longitude, latitude]`. The AI runner preserves and can render that
value, but a future ground-truth change should add a human-readable place name or
reverse-geocoded region if EONET events are included in the study. Do not ask an
AI model to invent a place name from incomplete coordinates during normalization.

The runner intentionally does not claim queue files or schedule collection.
Those responsibilities belong to the root `pipeline_worker`. Durable off-host
upload remains a deployment responsibility.

## Common problems

- `uv: command not found`: install uv above, reopen the terminal, and retry.
- Missing API key: copy `.env.example` to `.env` and fill only the local file.
- Unsupported event type: add a reviewed hazard bank and mapping before probing.
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
7. Run all three baseline targets and verify the expected/completed/failed counts.
8. Record and resolve any model, billing, quota, or interface errors.
9. Preserve the exact target file, question banks, Git commit, and collection date.
10. Pass a real supported v5 queue file through the mock target.
11. Run the root worker end-to-end and verify queue acknowledgement.
