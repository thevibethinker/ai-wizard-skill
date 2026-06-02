---
name: ai-wizard-interpreter
description: Explain an AI Wizard dossier (profile.json) in plain language — what the score means, exactly how it was computed, what drove it up or down, how confident it is, and what to do next. Use when someone submits their AI Wizard result and wants it interpreted. Read-only; never runs or modifies the ai-wizard skill.
compatibility: Created for Zo Computer. Consumes AI Wizard profile.json output (any version that stores score + axes + maturity_stage).
metadata:
  author: va.zo.computer
  version: "0.1.0"
  created: "2026-06-02"
---

# AI Wizard Interpreter

The `ai-wizard` skill produces a score but isn't very explainable on its own. This skill is the **interpreter layer**: hand it a dossier and it explains the result the way a coach would — grounded in the actual scoring math, not vibes.

It is strictly **read-only** toward `ai-wizard`: it never imports, runs, or edits that skill. It only reads the `profile.json` that ai-wizard already emitted.

## What "submit your dossier" means

A dossier is the `profile.json` AI Wizard writes to `Databases/ai-wizard/runs/<run-id>/profile.json`. People can submit it three ways:

1. **A file** they hand you (any path to a `profile.json`, or a run directory).
2. **A run id** already in `Databases/ai-wizard/runs/`.
3. **The latest run** on this workspace.

## Commands

```bash
# Explain a specific dossier file
python3 Skills/ai-wizard-interpreter/scripts/interpret.py explain --profile <path/to/profile.json>

# Explain by run id
python3 Skills/ai-wizard-interpreter/scripts/interpret.py explain --run <run-id>

# Explain the most recent run
python3 Skills/ai-wizard-interpreter/scripts/interpret.py explain --latest

# Machine-readable explanation (for a UI/API)
python3 Skills/ai-wizard-interpreter/scripts/interpret.py explain --latest --format json

# Save a copy of the report (markdown or json) alongside printing it
python3 Skills/ai-wizard-interpreter/scripts/interpret.py explain --run <run-id> --out report.md
```

## How to run this skill

1. Locate the dossier (ask for a file, a run id, or use `--latest`).
2. Run `explain`. Default output is human-readable markdown.
3. Present the markdown to the person. If it's going into a page/API, use `--format json`.
4. If the script prints a `WARNING: score reconstruction off by N points`, ai-wizard's scoring formula has changed — tell the person the math walk-through is approximate and flag it for maintenance (see `references/score-formula.md`).

## What the explanation contains

- **Headline:** score/1000, plain-language band, honest range, maturity stage + meaning, archetype.
- **The actual math:** the three skill groups, each group's 0–1 average, its weight, and roughly how many of the 1000 points it contributed — then the exact final equation. This is **reconstructed from the profile and verified against the profile's own `overall`**, so it's faithful, not a paraphrase.
- **What pushed the score UP / DOWN:** the strongest and weakest individual axes, in plain English.
- **How much to trust each part:** per-dimension confidence (when the profile stores it) and semantic-review status.
- **Honest caveats, risks, and a prioritized "do these next" plan.**

## Design notes

- **Faithful, not invented.** The score formula constants live in `references/score-formula.md` and are mirrored in the script. The interpreter solves for the two hidden inputs (evidence coverage and the semantic bonus) by inverting ai-wizard's confidence formula, then checks that its reconstruction reproduces the stored score. If it can't (delta > 1 point), it says so rather than bluffing.
- **Degrades gracefully.** Older profiles that lack `range` or per-dimension `confidence` still work — the range is recomputed from confidence using ai-wizard's documented uncertainty formula, and missing dimension data is stated plainly.
- **No external actions.** Output is printed (and optionally written to a path you choose). Nothing is sent, published, or uploaded.

## Outputs

By default the explanation is printed to stdout. With `--out <path>` it is also written there (use `--dry-run` to preview without writing).
