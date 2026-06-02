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
