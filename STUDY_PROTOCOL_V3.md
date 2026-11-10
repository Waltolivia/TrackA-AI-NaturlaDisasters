# Track A study protocol: version 3

Status: **proposed live-search successor to study V2**

V3 introduces live web search, fewer prompts, broader natural-disaster
coverage, and coordinate-only EONET probing. V1/V2 outputs remain historical
conditions and must not be analyzed as if they were V3 responses.

## Frozen V3 inputs

- Targets: `ai_probe_runner/config/targets.study-v3-search.json`
- Questions: `ai_probe_runner/config/question_banks_v3/`
- Ground truth: Disaster Monitor v5 NWS and NASA EONET collectors
- Probe actions: `NEW_EVENT`, `STATUS_CHANGED`, `SEVERITY_CHANGED`, and legacy
  `ESCALATION`
- Non-probe lifecycle actions: `EVENT_ENDED`, `COLLECTION_COMPLETE`,
  `ROUTINE_UPDATE`, and `UPDATE`

Do not edit the target file or question directory without recording a method
transition. The response-completeness repair prepared on 2026-11-09 keeps the
V3 filenames, question IDs, schedule, models, search settings, triggers, and
sources, but changes the output ceiling and prompt wording described below.
The operator must record the actual UTC deployment time; earlier and later V3
runs must remain distinguishable during analysis.

## Targets and cost controls

| Provider | Model | Search | Output ceiling | Search control |
| --- | --- | --- | ---: | --- |
| OpenAI | `gpt-5.4-nano-2026-03-17` | On | 2,048 tokens | At most 1 tool call |
| Anthropic | `claude-haiku-5-5` | On | 2,048 tokens | `max_uses: 1`, low effort |
| Google | `gemini-3.5-flash-lite` | On | 2,048 tokens | Prompt requests current web information |

Google may execute multiple queries in one response. Actual search calls,
citations, provider usage, requested model, and resolved model are retained in
the run data. Operators must monitor all three provider dashboards and use
account-level budget alerts or spending limits where available.

The pre-repair V3 ceiling was 640 tokens. It produced visibly cut-off or empty
answers while still reporting successful API calls. The repaired prompts ask
for answers under 250 words and the ceiling is 2,048 tokens, giving the models
room for search/tool processing and a complete concise answer. The runner now
records and displays provider completion information but does not retry an
empty or truncated answer automatically. This avoids silently increasing cost
or changing the worker's queue behavior.

Official pricing references, reviewed 2026-10-21:

- <https://developers.openai.com/api/docs/pricing>
- <https://docs.anthropic.com/en/docs/build-with-claude/tool-use/web-search-tool>
- <https://ai.google.dev/gemini-api/docs/pricing>

## Question schedule

For a recognized `NEW_EVENT`, each model receives:

1. Current confirmed situation and sources.
2. Immediate protective action, including evacuation/shelter distinctions.
3. One consolidated hazard-specific question.

This produces three questions across three models: **9 provider calls**.

For `STATUS_CHANGED`, `SEVERITY_CHANGED`, or `ESCALATION`, each model receives
one consolidated current-status/change/action question: **3 provider calls**.

A collector-approved natural disaster without a hazard-specific file receives
the two general new-event questions or the one general update question. It is
not discarded and is not routed to an incorrect hazard family.

## Hazard and location policy

V3 provides specific banks for earthquake, flood, landslide, tornado, tropical
cyclone, tsunami, volcano, and wildfire. `typhoon` and `typhoons` map to
`tropical_cyclone`; plural collector categories are normalized to their
singular family.

NWS named areas are preserved. EONET strings in the form
`coordinates=[longitude, latitude]` are preserved and rendered as explicitly
labeled coordinates. Prompts require the model to disclose uncertainty rather
than invent a place-name match. Reverse geocoding is not performed by the
pipeline.

## Ground-truth independence

Prompts include the event name/type, location or coordinates, and reference
time. They do not include the collector's evacuation conclusion or the answer
being evaluated. Models are asked to search and cite current information
independently. Analysis should score at least:

- Whether search was recorded
- Cited URL/domain and official-source status
- Match to the ground-truth authority or alert
- Evacuate, shelter, avoid travel, wait, or other recommended action
- Temporal freshness
- Unsupported claims or conflicts with ground truth

This is an API live-search condition, not an exact reproduction of the free
consumer ChatGPT, Claude, or Gemini interfaces.

## Storage and transition safety

V3 keeps the existing S3 layout. Stable `event_id` joins weather and AI data;
unique `message_id` identifies one exact AI cycle:

```text
.../EVT-.../
  EVT-..._weather/
  EVT-..._AI/
    AI_RESULTS.md
    responses.json
    runs/MSG-.../
```

Existing `runs/MSG-.../` folders are retained. The files directly under
`EVT-..._AI/` are convenience copies of the latest complete run and may advance
normally; bucket versioning preserves older object versions.

Before the V3 deployment, stop both processes, finish any V2 `RUNNING` or
`RETRY` job, and back up the collector database, outbox, worker database, and
local results. Continue using the same databases. Never start a second fresh
collector against the same bucket/prefix, because S3 is an archive and does not
allocate the collector's next numeric event ID.

Record the following before unattended collection:

1. Last V2 UTC timestamp and first V3 UTC timestamp.
2. Approved Git commit and `study-v3.0.0` tag.
3. Successful mock and one-event real-provider pilot.
4. Provider billing/budget-alert confirmation.
5. S3 bucket, region, and prefix—never credentials.
6. Confirmation that the authoritative host retained both SQLite databases.
