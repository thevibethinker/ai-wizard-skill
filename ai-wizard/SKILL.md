---
name: ai-wizard
description: Generate an observed AI fluency profile from real AI usage traces, workspace artifacts, and Vibe Pill methodology. Use when assessing how someone actually works with AI across systems, not when running a self-report quiz.
compatibility: Created for Zo Computer; baseline mode also supports exported Claude/Codex/ChatGPT-style conversation folders.
metadata:
  author: va.zo.computer
  version: "0.2.0"
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
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --no-semantic --dogfood
python3 Skills/ai-wizard/scripts/ai_wizard.py profile --semantic-provider zo --semantic-resume
python3 Skills/ai-wizard/scripts/ai_wizard.py report --latest
python3 Skills/ai-wizard/scripts/ai_wizard.py history
```

## Defaults

- Local-first.
- Capped scan depth by default.
- Heuristic fallback by default; semantic-Zo is only active when `--semantic-provider zo` is requested and the profile reports `semantic_status: complete`.
- Quick scan is `--no-semantic`; balanced scan is default capped mode; deep scan is `--depth full` and may be paired with `--semantic-provider zo`.
- No external upload.
- Public report redacts raw private evidence unless explicitly configured otherwise.
- Semantic provider failures, timeouts, and malformed responses are recorded in `semantic_events`; outputs still write with deterministic fallback scoring.
- `--semantic-resume` reuses `semantic-reviews.jsonl` checkpoints in the target run directory.
- `--dogfood` writes evaluator diagnostics (`dogfood-report.json` and `dogfood-report.md`) without raw private evidence.

## Evidence sources (zo-native mode)

Three sources, allocated 60/30/10 of `--artifact-limit` and rebalanced when one under-delivers:

| Source | What it collects | Where |
|---|---|---|
| `workspace` | Build plans, skills, prompts (md/py/json/yaml/ts) | Auto-detected roots (`N5/builds`, `Skills`, `Prompts`) or `AI_WIZARD_ROOTS` |
| `conversations` | Real operator messages from AI session traces | `~/.claude/projects` Claude Code JSONL + `N5/logs/threads` exports, or `AI_WIZARD_TRACE_DIRS` / `--trace-dir` |
| `git` | Commit history (subjects + bodies) | Workspace git repo |

- Select sources with `--sources workspace,conversations,git` (default: all).
- Conversation traces are deduped, filtered of synthetic/system messages, and exclude ai-wizard's own sessions to prevent self-inflation.
- Environment overrides (all optional, colon-separated paths): `AI_WIZARD_WORKSPACE`, `AI_WIZARD_ROOTS`, `AI_WIZARD_TRACE_DIRS`, `AI_WIZARD_ZO_MODEL`. Empty `AI_WIZARD_TRACE_DIRS` disables trace collection. On a machine without N5, roots fall back to scanning the workspace itself — no N5 layout required.

## Outputs

Default outputs are written to `Databases/ai-wizard/runs/<run-id>/`, or to the supplied `--out` directory.

The local history database is `Databases/ai-wizard/ai_wizard_history.sqlite`.
