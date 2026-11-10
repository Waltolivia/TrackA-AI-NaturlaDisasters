# Study V3 question banks

These prompts define the live-search study condition. On 2026-11-09 their
wording was minimally revised to sound more like direct user questions, include
the event timestamp consistently, and request answers under 250 words. The
question IDs, categories, schedule, models, and search condition did not
change. Record the actual UTC deployment time so pre-repair and post-repair
responses remain distinguishable. Do not make another wording change without a
documented method transition.

- A recognized `NEW_EVENT` receives two general questions and one
  hazard-specific question: 3 questions per model, 9 provider calls total.
- `STATUS_CHANGED`, `SEVERITY_CHANGED`, and `ESCALATION` receive one
  consolidated update question: 1 question per model, 3 calls total.
- A filtered natural-disaster family without a specific file still receives
  the general questions instead of being skipped.
- Coordinate-only EONET locations are rendered as longitude and latitude. The
  prompt tells the model not to invent a place-name match.

Every prompt requests current web information. OpenAI and Anthropic also use a
one-tool-call API cap from `targets.study-v3-search.json`. Gemini does not offer
the same per-request hard cap in this integration, so actual search calls are
recorded in each result and must be monitored.
