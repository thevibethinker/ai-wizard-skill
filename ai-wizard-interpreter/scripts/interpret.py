#!/usr/bin/env python3
"""AI Wizard Interpreter.

Reads an AI Wizard dossier (profile.json) and produces a plain-language,
arithmetic-faithful explanation of the score: what it means, exactly how it
was computed, what pushed it up or down, how confident it is, and what to do
next.

This tool is READ-ONLY with respect to the ai-wizard skill. It never imports,
modifies, or re-runs ai-wizard. It only interprets the JSON that ai-wizard
already emitted. The score formula is reconstructed from the documented
weights and the section averages stored in the profile, then verified against
the profile's own `overall` so the explanation is provably faithful rather
than a paraphrase.

Usage:
    python3 interpret.py explain --profile <path/to/profile.json>
    python3 interpret.py explain --run <run_id>
    python3 interpret.py explain --latest
    python3 interpret.py explain --latest --format json
    python3 interpret.py explain --profile <path> --out report.md --dry-run

Exit codes: 0 success, 1 failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants mirrored from ai-wizard (compute_score / maturity_stage / archetype).
# These are duplicated DELIBERATELY so the interpreter can reconstruct and
# verify the score without importing ai-wizard. If ai-wizard's formula changes,
# the self-check (verify_reconstruction) will flag the drift instead of lying.
# ---------------------------------------------------------------------------
SECTION_WEIGHTS = {
    "diagnostic_instincts": 0.28,
    "vibe_pill_primitives": 0.47,
    "meta_primitives": 0.25,
}

SECTION_LABELS = {
    "diagnostic_instincts": "Diagnostic Instincts",
    "vibe_pill_primitives": "Vibe Pill Primitives",
    "meta_primitives": "Meta-Primitives",
}

SECTION_MEANING = {
    "diagnostic_instincts": (
        "how you THINK with AI — whether you verify outputs, break problems "
        "down, catch failures, stay tool-agnostic, delegate wisely, and iterate"
    ),
    "vibe_pill_primitives": (
        "what you BUILD with AI — composing systems, designing pipelines, "
        "making tools, wiring integrations, setting trust boundaries, and "
        "closing feedback loops (weighted heaviest, ~47%)"
    ),
    "meta_primitives": (
        "how you SUSTAIN AI work — engineering context, tracking state, and "
        "recovering from errors"
    ),
}

AXIS_PLAIN = {
    "mental_model_accuracy": "Mental Model Accuracy (do you check what's true vs. trust the output)",
    "decomposition_instinct": "Decomposition Instinct (breaking big asks into steps/phases)",
    "failure_recognition": "Failure Recognition (spotting when AI is wrong or hallucinating)",
    "tool_agnostic_thinking": "Tool-Agnostic Thinking (portable ideas, not locked to one tool)",
    "delegation_judgment": "Delegation Judgment (knowing what to hand off vs. gate)",
    "iteration_refinement": "Iteration & Refinement (debugging and improving, not re-rolling)",
    "system_composition": "System Composition (wiring parts into a working whole)",
    "pipeline_thinking": "Pipeline Thinking (source → transform → store → deliver)",
    "tool_thinking": "Tool Thinking (building reusable surfaces: CLIs, forms, routes)",
    "integration_thinking": "Integration Thinking (APIs, webhooks, syncs, OAuth)",
    "orchestration_trust_boundaries": "Orchestration & Trust Boundaries (approval gates, dry-runs)",
    "feedback_loops": "Feedback Loops (logs, history, evals that make things improve)",
    "context_engineering": "Context Engineering (personas, rules, source selection)",
    "state_awareness": "State Awareness (status, checkpoints, idempotency)",
    "error_recovery": "Error Recovery (hypotheses, root cause, breaking loops)",
}

# Stage ladder (level -> what it signals). Mirrors methodology.md.
STAGE_MEANING = {
    0: "Isolated answers, little reuse.",
    1: "Reuses prompts and verifies sometimes.",
    2: "Decomposes tasks into repeatable flows.",
    3: "Builds reusable surfaces (tools).",
    4: "Integrates systems and manages trust/state.",
    5: "Designs logs, history, evals, and feedback loops.",
    6: "Independently decomposes novel problems and ships systems.",
}

BAND_PLAIN = {
    "advanced": "Advanced — top tier of observed fluency.",
    "strong": "Strong — well above typical, with clear system-building habits.",
    "developing": "Developing — solid instincts forming, gaps still visible.",
    "emerging": "Emerging — early signal; foundations present but thin.",
    "insufficient-evidence": "Insufficient evidence — not enough usable signal to score reliably.",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fail(msg: str) -> "Any":
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Locating the dossier
# ---------------------------------------------------------------------------
def runs_root() -> Path:
    import os

    workspace = Path(os.environ.get("AI_WIZARD_WORKSPACE", "/home/workspace")).resolve()
    return workspace / "Databases/ai-wizard/runs"


def resolve_profile_path(args: argparse.Namespace) -> Path:
    if args.profile:
        p = Path(args.profile)
        if p.is_dir():
            p = p / "profile.json"
        if not p.exists():
            fail(f"profile not found: {p}")
        return p
    if args.run:
        p = runs_root() / args.run / "profile.json"
        if not p.exists():
            fail(f"run profile not found: {p}")
        return p
    if args.latest:
        root = runs_root()
        if not root.exists():
            fail(f"no runs directory at {root}")
        candidates = [d for d in root.iterdir() if d.is_dir() and (d / "profile.json").exists()]
        if not candidates:
            fail(f"no profile runs found under {root}")
        latest = max(candidates, key=lambda d: (d / "profile.json").stat().st_mtime)
        return latest / "profile.json"
    fail("provide one of --profile, --run, or --latest")


def load_profile(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(errors="ignore"))
    except json.JSONDecodeError as exc:
        fail(f"profile is not valid JSON ({path}): {exc}")
    if not isinstance(data, dict):
        fail(f"profile JSON is not an object: {path}")
    # Minimal shape check so we fail loudly rather than guess.
    missing = [k for k in ("score", "axes", "maturity_stage") if k not in data]
    if missing:
        fail(f"profile missing required keys {missing}; is this an AI Wizard profile.json?")
    return data


# ---------------------------------------------------------------------------
# Score reconstruction + verification
# ---------------------------------------------------------------------------
def section_averages(axes: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for section, axis_map in axes.items():
        if not isinstance(axis_map, dict) or not axis_map:
            continue
        vals = [float(v.get("score", 0.0)) for v in axis_map.values() if isinstance(v, dict)]
        out[section] = sum(vals) / len(vals) if vals else 0.0
    return out


def reconstruct_score(profile: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the score arithmetic from stored fields and solve for the two
    hidden inputs (coverage, semantic) by inverting the confidence formula.

    ai-wizard:
        total            = sum(section_avg * weight)
        confidence_adj   = total * (0.72 + min(0.22, coverage*0.22)) + (0.04 if semantic)
        overall          = round(confidence_adj * 1000)
        confidence       = round(min(0.9, 0.4 + coverage*0.3 + (0.12 if semantic)), 3)
    """
    axes = profile.get("axes", {})
    stored_score = profile.get("score", {})
    stored_overall = stored_score.get("overall")
    stored_conf = stored_score.get("confidence")
    stored_expl = stored_score.get("explanation", {})

    avgs = section_averages(axes)
    # Prefer the profile's own explanation averages when present (authoritative),
    # else use our recomputed per-axis averages.
    used_avgs = {k: float(stored_expl.get(k, avgs.get(k, 0.0))) for k in SECTION_WEIGHTS}

    total = sum(used_avgs[k] * SECTION_WEIGHTS[k] for k in SECTION_WEIGHTS)

    # Solve for semantic + coverage by testing the 2 semantic states against
    # the stored confidence, which pins coverage exactly.
    best = None
    for semantic in (True, False):
        sem_conf = 0.12 if semantic else 0.0
        if stored_conf is not None:
            # 0.4 + coverage*0.3 + sem_conf = conf  (unless clamped at 0.9)
            cov = (float(stored_conf) - 0.4 - sem_conf) / 0.3
            cov = max(0.0, min(1.0, cov))
        else:
            cov = 1.0
        sem_bonus = 0.04 if semantic else 0.0
        conf_adj = total * (0.72 + min(0.22, cov * 0.22)) + sem_bonus
        recon_overall = max(0, min(1000, round(conf_adj * 1000)))
        recon_conf = round(min(0.9, 0.4 + cov * 0.3 + sem_conf), 3)
        delta = abs(recon_overall - stored_overall) if stored_overall is not None else 0
        cand = {
            "semantic": semantic,
            "coverage": round(cov, 4),
            "total_weighted": round(total, 4),
            "coverage_multiplier": round(0.72 + min(0.22, cov * 0.22), 4),
            "semantic_bonus": sem_bonus,
            "reconstructed_overall": recon_overall,
            "reconstructed_confidence": recon_conf,
            "overall_delta": delta,
        }
        if best is None or delta < best["overall_delta"]:
            best = cand
    best["verified"] = stored_overall is not None and best["overall_delta"] <= 1
    best["stored_overall"] = stored_overall
    best["stored_confidence"] = stored_conf
    best["used_section_averages"] = {k: round(v, 4) for k, v in used_avgs.items()}
    return best


# ---------------------------------------------------------------------------
# Building the human explanation
# ---------------------------------------------------------------------------
def section_contributions(recon: dict[str, Any]) -> list[dict[str, Any]]:
    avgs = recon["used_section_averages"]
    rows = []
    for section, weight in SECTION_WEIGHTS.items():
        avg = avgs.get(section, 0.0)
        contrib = avg * weight
        rows.append({
            "section": section,
            "label": SECTION_LABELS[section],
            "meaning": SECTION_MEANING[section],
            "avg_0_1": round(avg, 3),
            "weight": weight,
            "weighted_contribution": round(contrib, 4),
            "points_of_1000": round(contrib * recon["coverage_multiplier"] * 1000),
        })
    rows.sort(key=lambda r: r["weighted_contribution"], reverse=True)
    return rows


def axis_rankings(axes: dict[str, Any]) -> dict[str, list[tuple[str, float, str]]]:
    flat: list[tuple[str, float, str]] = []
    for section, axis_map in axes.items():
        if not isinstance(axis_map, dict):
            continue
        for axis, payload in axis_map.items():
            if isinstance(payload, dict):
                flat.append((axis, float(payload.get("score", 0.0)), section))
    flat.sort(key=lambda x: x[1], reverse=True)
    return {"strengths": flat[:4], "weaknesses": list(reversed(flat[-4:]))}


def dimension_confidence_summary(profile: dict[str, Any]) -> dict[str, list[str]]:
    dims = (profile.get("coverage", {}) or {}).get("dimensions", {}) or {}
    out: dict[str, list[str]] = {"high": [], "medium": [], "low": []}
    for section in dims.values():
        if not isinstance(section, dict):
            continue
        for axis, payload in section.items():
            if isinstance(payload, dict):
                conf = payload.get("confidence", "low")
                if conf in out:
                    out[conf].append(axis)
    return out


def build_explanation(profile: dict[str, Any]) -> dict[str, Any]:
    recon = reconstruct_score(profile)
    score = profile.get("score", {})
    stage = profile.get("maturity_stage", {})
    archetype = profile.get("archetype", {})
    coverage = profile.get("coverage", {}) or {}
    interp = profile.get("score_interpretation", {}) or {}
    semantic = profile.get("semantic", {}) or {}

    contribs = section_contributions(recon)
    ranks = axis_rankings(profile.get("axes", {}))
    dim_conf = dimension_confidence_summary(profile)
    dimensions_present = bool((coverage.get("dimensions") or {}))

    # Range may be absent in older profiles; reconstruct it from ai-wizard's
    # own uncertainty formula: uncertainty = round((1 - confidence) * 170).
    stored_range = score.get("range") or {}
    overall = score.get("overall")
    conf = score.get("confidence")
    range_low = stored_range.get("low")
    range_high = stored_range.get("high")
    range_reconstructed = False
    if (range_low is None or range_high is None) and overall is not None and conf is not None:
        unc = round((1.0 - float(conf)) * 170)
        range_low = max(0, overall - unc)
        range_high = min(1000, overall + unc)
        range_reconstructed = True

    return {
        "interpreter_version": "0.1.0",
        "generated_at": now_iso(),
        "run_id": profile.get("run_id"),
        "headline": {
            "score": score.get("overall"),
            "out_of": 1000,
            "band": score.get("band"),
            "band_plain": BAND_PLAIN.get(score.get("band", ""), score.get("band", "")),
            "range_low": range_low,
            "range_high": range_high,
            "range_reconstructed": range_reconstructed,
            "confidence": score.get("confidence"),
            "stage_level": stage.get("level"),
            "stage_label": stage.get("label"),
            "stage_meaning": STAGE_MEANING.get(stage.get("level"), ""),
            "archetype": archetype.get("name"),
        },
        "reconstruction": recon,
        "section_contributions": contribs,
        "strengths": [
            {"axis": a, "score": round(s, 3), "plain": AXIS_PLAIN.get(a, a)} for a, s, _ in ranks["strengths"]
        ],
        "weaknesses": [
            {"axis": a, "score": round(s, 3), "plain": AXIS_PLAIN.get(a, a)} for a, s, _ in ranks["weaknesses"]
        ],
        "dimension_confidence": dim_conf,
        "dimensions_present": dimensions_present,
        "evidence_records": coverage.get("evidence_records"),
        "semantic_status": {
            "provider": semantic.get("provider"),
            "status": semantic.get("status"),
            "note": semantic.get("note"),
        },
        "caveats": interp.get("warnings", []),
        "risks": profile.get("risks", []),
        "next_build_plan": profile.get("next_build_plan", []),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_markdown(exp: dict[str, Any]) -> str:
    h = exp["headline"]
    recon = exp["reconstruction"]
    today = datetime.now(timezone.utc).date().isoformat()

    verify_line = (
        "verified — the formula below reproduces the official score exactly"
        if recon.get("verified")
        else f"⚠️ reconstruction differs from stored score by {recon.get('overall_delta')} points; "
        "treat the formula walk-through as approximate (ai-wizard's scoring may have changed)"
    )

    lines = [
        "---",
        f"created: {today}",
        f"last_edited: {today}",
        "version: 0.1",
        "provenance: ai-wizard-interpreter",
        "---",
        "",
        "# What Your AI Wizard Score Means",
        "",
        f"## {h['score']}/{h['out_of']} — {h.get('band_plain', '')}",
        "",
        f"- **Likely range:** {h['range_low']}–{h['range_high']} "
        f"(confidence {h['confidence']}). The range is honest uncertainty: lower "
        "confidence = wider range."
        + ("  _(range derived from confidence; this profile didn't store one.)_"
           if h.get("range_reconstructed") else ""),
        f"- **Stage {h['stage_level']} — {h['stage_label']}:** {h['stage_meaning']}",
        f"- **Archetype:** {h['archetype']}",
        f"- **Evidence used:** {exp['evidence_records']} items.",
        "",
        "## How the score was built (the actual math)",
        "",
        "Your score is **not** a vibe. It's a weighted blend of three groups of "
        "skills, each scored 0–1, then scaled by how much evidence was available. "
        f"Reconstruction is **{verify_line}**.",
        "",
        "| Group | What it measures | Avg (0–1) | Weight | ≈ Points |",
        "|---|---|---|---|---|",
    ]
    for row in exp["section_contributions"]:
        lines.append(
            f"| **{row['label']}** | {row['meaning']} | {row['avg_0_1']} | "
            f"{int(row['weight'] * 100)}% | ~{row['points_of_1000']} |"
        )
    lines += [
        "",
        f"- Weighted blend = **{recon['total_weighted']}** of a possible 1.0.",
        f"- Evidence multiplier = **×{recon['coverage_multiplier']}** "
        f"(coverage ≈ {recon['coverage']}; more & broader evidence → closer to ×0.94).",
        *( [f"- Semantic-review bonus = **+{recon['semantic_bonus']}** "
            "(an LLM adjudicated the evidence, which nudges the score up slightly)."]
           if recon["semantic_bonus"] else
           ["- No semantic-review bonus applied (deterministic scoring only)."] ),
        f"- Final: round({recon['total_weighted']} × {recon['coverage_multiplier']}"
        f"{' + ' + str(recon['semantic_bonus']) if recon['semantic_bonus'] else ''}) × 1000 "
        f"= **{recon['reconstructed_overall']}**.",
        "",
        "## What pushed your score UP",
        "",
    ]
    for s in exp["strengths"]:
        lines.append(f"- **{s['plain']}** — scored {s['score']}/1.0.")
    lines += ["", "## What held your score DOWN", ""]
    for w in exp["weaknesses"]:
        lines.append(f"- **{w['plain']}** — scored {w['score']}/1.0.")

    dc = exp["dimension_confidence"]
    lines += [
        "",
        "## How much to trust each part",
        "",
    ]
    if exp.get("dimensions_present"):
        lines += [
            f"- **High-confidence dimensions:** {', '.join(a.replace('_', ' ') for a in dc['high']) or 'none'}",
            f"- **Medium-confidence:** {', '.join(a.replace('_', ' ') for a in dc['medium']) or 'none'}",
            f"- **Low-confidence (thin evidence):** {', '.join(a.replace('_', ' ') for a in dc['low']) or 'none'}",
        ]
    else:
        lines += [
            "- This profile didn't store per-dimension confidence breakdowns "
            "(older AI Wizard run). Rely on the overall confidence and caveats below.",
        ]
    lines += [
        "",
        f"Semantic review: **{exp['semantic_status'].get('status', 'n/a')}** "
        f"(provider: {exp['semantic_status'].get('provider', 'n/a')}).",
    ]

    if exp["caveats"]:
        lines += ["", "## Honest caveats about this score", ""]
        lines += [f"- {c}" for c in exp["caveats"]]

    if exp["risks"]:
        lines += ["", "## Risks flagged", ""]
        lines += [f"- {r}" for r in exp["risks"]]

    if exp["next_build_plan"]:
        lines += ["", "## How to raise your score (do these next)", ""]
        lines += [f"{i}. {step}" for i, step in enumerate(exp["next_build_plan"], 1)]

    lines += [
        "",
        "---",
        "",
        "_The score compresses the profile; it does not replace it. It reflects "
        "the AI work that was actually observed — it is a floor on what you can "
        "do, not a ceiling._",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def command_explain(args: argparse.Namespace) -> None:
    path = resolve_profile_path(args)
    profile = load_profile(path)
    exp = build_explanation(profile)

    if args.format == "json":
        output = json.dumps(exp, indent=2)
    else:
        output = render_markdown(exp)

    if not exp["reconstruction"].get("verified") and exp["headline"]["score"] is not None:
        print(
            f"WARNING: score reconstruction off by "
            f"{exp['reconstruction'].get('overall_delta')} points — "
            "ai-wizard's formula may have changed; see references/score-formula.md.",
            file=sys.stderr,
        )

    if args.out:
        out_path = Path(args.out)
        if args.dry_run:
            print(f"[dry-run] would write {len(output)} chars to {out_path}", file=sys.stderr)
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output)
            print(f"wrote {out_path}", file=sys.stderr)

    print(output)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Explain an AI Wizard dossier (profile.json) in plain language.")
    sub = p.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("explain", help="Explain a profile's score.")
    src = ex.add_argument_group("dossier source (choose one)")
    src.add_argument("--profile", help="Path to a profile.json (or a run directory containing one).")
    src.add_argument("--run", help="Run id under Databases/ai-wizard/runs/.")
    src.add_argument("--latest", action="store_true", help="Use the most recent run.")
    ex.add_argument("--format", choices=["markdown", "json"], default="markdown")
    ex.add_argument("--out", help="Also write the rendered output to this path.")
    ex.add_argument("--dry-run", action="store_true", help="With --out, show what would be written without writing.")
    ex.set_defaults(func=command_explain)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
