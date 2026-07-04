---
created: 2026-05-25
last_edited: 2026-05-25
version: 0.1
provenance: con_hnCNKu4MfUQuWaDn
---

# AI Wizard Methodology

AI Wizard treats AI fluency as observed operating maturity, not self-declared knowledge.

## Diagnostic Instinct Axes

1. Mental Model Accuracy
2. Decomposition Instinct
3. Failure Recognition
4. Tool-Agnostic Thinking
5. Delegation Judgment
6. Iteration / Refinement

## Core Primitive Axes

1. System Composition
2. Pipeline Thinking
3. Tool Thinking
4. Integration Thinking
5. Orchestration & Trust Boundaries
6. Feedback Loops

## Meta-Primitive Axes

1. Context Engineering
2. State Awareness
3. Error Recovery

## Maturity Stages

| Stage | Label | Meaning |
|---|---|---|
| 0 | AI Consumer | Isolated answers, little reuse |
| 1 | Prompt Practitioner | Reuses prompts and verifies sometimes |
| 2 | Workflow Designer | Decomposes tasks into repeatable flows |
| 3 | Tool Builder | Builds reusable surfaces |
| 4 | Systems Operator | Integrates systems and manages trust/state |
| 5 | Compounding Builder | Designs logs, history, evals, and feedback loops |
| 6 | Technically Dangerous | Independently decomposes novel problems and ships systems |

## Scoring Philosophy

The score compresses the profile; it does not replace it. A high score requires evidence across primitives, meta-primitives, verification behavior, state awareness, and recovery behavior.

AI Wizard reports a `raw_score` and a `calibrated_range`. The raw score is deterministic for the collected evidence and scoring path. The calibrated range widens when evidence is sparse, source coverage is skewed, or semantic adjudication is failed, partial, or not requested. The range narrows only when coverage is stronger and semantic-Zo or replayed semantic reviews complete.

## Evidence Standards

Claims should be backed by evidence pointers. When evidence is missing, the profile should report uncertainty instead of inferring capability.

## Scan Concepts

- **Quick:** deterministic heuristic profile, usually `--no-semantic`.
- **Balanced:** default capped profile. It limits evidence volume and uses heuristic fallback unless semantic-Zo is explicitly requested.
- **Deep:** full profile with more evidence, optionally `--semantic-provider zo`. Do not call this semantic-Zo unless the run reports `semantic_status: complete`.

## Semantic and Fallback Contract

Heuristic runs are keyword and evidence-metadata based. They are useful for local regression and quick profiling but are not LLM adjudication.

Semantic-Zo runs require an available Zo identity token. They send compact redacted packets to `/zo/ask`, save normalized reviews to `semantic-reviews.jsonl`, and can resume from that checkpoint with `--semantic-resume`. If the provider fails, times out, or returns malformed JSON, the run records retry/fallback events and keeps the profile output honest with failed or partial semantic status.

## Dogfood Mode

`--dogfood` evaluates the run itself. It writes dogfood diagnostics with runtime, evidence coverage, semantic status, retry/fallback events, scoring volatility, and suggested verification commands. Dogfood mode is an evaluator report, not a public dossier.
