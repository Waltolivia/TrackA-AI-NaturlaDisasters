# AI target configuration

Target files define the API conditions that receive every rendered research
question. They contain model identifiers and experimental settings only. Never
put API keys in these files.

## Included configurations

- `targets.mock.json` runs a free local test without contacting an AI provider.
- `targets.example.json` contains the recommended inexpensive three-provider
  baseline, reviewed on 2026-09-28.
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
| `openai-luna-no-search` | OpenAI | `gpt-5.6-luna` | Responses API |
| `anthropic-sonnet-no-search` | Anthropic | `claude-sonnet-5-5` | Messages API |
| `google-flash-lite-no-search` | Google | `gemini-3.5-flash-lite` | Interactions API |

This is a low-cost API comparison, not an exact reproduction of free ChatGPT,
Claude, or Gemini. Consumer products may use different routing, system prompts,
tools, safety layers, personalization, and model versions.

Anthropic's less expensive Haiku 4.5 model was intentionally not selected for
the baseline because its documented lifecycle may end in October 2026. A model
that may disappear during collection is a poor default for a longitudinal
study. If the team deliberately studies Haiku before retirement, use a separate
target file and label the time-bounded condition clearly.

## Target fields

Each file is a JSON array. Every entry supports:

| Field | Meaning |
| --- | --- |
| `target_id` | Stable project label for this complete experimental condition. |
| `provider` | Provider adapter: `openai`, `anthropic`, `google`, or `mock`. |
| `model` | Exact model ID sent to the provider API. |
| `interface` | Descriptive API label archived with the result. |
| `browsing` | Whether the provider's supported search tool is requested. |
| `enabled` | Whether this entry participates in a run. |

The current runner passes `model` and `browsing` into the provider adapter. The
other fields are preserved in every result for identification and auditability.
The current target schema does **not** configure temperature, output length,
reasoning effort, or retries. Adding any of those requires an explicit code and
schema change; do not add unused JSON fields and assume they affect requests.

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
  "target_id": "openai-luna-with-search",
  "provider": "openai",
  "model": "gpt-5.6-luna",
  "interface": "responses-api",
  "browsing": true,
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
