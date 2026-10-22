# AI target configuration

Target files define the API conditions that receive every rendered research
question. They contain model identifiers and experimental settings only. Never
put API keys in these files.

## Included configurations

- `targets.mock.json` runs a free local test without contacting an AI provider.
- `targets.study-v1.json` preserves the original Sonnet study condition.
- `targets.study-v2.json` preserves the lower-cost no-search condition.
- `targets.study-v3-search.json` is the current reduced-prompt live-search
  condition.
- `targets.example.json` mirrors v2 for local experimentation.
- `targets.local.json` is the ignored working copy that each researcher may use
  for account-specific testing.

Create a local V3 copy from `ai_probe_runner/`:

```bash
cp config/targets.study-v3-search.json config/targets.local.json
python -m json.tool config/targets.local.json >/dev/null
```

## Current V3 condition

V3 keeps one quick, cost-conscious model per provider and enables current web
information:

| Target ID | Provider | Model ID | Interface |
| --- | --- | --- | --- |
| `openai-gpt-5-4-nano-2026-03-17-search-v3` | OpenAI | `gpt-5.4-nano-2026-03-17` | Responses API + search |
| `anthropic-haiku-5-5-low-effort-search-v3` | Anthropic | `claude-haiku-5-5` | Messages API + search |
| `google-gemini-3-5-flash-lite-search-v3` | Google | `gemini-3.5-flash-lite` | Interactions API + search |

This is a low-cost API comparison, not an exact reproduction of free ChatGPT,
Claude, or Gemini. Consumer products may use different routing, system prompts,
tools, safety layers, personalization, and model versions.

The V3 condition retains Haiku after Sonnet consumed credits faster than
expected. It caps output at 640 tokens. OpenAI and Anthropic are hard-capped at
one search tool call per response; each V3 prompt also requests one focused
search. Gemini can decide to execute multiple queries within one response, so
its recorded search count and provider usage dashboard must be monitored.

## Gemini search billing

As reviewed on 2026-10-21, Google's pricing page lists Gemini 3 search
grounding as unavailable through the free-tier API for the selected Flash-Lite
condition. On the paid tier, the first 5,000 search requests per month are
currently included across eligible Gemini 3 models, after which search is
billed per query. One response may generate multiple queries. Confirm billing,
set a budget alert, and review the
[official pricing page](https://ai.google.dev/gemini-api/docs/pricing) before
unattended V3 collection. Pricing and quota can change.

## Target fields

Each file is a JSON array. Every entry supports:

| Field | Meaning |
| --- | --- |
| `target_id` | Stable project label for this complete experimental condition. |
| `study_id` | Optional shared label written into V3 manifests and readable output. |
| `provider` | Provider adapter: `openai`, `anthropic`, `google`, or `mock`. |
| `model` | Exact model ID sent to the provider API. |
| `interface` | Descriptive API label archived with the result. |
| `browsing` | Whether the provider's supported search tool is requested. |
| `max_output_tokens` | Positive integer ceiling passed to every provider. |
| `effort` | Optional Anthropic effort level; v2 explicitly uses `low`. |
| `max_search_uses` | Optional 1–10 search-call cap. Used by OpenAI and Anthropic in V3. |
| `enabled` | Whether this entry participates in a run. |

The runner passes `model`, `browsing`, `max_output_tokens`, supported `effort`,
and supported search caps into provider adapters. Other fields are preserved
for identification and auditing. Study V3 freezes output length at 640 tokens
and Anthropic effort at `low`.

## Test one provider at a time

Edit only the ignored `targets.local.json`. Keep the target under test enabled
and set the other two entries to:

```json
"enabled": false
```

Then run:

```bash
uv run ai-probe-runner \
  --trigger examples/trigger.flash-flood.json \
  --targets config/targets.local.json \
  --question-bank-dir config/question_banks_v3 \
  --delay-seconds 1
```

Repeat for OpenAI, Anthropic, and Google before enabling all three together.
Inspect both the printed summary and the generated `probes.jsonl`; provider
errors are retained as records and do not necessarily make the CLI exit with a
failure status.

## Preserve search as a separate condition

Do not change an existing target from `browsing: false` to `true` during a study.
Instead, copy the entry, give it a distinct `target_id`, and change only
`browsing`:

```json
{
  "target_id": "openai-gpt-5-4-nano-2026-03-17-with-search",
  "provider": "openai",
  "model": "gpt-5.4-nano-2026-03-17",
  "interface": "responses-api",
  "browsing": true,
  "max_search_uses": 1,
  "max_output_tokens": 640,
  "enabled": true
}
```

Verify support and pricing separately for every provider. Search availability,
tool names, limits, and charges can change independently from the base model.
Treat search and no-search responses as different experimental conditions.

## Freeze a research target set

Before unattended collection:

1. Verify every model ID with a small manual pilot.
2. Decide whether aliases or provider snapshots best match the study protocol.
3. Confirm that browsing, question banks, and retry behavior are fixed.
4. Commit the approved target file rather than relying on an untracked local copy.
5. Tag or record the Git commit that begins the collection period.
6. Record provider-reported resolved model IDs from the saved responses.
7. Review provider deprecation notices on a regular schedule.

Changing a model ID later creates a new condition. Use a new `target_id`, record
the effective date, and retain the earlier configuration so results remain
interpretable.
