---
created: 2026-06-02
last_edited: 2026-06-02
version: 0.1
provenance: ai-wizard-interpreter
---

# AI Wizard Score Formula (as interpreted)

This documents the scoring math the interpreter relies on. It is mirrored from
`Skills/ai-wizard/scripts/ai_wizard.py` (`compute_score`, `maturity_stage`,
`archetype`) **as of 2026-06-02**. The interpreter duplicates these constants
deliberately so it can reconstruct and *verify* a score without importing
ai-wizard. If ai-wizard changes its formula, the interpreter's self-check
(`verify`) will report a non-zero delta instead of silently lying — that is the
signal to update this file and the constants in `scripts/interpret.py`.

## Inputs stored in `profile.json`

- `axes` — three sections, each a map of axis → `{score (0–1), confidence, evidence_ids}`.
- `score.explanation` — the authoritative per-section averages (0–1).
- `score.overall`, `score.confidence`, `score.band`, `score.range`.
- `maturity_stage.{level,label}`, `archetype.name`.
- `semantic.{provider,status}`, `coverage.{evidence_records,dimensions}`.

## Section weights

| Section | Weight |
|---|---|
| `vibe_pill_primitives` (what you build) | 0.47 |
| `diagnostic_instincts` (how you think) | 0.28 |
| `meta_primitives` (how you sustain) | 0.25 |

## Score equation

```
total          = Σ (section_average * section_weight)          # 0..1
coverage_mult  = 0.72 + min(0.22, coverage * 0.22)              # 0.72..0.94
conf_adjusted  = total * coverage_mult + (0.04 if semantic else 0)
overall        = round(conf_adjusted * 1000)                    # 0..1000
```

`coverage` = `min(1.0, evidence_records / reference_records)`, where
`reference_records` is `min(semantic_cap, 24)` in capped depth (default) or 250
in full depth. A typical capped run hits coverage = 1.0, so `coverage_mult` =
0.94.

## Confidence + range

```
confidence  = round(min(0.9, 0.4 + coverage*0.3 + (0.12 if semantic else 0)), 3)
uncertainty = round((1.0 - confidence) * 170)
range.low   = max(0, overall - uncertainty)
range.high  = min(1000, overall + uncertainty)
```

The interpreter inverts the confidence equation to recover `coverage` exactly,
then tests both semantic states (True/False) and keeps whichever reproduces
`overall`. It recomputes `range` with this formula when a profile doesn't store
one.

## Bands

| Band | Range |
|---|---|
| advanced | ≥ 820 |
| strong | 650–819 |
| developing | 400–649 |
| emerging | 1–399 |
| insufficient-evidence | coverage ≤ 0 |

## Maturity stage

```
avg_core  = mean(vibe_pill_primitives axis scores)
avg_meta  = mean(meta_primitives axis scores)
combined  = avg_core*0.62 + avg_meta*0.38
```

| combined ≥ | level | label |
|---|---|---|
| 0.86 | 6 | Technically Dangerous |
| 0.72 | 5 | Compounding Builder |
| 0.58 | 4 | Systems Operator |
| 0.44 | 3 | Tool Builder |
| 0.30 | 2 | Workflow Designer |
| 0.16 | 1 | Prompt Practitioner |
| else | 0 | AI Consumer |

## Archetype (optional marketing layer)

| overall < | name |
|---|---|
| 375 | White Rabbit |
| 600 | Kung Fu Master |
| 820 | Spoon Bender |
| else | The One |
