# AI Probe Runner

This folder contains the AI-facing half of the Track A natural-disaster data
collection project. It asks a versioned question bank of configured AI APIs and
archives timestamped responses for later comparison with official ground truth.

It is intentionally self-contained. This initial module does **not** import from
or modify `emergency_alert_collector/`. The future integration boundary is one
small trigger JSON object.

## What it does

- Accepts a trigger JSON or manual hazard/event/location input.
- Combines a general question bank with one hazard-specific bank.
- Runs every rendered question against every enabled target configuration.
- Treats browsing on/off as separate experimental conditions.
- Saves the trigger, rendered questions, normalized records, raw responses,
  timestamps, model identifiers, citations, token usage, errors, and hashes.
- Includes a mock provider so the full pipeline can be tested without API keys.

## Folder layout

```text
ai_probe_runner/
  config/
    question_banks/
      general.json
      hazards/
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

## Quick start with uv

From the shared repository root:

```bash
cd ai_probe_runner
uv sync --extra dev --extra providers
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

Output is written under `data/YYYY-MM-DD/<cycle-id>/`.

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

Verify that each configured model and search tool is available to the team's API
account. Model availability and names can change. Disable unavailable or
unapproved conditions with `"enabled": false`, and freeze the chosen file
before real research collection.

Run a real pilot:

```bash
uv run ai-probe-runner \
  --trigger examples/trigger.flash-flood.json \
  --targets config/targets.local.json \
  --delay-seconds 1
```

## Trigger contract

The future ground-truth integration should send an object like:

```json
{
  "cycle_id": "one-shared-uuid",
  "source": "NWS",
  "source_id": "official-alert-id",
  "version_hash": "official-alert-version-hash",
  "hazard_family": "flood",
  "event": "Flash Flood Warning",
  "area": "Garfield County, Colorado",
  "severity": "Severe",
  "urgency": "Immediate",
  "certainty": "Likely",
  "effective": "2026-09-28T16:00:00Z",
  "expires": "2026-09-28T20:00:00Z",
  "detected_at": "2026-09-28T16:01:00Z"
}
```

Required fields are `source`, `source_id`, `hazard_family`, `event`, and
`area`. The supported starter families are:

- `flood`
- `wildfire`
- `tropical_cyclone`
- `tornado`
- `earthquake`

The family must match a filename under `config/question_banks/hazards/`.

## How the future wiring works

The JSON itself does not launch this program. Later, a small queue/worker should:

1. Notice that the ground-truth collector saved a new qualifying alert version.
2. Classify it into a controlled `hazard_family`.
3. Store a pending trigger containing the fields above.
4. Claim one pending trigger and invoke this CLI.
5. Mark the trigger completed or failed.

Conceptually, the worker will run:

```bash
uv run ai-probe-runner \
  --trigger /path/to/claimed-trigger.json \
  --targets config/targets.local.json
```

That queue and worker are deliberately not part of this PR, because adding them
would require changing the ground-truth collector. Keeping the boundary at JSON
makes both sides independently testable now.

## Question banks

Every trigger receives the questions in `general.json` plus the matching hazard
file. Templates may use fields such as `{event}` and `{area}`. Questions are
rendered deterministically; an AI is not used to generate research questions.

Question IDs must be unique across the two selected banks. Treat changes to
wording, IDs, model configurations, browsing conditions, and retry policy as
research-protocol changes that should be committed and documented.

## Output and reproducibility

Each cycle contains:

- `manifest.json`: cycle timing, counts, hashes, runtime, and Git commit.
- `trigger.json`: exact event input.
- `questions.json`: exact rendered prompts.
- `probes.jsonl`: one normalized record for every question/target attempt.
- `raw/*.json`: complete successful provider responses.

Errors are retained as data instead of being silently discarded. The runner
never overwrites an existing cycle directory, so use a new `cycle_id` for a
deliberate rerun.

## Team test checklist

1. Run `uv run pytest`.
2. Run the example trigger with `targets.mock.json`.
3. Confirm the manifest reports all expected probes completed.
4. Inspect `trigger.json`, `questions.json`, and `probes.jsonl`.
5. Run one provider at a time using a local target file.
6. Record and resolve any model, billing, quota, or search-tool errors.
7. Only after the manual pilot, design the durable trigger queue and 24/7 worker.
