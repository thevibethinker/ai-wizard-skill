---
created: 2026-05-25
last_edited: 2026-05-25
version: 0.1
provenance: con_hnCNKu4MfUQuWaDn
---

# AI Wizard

AI Wizard is an observed AI fluency profiler. It reads real usage traces and workspace artifacts to build a practical profile of how someone works with AI.

It is not primarily a quiz and not just a leaderboard. The score is a summary; the useful object is the profile.

## What It Produces

- AI operator profile
- Vibe Pill maturity stage
- Optional public archetype
- Fluency map across diagnostic instincts, core primitives, and meta-primitives
- Evidence dossier
- Risks and missing evidence
- Next-build plan
- Secondary score
- Local history database

## Quick Start

```bash
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --mode zo-native --depth capped
```

Baseline mode for exported traces:

```bash
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --mode baseline --input /path/to/export
```

Fast deterministic mode:

```bash
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --no-semantic
```

Dogfood diagnostics for evaluating AI Wizard itself:

```bash
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --no-semantic --dogfood
```

## Scan Depths

AI Wizard currently supports three practical scan concepts:

- **Quick scan:** `--no-semantic`, usually with the default capped scan. This is deterministic and fast. It writes the same profile artifacts but reports `semantic_mode: heuristic` and `semantic_status: not_requested`.
- **Balanced scan:** default `profile --depth capped`. Today this still uses the heuristic fallback unless a semantic provider is explicitly requested. It bounds evidence review with `--semantic-cap`.
- **Deep scan:** `--depth full`, optionally with `--semantic-provider zo`. Full depth inspects more collected evidence. It should only be described as semantic-Zo when the resulting profile reports `semantic_status: complete`.

## Semantic Behavior

The default and `--semantic-provider heuristic` paths are deterministic heuristic runs. They do not call Zo and must not be described as LLM-adjudicated semantic success.

`--semantic-provider zo` requires `ZO_CLIENT_IDENTITY_TOKEN`. When requested, AI Wizard samples redacted evidence packets, calls `/zo/ask`, writes replayable `semantic-reviews.jsonl`, and sets `semantic_mode: semantic-zo`. Runtime failures, malformed responses, or timeouts are recorded in `semantic_events`; failed or partial runs keep producing local outputs with deterministic fallback scoring.

Use `--semantic-reviews <path>` to replay saved reviews without another provider call. Use `--semantic-resume` to reuse the run directory checkpoint and request only missing reviews.

## Evidence, Calibration, and Ranges

Every run writes `inventory.json` plus profile-level `coverage`, `dimension_coverage`, and `dimension_dossier` fields. Coverage reports the number and type of evidence records, source roots, unavailable source classes, and skew warnings.

The user-facing score is `raw_score`; `calibrated_range` expresses uncertainty from evidence count, source skew, and semantic status. A wide range or low confidence is expected when evidence is sparse, concentrated in one root, or semantic adjudication is failed, partial, or not requested.

## Privacy and Fallback Guarantees

AI Wizard is local-first. It writes local artifacts under `Databases/ai-wizard/runs/<run-id>/` or the supplied `--out` directory. It does not publish, upload, or send outputs externally.

Public markdown outputs redact raw private evidence by default. Semantic-Zo packets are compact and redacted before provider calls. If semantic-Zo is unavailable or fails, the run records the limitation and falls back to deterministic heuristic scoring rather than claiming semantic success.

## Methodology

AI Wizard combines:

- the old Vibe Pill AI Fluency Test dimensions,
- the Vibe Pill primitives framework,
- the Vibe Pill identity arc,
- and evidence from actual AI collaboration.

The old diagnostic asked what a person would do. AI Wizard observes what they actually do.

## Privacy

AI Wizard is local-first. The default report summarizes evidence and stores local pointers instead of dumping private transcripts. Public share cards are redacted by default.

## Migration Note

Earlier internal work used the name `wizard-score`. This skill supersedes that prototype as `ai-wizard`.
