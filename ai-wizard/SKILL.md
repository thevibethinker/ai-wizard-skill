---
name: ai-wizard
description: Generate an observed AI fluency profile from real AI usage traces, workspace artifacts, and Vibe Pill methodology. Use when assessing how someone actually works with AI across systems, not when running a self-report quiz.
compatibility: Created for Zo Computer; baseline mode also supports exported Claude/Codex/ChatGPT-style conversation folders.
metadata:
  author: va.zo.computer
  version: "0.1.0"
  created: "2026-05-25"
---

# AI Wizard

AI Wizard produces an observed AI fluency profile. It is profile-first and score-second:

1. Profile and maturity stage
2. Evidence dossier
3. Primitive fluency map
4. Risks and missing evidence
5. Next-build plan
6. Secondary score

It is grounded in Vibe Pill methodology:

- Old AI Fluency Test dimensions: mental model accuracy, decomposition, failure recognition, tool-agnostic thinking, delegation judgment, iteration/refinement
- Vibe Pill primitives: system composition, pipeline thinking, tool thinking, integration thinking, orchestration/trust boundaries, feedback loops
- Meta-primitives: context engineering, state awareness, error recovery

## Commands

```bash
python3 Skills/ai-wizard/scripts/ai_wizard.py scan
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --mode zo-native --depth capped
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --mode baseline --input Skills/ai-wizard/tests/fixtures/baseline
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --no-semantic
python3 Skills/ai-wizard/scripts/ai_wizard.py history
```

## Defaults

- Local-first.
- Capped semantic depth by default.
- No external upload.
- Public report redacts raw private evidence unless explicitly configured otherwise.

## Outputs

Default outputs are written to `Databases/ai-wizard/runs/<run-id>/`, or to the supplied `--out` directory.

The local history database is `Databases/ai-wizard/ai_wizard_history.sqlite`.
