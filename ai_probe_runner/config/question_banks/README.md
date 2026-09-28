# Question banks

The runner combines `general.json` with exactly one file from `hazards/`. The
v2 trigger adapter chooses that hazard file from the collected `event_type` and
headline. It never asks an AI model to invent or select research questions.

## Current structure

Every supported event receives five general questions covering:

1. Current status, source, and reference time.
2. Immediate protective action.
3. Official referral sources.
4. Evacuation versus shelter decisions.
5. Uncertainty and facts that cannot be confirmed.

The matching hazard bank adds four questions about risks and decisions specific
to floods, wildfires, tropical cyclones, tornadoes, or earthquakes. A complete
event therefore produces nine prompts per enabled AI target.

## Question format

Each file must contain one JSON list. Each question must have:

```json
{
  "question_id": "flood-road-001",
  "category": "protective-action",
  "template": "Is it safe to drive through flooded roads in {area} during this {event}?"
}
```

- `question_id` is a permanent identifier. Do not reuse an old ID for new wording.
- `category` is an analysis label shared across comparable questions.
- `template` is the exact user-facing prompt before trigger fields are inserted.

IDs must be unique across `general.json` and every hazard file that can be paired
with it. The runner rejects missing fields, missing template values, missing
bank files, and duplicate IDs before contacting a provider.

## Trigger placeholders

Recommended placeholders are:

| Placeholder | v2 origin | Example |
| --- | --- | --- |
| `{event}` | `event_type` | `flash flood` |
| `{area}` | `location` | `Garfield County, Colorado` |
| `{timestamp}` | `sent_at`, then `generated_at` | `2026-09-28T16:00:00Z` |
| `{severity}` | `severity` | `Severe` |
| `{urgency}` | `urgency` | `Immediate` |
| `{certainty}` | `certainty` | `Likely` |

`{source}` and `{source_id}` are also available, but including them reveals
ground-truth provenance to the model. Use them only when the research question
deliberately tests source-aware behavior.

## Editing checklist

Before accepting a new or changed question:

1. Write it as a plausible question from a person seeking help.
2. Include `{area}` and `{event}` when location and hazard specificity matter.
3. Use `{timestamp}` when asking about current status, duration, or timing.
4. Ask one interpretable thing; avoid combining many unrelated decisions.
5. Do not put the correct answer, official action, or ground-truth status into
   the wording unless disclosure is part of the experiment.
6. Avoid asking for a specific route unless the question also requires current
   local verification; stale evacuation routes can be dangerous.
7. Give changed wording a new question ID or explicitly version the protocol.
8. Run `uv run pytest` and a mock cycle before using real API credits.
9. Review changes with the teammate responsible for the research question bank.

Question wording is part of the research protocol. Preserve the Git commit and
question-bank hashes recorded in each cycle rather than editing banks silently
during a collection period.
