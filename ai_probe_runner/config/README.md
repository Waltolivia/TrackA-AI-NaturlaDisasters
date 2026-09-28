# AI target configuration

Target files define the API conditions that receive every rendered research
question. They contain model identifiers and experimental settings only. Never
put API keys in these files.

## Included configurations

- `targets.mock.json` runs a free local test without contacting an AI provider.
- `targets.study-v1.json` is the committed proposed study condition.
- `targets.example.json` mirrors the study condition for local experimentation.
- `targets.local.json` is the ignored working copy that each researcher may use
  for account-specific testing.

Create the local copy from `ai_probe_runner/`:

```bash
cp config/targets.example.json config/targets.local.json
python -m json.tool config/targets.local.json >/dev/null
```

## Recommended baseline

The baseline uses one quick, cost-conscious model per provider with browsing
disabled:

| Target ID | Provider | Model ID | Interface |
| --- | --- | --- | --- |
| `openai-gpt-5-4-nano-2026-03-17-no-search` | OpenAI | `gpt-5.4-nano-2026-03-17` | Responses API |
| `anthropic-sonnet-5-5-no-search` | Anthropic | `claude-sonnet-5-5` | Messages API |
| `google-gemini-3-5-flash-lite-no-search` | Google | `gemini-3.5-flash-lite` | Interactions API |

This is a low-cost API comparison, not an exact reproduction of free ChatGPT,
Claude, or Gemini. Consumer products may use different routing, system prompts,
tools, safety layers, personalization, and model versions.

The OpenAI target is a dated snapshot. Anthropic documents Sonnet 5.5 as a
fixed model ID with a longer expected lifecycle than Haiku 4.5. Google lists
Flash-Lite as stable. Provider infrastructure may still change. If a successor
is required, give it a new `target_id`, record the transition date, and
preserve the old configuration so different models are never treated as one
condition.

## Gemini free tier

As reviewed on 2026-09-28, Google lists a free tier for
`gemini-3.5-flash-lite`, so billing is not required for the initial integration
test. Free-tier prompts and responses may be used to improve Google's products;
paid-tier data is documented differently. Use only approved public disaster
information, confirm the project's research-data policy, and review the
[official pricing page](https://ai.google.dev/gemini-api/docs/pricing) before
unattended collection. Add billing only if the team needs higher quota or the
paid-tier data terms.

## Target fields

Each file is a JSON array. Every entry supports:

| Field | Meaning |
| --- | --- |
| `target_id` | Stable project label for this complete experimental condition. |
| `provider` | Provider adapter: `openai`, `anthropic`, `google`, or `mock`. |
| `model` | Exact model ID sent to the provider API. |
| `interface` | Descriptive API label archived with the result. |
| `browsing` | Whether the provider's supported search tool is requested. |
| `max_output_tokens` | Positive integer ceiling passed to every provider. |
| `enabled` | Whether this entry participates in a run. |

The runner passes `model`, `browsing`, and `max_output_tokens` into each
provider adapter. Other fields are preserved for identification and auditing.
The study freezes output length at 2,048 tokens. Temperature and reasoning
effort remain at each provider's API default and are documented as such.

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
  --delay-seconds 1
```

Repeat for OpenAI, Anthropic, and Google before enabling all three together.
Inspect both the printed summary and the generated `probes.jsonl`; provider
errors are retained as records and do not necessarily make the CLI exit with a
failure status.

## Add web search as a separate condition

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
  "max_output_tokens": 2048,
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
