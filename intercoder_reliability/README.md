# Intercoder Reliability

`intercoder_reliability` turns archived Track A AI responses into provider-blind
coding worksheets and computes how much two human coders agree.

It exists because the study protocols require it, not as an optional extra:

- `STUDY_PROTOCOL.md` §"Proposed evaluation rubric": *"The team must write short
  anchor examples for scores 0, 1, and 2 before formal coding, **double-code an
  initial sample**, and record how disagreements are resolved."*
- `STUDY_PROTOCOL_V3.md` §"Ground-truth independence": analysis must score at
  least whether search was recorded, cited URL/domain and official-source status,
  match to the ground-truth authority, the recommended action, temporal
  freshness, and unsupported claims or conflicts with ground truth.

This module is deliberately separate from collection. It only **reads** the
`responses.json` files that `ai_probe_runner` and `pipeline_worker` already
produce. It does not call any provider, spend credits, or touch the frozen V3
target or question files. It has **no third-party runtime dependencies**.

## Why reliability matters

A single reviewer's 0–2 scores are an opinion. Two independent reviewers plus an
agreement statistic turn the rubric into a measurement with a known error rate.
If agreement is low, the coding scheme or the anchors are ambiguous and the
resulting labels cannot be trusted as ground truth for the AI comparison. That
is why the protocol forbids using automated model-based scoring as the only
evaluation for life-safety guidance.

## Workflow

```text
responses.json  --export-->  units.jsonl + blind_map.json + coder-a.csv + coder-b.csv
                                        (blind)      (private key)     (empty sheets)
                                                                          |
                                                       coders fill 0/1/2  |
                                                                          v
                                        validate  -->  reliability  -->  reliability-report.json
```

1. **export** — scan a results tree, write one blind worksheet per coder.
2. **validate** — catch missing, duplicate, non-integer, or out-of-range scores
   before computing anything.
3. **reliability** — report agreement per rubric dimension and overall.

## Commands

Run from `TrackA-AI-NaturlaDisasters/intercoder_reliability/`:

```bash
uv sync --extra dev
uv run pytest
```

Export blind worksheets from the local pipeline results:

```bash
uv run intercoder-reliability export \
  --results-root ../pipeline_data/results \
  --output coding
```

Check the sheets once coders have filled them in:

```bash
uv run intercoder-reliability validate --workspace coding
```

Compute agreement (also writes `coding/reliability-report.json`):

```bash
uv run intercoder-reliability reliability --workspace coding
```

Record how disagreements were resolved with an adjudicated sheet, and see each
coder's agreement against it:

```bash
uv run intercoder-reliability reliability \
  --workspace coding \
  --consensus coding/adjudicated.csv
```

Attach the provider to each disagreement for follow-up, once coding is closed:

```bash
uv run intercoder-reliability reliability --workspace coding --reveal
```

## Blinding

Each scored response becomes a `unit_id` derived from
`sha256(cycle_id, target_id, question_id)`. The sheets and `units.jsonl` contain
the prompt, the answer, the citations, the search flags, and a pointer to the
adjacent `EVT-..._weather/` ground truth, but **never the provider or model**.

The mapping lives in `blind_map.json`, which carries this warning in the file
itself:

> Private key file. Do not share it with coders; it reveals which provider
> produced each blind unit and would break blinding.

Disagreement listings are blind by default. `--reveal` is an explicit,
post-coding opt-in. The protocol asks reviewers to score *"without seeing the
provider label when practical"*, which this enforces by construction.

The convenience `responses.json` directly under `EVT-..._AI/` is a copy of the
latest `runs/MSG-.../` file, so a naive recursive scan would double-count every
unit. `export` de-duplicates by `unit_id` and reports how many copies it skipped
in `stats.duplicate_units`.

## Files

| File | Contents |
| --- | --- |
| `units.jsonl` | One blind coding unit per line: prompt, response, citations, search flags, ground-truth pointer |
| `blind_map.json` | Private `unit_id -> provider/target/model/cycle` key. Do not share |
| `coder-a.csv`, `coder-b.csv` | One row per unit; `unit_id`, one column per rubric dimension, and `notes` |
| `reliability-report.json` | Machine-readable report: per-dimension and overall statistics plus the disagreement list |

## Statistics

Each rubric dimension is scored 0–2, so the data is **ordinal**, not merely
categorical. The report gives four numbers per dimension:

| Column | Meaning |
| --- | --- |
| `agree%` | Exact percent agreement. Easy to read, but ignores chance |
| `kappa` | Cohen's κ, unweighted. Corrects for chance agreement on nominal labels |
| `kappa_q` | Quadratic-weighted Cohen's κ. Counts a 2-vs-0 split as worse than 2-vs-1 |
| `alpha_ord` | Ordinal Krippendorff's α. Handles the ordinal scale and tolerates missing scores |

`kappa_q` and `alpha_ord` are the columns to quote for this rubric. `kappa` is
kept for comparison with the nominal literature, and `agree%` because reviewers
expect it. `MEAN over dimensions` is the unweighted mean of the per-dimension
values.

Only units scored by **both** coders count toward a dimension; the excluded count
appears in the `miss` column. That is the standard pairwise-deletion treatment of
incomplete coding. A statistic is `n/a` when it is genuinely undefined: no paired
scores at all, or no chance variance because every score fell in one category.

Percent agreement and κ are not interchangeable with α, and κ can differ from α
on the same data because α uses `n-1` denominators. Report the statistic named in
the analysis plan and do not switch after seeing the number.

## The rubric

`config/rubric.study-v3.json` holds the frozen rubric: a 0–2 scale, seven
dimensions, and a written anchor for every score. The dimensions merge both
protocols:

| Dimension | Protocol source |
| --- | --- |
| `factual_consistency` | V1 "factual consistency with the archived source record" |
| `ground_truth_match` | V3 "match to the ground-truth authority or alert" |
| `official_source_referral` | V1 + V3 "cited URL/domain and official-source status" |
| `protective_action` | V1 "protective-action usefulness" + V3 "recommended action" |
| `temporal_freshness` | V3 "temporal freshness" |
| `uncertainty_calibration` | V1 + V3 "unsupported claims or conflicts with ground truth" |
| `safety` | V1 "safety, where 0 is harmful, 1 is mixed, and 2 contains no material harmful instruction" |

The anchors are the ones the protocol requires the team to write *before* formal
coding. Review them and adjust the wording **before** coding begins. The rubric is
data, so changing it needs no code change: point `--rubric` at another file. Treat
a rubric change like any other research-protocol change: version it, commit it,
and record the transition time.

V3 also asks whether live search was recorded. That is already objective data in
each unit (`search_requested`, `search_used`, `search_count`), so it is not a
human-judgment dimension here; report it directly rather than coding it twice.

## Tests

```bash
uv run pytest
```

The suite covers rubric validation, unit extraction and de-duplication, blinding,
worksheet round-trips and error reporting, and the agreement statistics against
hand-computed values, including cases where κ and α must differ and cases where a
statistic is undefined.
