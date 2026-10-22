# Study V3 question banks

These prompts define the live-search study condition. Do not edit them after
collection begins. Create a new versioned directory for any later prompt
change.

- A recognized `NEW_EVENT` receives two general questions and one
  hazard-specific question: 3 questions per model, 9 provider calls total.
- `STATUS_CHANGED`, `SEVERITY_CHANGED`, and `ESCALATION` receive one
  consolidated update question: 1 question per model, 3 calls total.
- A filtered natural-disaster family without a specific file still receives
  the general questions instead of being skipped.
- Coordinate-only EONET locations are rendered as longitude and latitude. The
  prompt tells the model not to invent a place-name match.

Every prompt requests one focused live search. OpenAI and Anthropic also use a
one-tool-call API cap from `targets.study-v3-search.json`. Gemini does not offer
the same per-request hard cap in this integration, so the one-search instruction
is the cost control and actual search calls are recorded in each result.
