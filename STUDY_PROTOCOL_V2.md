# Track A study protocol: version 2

Status: **proposed cost-controlled successor to study v1**

Version 2 keeps the v1 sources, trigger policy, question banks, no-search
condition, retention rules, and evaluation rubric. It changes only the model
configuration and result presentation described below. Do not combine v1 and
v2 responses as though they came from the same experimental condition.

## Why version 2 exists

The v1 Anthropic Sonnet target consumed prepaid credits faster than expected.
The human-facing results were also difficult to review because the primary
record was an append-only JSON Lines audit file. V2 makes the lower-cost model
choice explicit and adds derived, readable outputs without removing any raw
research data.

## V2 targets

The committed target file is
`ai_probe_runner/config/targets.study-v2.json`.

| Provider | Exact model ID | Search | Output ceiling | Extra setting |
| --- | --- | --- | --- | --- |
| OpenAI | `gpt-5.4-nano-2026-03-17` | Off | 1,024 tokens | API default |
| Anthropic | `claude-haiku-5-5` | Off | 1,024 tokens | `effort: low` |
| Google | `gemini-3.5-flash-lite` | Off | 1,024 tokens | API default |

The lower common output ceiling preserves a comparable maximum across the
three providers. It is a ceiling, not a requested response length.

## V2 result layout

New cycles are stored under:

```text
pipeline_data/results/YYYY/Month/DD/EVENT_ID/MESSAGE_ID/
```

Each cycle includes:

- `AI_RESULTS.md`: human-readable prompts and answers grouped by provider.
- `responses.json`: compact valid JSON for analysis and sharing.
- `trigger.raw.json`: exact collector message that caused the AI cycle.
- `trigger.json`, `questions.json`, `manifest.json`, and `probes.jsonl`: full
  reproducibility and retry records retained from v1.
- `raw/`: complete provider responses retained from v1.

The readable files are derived from the latest attempt for each target/question
pair. `probes.jsonl` remains authoritative for attempt history.

## Transition record

Before deployment, record:

1. The last UTC timestamp collected under v1.
2. The first UTC timestamp collected under v2.
3. The deployed Git commit or tag.
4. Confirmation that every host uses `targets.study-v2.json` or a local copy
   that exactly matches it.
