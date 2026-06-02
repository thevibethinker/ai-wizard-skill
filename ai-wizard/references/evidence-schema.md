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

Each profile run writes `inventory.json` next to `profile.json`.

```json
{
  "used": {
    "total_evidence_items_scanned": 42,
    "included_source_types": ["baseline"],
    "included_evidence_kinds": ["operator_message"],
    "source_counts": {"baseline": 42},
    "kind_counts": {"operator_message": 42},
    "root_counts": {"baseline-export": 42},
    "top_roots": [{"root": "baseline-export", "count": 42}],
    "signal_counts": {"pipeline_thinking": 7},
    "top_paths": ["optional local path or reference"]
  },
  "skipped_or_unavailable_source_types": ["codex", "claude_code"],
  "skew_warnings": ["Score is based on artifact-heavy evidence."],
  "suggested_next_evidence": ["direct AI conversation/operator-message traces"]
}
```

`profile.json` also includes `coverage.dimensions`, keyed by section and dimension:

```json
{
  "coverage": {
    "dimensions": {
      "vibe_pill_primitives": {
        "pipeline_thinking": {
          "evidence_count": 3,
          "representative_sources": [
            {"id": "baseline-0000", "source": "baseline", "kind": "operator_message", "path": "path#message-0"}
          ],
          "confidence": "medium",
          "missing_evidence_notes": []
        }
      }
    }
  }
}
```

Confidence values are `low`, `medium`, or `high`. Public dossier/share output may include compact counts, warnings, and representative IDs/paths, but must not dump raw private evidence text unless explicitly requested.
