# Track A study protocol: version 2

Status: **proposed cost-controlled successor to study v1**

Version 2 keeps the v1 sources, trigger policy, question banks, and no-search
condition. It changes the model configuration, output presentation, and shared
storage described below. Do not combine v1 and v2 responses as though they came
from the same experimental condition.

## Why version 2 exists

The v1 Anthropic Sonnet target consumed prepaid credits faster than expected.
The primary AI record was also difficult to review because it was an
append-only JSON Lines audit file. V2 makes the lower-cost model choice explicit
and adds derived readable outputs without removing raw research data.

## V2 targets

The committed target file is
`ai_probe_runner/config/targets.study-v2.json`.

| Provider | Exact model ID | Search | Output ceiling | Extra setting |
| --- | --- | --- | --- | --- |
| OpenAI | `gpt-5.4-nano-2026-03-17` | Off | 1,024 tokens | API default |
| Anthropic | `claude-haiku-5-5` | Off | 1,024 tokens | `effort: low` |
| Google | `gemini-3.5-flash-lite` | Off | 1,024 tokens | API default |

The common output ceiling is a maximum, not a requested response length.

## V2 storage layout

S3 is the primary shared research archive. Local files and SQLite databases
remain the working and recovery copies.

```text
disaster_monitor-v5/archive/YYYY/Month/Week/EVT-.../
  EVT-..._weather/
    EVENT_REPORT.txt
    event.json
    alerts.json
  EVT-..._AI/
    AI_RESULTS.md
    responses.json
    runs/MSG-.../
      AI_RESULTS.md
      responses.json
      trigger.raw.json
      questions.json
      manifest.json
      probes.jsonl
      raw/
```

The stable `event_id` joins ground truth and AI results. The unique
`message_id` joins one exact collector change to one AI cycle. The readable
files are derived views; `probes.jsonl` and `raw/` remain the attempt history
and complete provider record.

S3 failures retry independently and never repeat already-completed AI probes.
The optional DynamoDB tier remains a separate secondary archive and is not
required by v2.

## Transition record

Before deployment, record:

1. The last UTC timestamp collected under v1, if v1 collection occurred.
2. The first UTC timestamp collected under v2.
3. The deployed Git commit and `study-v2.0.0` tag.
4. The S3 bucket region and prefix, but never credentials.
5. Confirmation that every host uses `targets.study-v2.json`.
6. Confirmation that the three model IDs and question banks passed a real pilot.
