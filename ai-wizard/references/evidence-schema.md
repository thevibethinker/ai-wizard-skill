---
created: 2026-05-25
last_edited: 2026-05-25
version: 0.1
provenance: con_hnCNKu4MfUQuWaDn
---

# Evidence Schema

AI Wizard normalizes heterogeneous traces into simple evidence records.

```json
{
  "id": "event-0001",
  "source": "zo|codex|claude_code|chatgpt|workspace",
  "kind": "conversation|artifact|command|file|build|skill",
  "path": "optional local path or reference",
  "timestamp": "optional ISO timestamp",
  "text": "short redacted text or metadata summary",
  "signals": ["decomposition", "verification"],
  "confidence": 0.7
}
```

Public reports should use summaries and IDs. Private reports may include short excerpts only when explicitly requested.

## Run Inventory

Each profile run writes `inventory.json` next to `profile.json`. The inventory is a compact accounting layer, not a raw evidence dump:

```json
{
  "total_evidence_items_scanned": 12,
  "included_source_types": ["conversation_trace", "workspace_artifact"],
  "skipped_or_unavailable_source_types": ["direct AI conversation/operator-message traces"],
  "top_roots": [{"name": "N5", "count": 9}],
  "skew_warnings": ["Artifact-heavy evidence; operator-message behavior may be underrepresented."]
}
```

`profile.json` also includes `dimension_coverage` for every scored dimension:

```json
{
  "pipeline_thinking": {
    "evidence_count": 3,
    "representative_sources": [
      {"id": "baseline-0000", "source": "baseline", "kind": "operator_message", "path": "sample.json#message-0"}
    ],
    "confidence": "medium",
    "missing_evidence_notes": []
  }
}
```

Public dossier and share outputs may include inventory counts, roots, source classes, and warnings. They must not include raw private evidence unless `--include-excerpts` is explicitly used for private output.

## Semantic Review Checkpoint

When semantic-Zo is requested, reviews are saved as newline-delimited JSON in `semantic-reviews.jsonl` inside the run directory. Each line is a normalized review:

```json
{
  "evidence_id": "baseline-0000",
  "quality": "strong",
  "axis_scores": {"pipeline_thinking": 0.8},
  "supported_claims": ["Compact claim from reviewed evidence."],
  "risk_flags": [],
  "level_up_hint": "Add an explicit verification gate."
}
```

`--semantic-resume` loads this checkpoint, skips already reviewed evidence IDs, and appends only newly completed reviews. `--semantic-reviews <path>` replays a saved review file without making a new provider call.

## Dogfood Report

Dogfood mode writes `dogfood-report.json` and `dogfood-report.md`. The JSON includes runtime summary, evidence inventory summary, semantic status, retry/timeout/fallback events, scoring volatility, and suggested verification commands. It is deliberately metadata-only and sets `raw_private_evidence_included` to `false`.
