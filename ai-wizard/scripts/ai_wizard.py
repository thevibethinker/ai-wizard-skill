#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from time import perf_counter

DEFAULT_WORKSPACE = Path(os.environ.get("AI_WIZARD_WORKSPACE", "/home/workspace")).resolve()
ZO_ASK_URL = "https://api.zo.computer/zo/ask"
ZO_MODEL = os.environ.get("AI_WIZARD_ZO_MODEL", "byok:8a1176d8-10bf-44e8-a25c-30329932843c")
QUALITY_MULTIPLIERS = {
    "noise": 0.0,
    "weak": 0.5,
    "moderate": 1.0,
    "strong": 1.35,
    "exemplary": 1.7,
}

DIAGNOSTIC_AXES = {
    "mental_model_accuracy": ["verify", "source", "ground truth", "schema", "architecture", "canonical"],
    "decomposition_instinct": ["plan", "phase", "drop", "scenario", "step", "wave", "breakdown"],
    "failure_recognition": ["validate", "test", "audit", "guardrail", "hallucination", "false positive"],
    "tool_agnostic_thinking": ["adapter", "portable", "baseline", "cross-compatible", "export", "claude", "codex", "chatgpt"],
    "delegation_judgment": ["approval", "confirm", "human", "gate", "draft", "review", "external"],
    "iteration_refinement": ["retry", "debug", "calibrate", "refine", "aar", "fix", "regression"],
}

CORE_PRIMITIVES = {
    "system_composition": ["wire", "connect", "route", "compose", "orchestrat", "multi-channel"],
    "pipeline_thinking": ["source", "transform", "store", "deliver", "dedupe", "schema", "pipeline"],
    "tool_thinking": ["cli", "dashboard", "form", "route", "interface", "button", "tool"],
    "integration_thinking": ["api", "oauth", "webhook", "sync", "export", "import", "calendar", "gmail"],
    "orchestration_trust_boundaries": ["approval", "gate", "human-in-the-loop", "dry-run", "confirm", "permission"],
    "feedback_loops": ["log", "history", "eval", "metric", "learn", "improve", "feedback"],
}

META_PRIMITIVES = {
    "context_engineering": ["context", "persona", "rule", "retrieval", "source", "constraint"],
    "state_awareness": ["state", "status", "checkpoint", "idempotent", "watermark", "progress"],
    "error_recovery": ["error", "hypothesis", "traceback", "debug", "circular", "root cause"],
}


@dataclass
class Evidence:
    id: str
    source: str
    kind: str
    path: str
    timestamp: str | None
    text: str
    signals: list[str]
    confidence: float


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_read(path: Path, max_chars: int = 12000) -> str:
    try:
        return path.read_text(errors="ignore")[:max_chars]
    except Exception:
        return ""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(DEFAULT_WORKSPACE))
    except ValueError:
        return str(path)


def build_artifact_root() -> Path:
    return DEFAULT_WORKSPACE / "Databases/ai-wizard/runs"


def history_db() -> Path:
    return DEFAULT_WORKSPACE / "Databases/ai-wizard/ai_wizard_history.sqlite"


def is_self_artifact(path: Path) -> bool:
    parts = path.parts
    rel_path = rel(path)
    if "__pycache__" in parts or "node_modules" in parts:
        return True
    blocked_prefixes = (
        "Skills/ai-wizard/",
        "N5/builds/ai-wizard-rebuild-20260525/",
    )
    return rel_path.startswith(blocked_prefixes)


def score_keywords(text: str, keywords: list[str]) -> int:
    lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lower)


def collect_workspace_artifacts(limit: int = 250) -> list[Evidence]:
    candidates: list[Path] = []
    for base in [DEFAULT_WORKSPACE / "N5/builds", DEFAULT_WORKSPACE / "Skills", DEFAULT_WORKSPACE / "Prompts"]:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if len(candidates) >= limit:
                break
            if path.is_file() and path.suffix.lower() in {".md", ".py", ".json", ".yaml", ".yml", ".tsx", ".ts"}:
                if not is_self_artifact(path):
                    candidates.append(path)
    evidence: list[Evidence] = []
    for idx, path in enumerate(candidates):
        text = safe_read(path, 6000)
        signals = detect_signals(text + "\n" + rel(path))
        evidence.append(Evidence(
            id=f"workspace-{idx:04d}",
            source="workspace",
            kind="artifact",
            path=rel(path),
            timestamp=None,
            text=summarize_text(text, rel(path)),
            signals=signals,
            confidence=0.65 if signals else 0.35,
        ))
    return evidence


def collect_export_artifacts(input_path: Path, source: str = "baseline", limit: int = 500, max_scan_files: int | None = None) -> list[Evidence]:
    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {input_path}")
    files: list[Path] = []
    scan_limit = max_scan_files or max(limit * 4, 250)
    if input_path.is_file():
        files = [input_path]
    else:
        candidates: list[tuple[float, str, Path]] = []
        for path in input_path.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".md", ".txt", ".html"}:
                continue
            try:
                candidates.append((path.stat().st_mtime, str(path), path))
            except OSError:
                continue
        candidates.sort(reverse=True)
        files = [path for _, _, path in candidates[:scan_limit]]
    evidence: list[Evidence] = []
    for idx, path in enumerate(files):
        if len(evidence) >= limit:
            break
        read_limit = 1_000_000 if path.suffix.lower() == ".jsonl" else 10000
        text = safe_read(path, read_limit)
        if path.suffix.lower() == ".jsonl":
            structured = structured_jsonl_evidence(text, source, path, start_idx=len(evidence), limit=limit - len(evidence))
            if structured:
                evidence.extend(structured)
                if len(evidence) >= limit:
                    break
            continue
        if path.suffix.lower() == ".json":
            structured = structured_json_evidence(text, source, path, start_idx=len(evidence), limit=limit - len(evidence))
            if structured:
                evidence.extend(structured)
                if len(evidence) >= limit:
                    break
                continue
            if is_known_conversation_json(text):
                continue
            text = flatten_json_text(text)
        signals = detect_signals(text)
        evidence.append(Evidence(
            id=f"{source}-{idx:04d}",
            source=source,
            kind="conversation",
            path=str(path),
            timestamp=None,
            text=summarize_text(text, path.name),
            signals=signals,
            confidence=0.55 if signals else 0.25,
        ))
        if len(evidence) >= limit:
            break
    return evidence


def is_known_conversation_json(text: str) -> bool:
    try:
        data = json.loads(text)
    except Exception:
        return False
    return isinstance(data, dict) and (isinstance(data.get("conversations"), list) or isinstance(data.get("mapping"), dict))


def extract_content_text(content: Any) -> str:
    chunks: list[str] = []
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "message", "content"):
            value = content.get(key)
            if isinstance(value, str):
                chunks.append(value)
            elif isinstance(value, (dict, list)):
                nested = extract_content_text(value)
                if nested:
                    chunks.append(nested)
    elif isinstance(content, list):
        for item in content:
            nested = extract_content_text(item)
            if nested:
                chunks.append(nested)
    return "\n".join(chunks)


def structured_jsonl_evidence(text: str, source: str, path: Path, start_idx: int = 0, limit: int = 500) -> list[Evidence]:
    chunks: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        if len(chunks) >= limit:
            break
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        event_type = data.get("type")
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        timestamp = data.get("timestamp") if isinstance(data.get("timestamp"), str) else None
        if event_type == "session_meta" or event_type == "turn_context":
            continue
        if event_type == "event_msg" and payload.get("type") == "user_message":
            message = payload.get("message")
            if isinstance(message, str):
                user_text = extract_real_user_message(message)
                if user_text:
                    chunks.append((user_text, timestamp))
            continue
        if event_type == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
            message = extract_content_text(payload.get("content"))
            user_text = extract_real_user_message(message)
            if user_text:
                chunks.append((user_text, timestamp))
    evidence: list[Evidence] = []
    for offset, (chunk, timestamp) in enumerate(chunks[:limit]):
        signals = detect_signals(chunk)
        evidence.append(Evidence(
            id=f"{source}-{start_idx + offset:04d}",
            source=source,
            kind="operator_message",
            path=f"{path}#message-{offset}",
            timestamp=timestamp,
            text=summarize_text(chunk, path.name),
            signals=signals,
            confidence=0.62 if signals else 0.28,
        ))
    return evidence


def extract_real_user_message(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    query_matches = re.findall(r"USER QUERY:\s*(.*?)(?:\s+MENTIONED FILES:|\n\s*<system-reminder>|$)", stripped, re.DOTALL)
    if query_matches:
        stripped = query_matches[-1].strip()
    if "</system_prompt>" in stripped:
        stripped = stripped.rsplit("</system_prompt>", 1)[-1].strip()
    if "MENTIONED FILES:" in stripped:
        stripped = stripped.split("MENTIONED FILES:", 1)[0].strip()
    stripped = re.sub(r"<system-reminder>.*?</system-reminder>", " ", stripped, flags=re.DOTALL)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    lower = stripped[:2000].lower()
    injected_prefixes = (
        "you are operating on a system called zo.",
        "you are running on the user's zo computer",
        "# agents.md instructions",
        "<environment_context>",
        "<system_prompt>",
        "knowledge cutoff:",
        "you are codex,",
        "you are an ai assistant",
    )
    if any(lower.startswith(prefix) for prefix in injected_prefixes):
        return ""
    if "workspace operating contract" in lower[:1000] and "# agents.md instructions" in lower[:200]:
        return ""
    return stripped


def structured_json_evidence(text: str, source: str, path: Path, start_idx: int = 0, limit: int = 500) -> list[Evidence]:
    try:
        data = json.loads(text)
    except Exception:
        return []
    chunks: list[tuple[str, str | None]] = []
    if isinstance(data, dict) and isinstance(data.get("conversations"), list):
        for conv in data["conversations"]:
            if not isinstance(conv, dict):
                continue
            title = str(conv.get("title") or path.name)
            messages = conv.get("messages") or []
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, str):
                        chunks.append((f"{title}: {msg}", None))
                    elif isinstance(msg, dict):
                        role = str(msg.get("role") or msg.get("author") or "user").lower()
                        if role == "user":
                            chunks.append((f"{title}: {flatten_json_text(json.dumps(msg))}", None))
    elif isinstance(data, dict) and isinstance(data.get("mapping"), dict):
        for node in data["mapping"].values():
            if not isinstance(node, dict):
                continue
            message = node.get("message")
            if not isinstance(message, dict):
                continue
            role = ((message.get("author") or {}).get("role") or "unknown")
            if role != "user":
                continue
            content = message.get("content") or {}
            parts = content.get("parts") if isinstance(content, dict) else None
            create_time = message.get("create_time")
            timestamp = None
            if isinstance(create_time, (int, float)):
                timestamp = datetime.fromtimestamp(create_time, timezone.utc).isoformat()
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, str) and part.strip():
                        chunks.append((f"{role}: {part}", timestamp))
    evidence: list[Evidence] = []
    for offset, (chunk, timestamp) in enumerate(chunks[:limit]):
        signals = detect_signals(chunk)
        evidence.append(Evidence(
            id=f"{source}-{start_idx + offset:04d}",
            source=source,
            kind="operator_message",
            path=f"{path}#message-{offset}",
            timestamp=timestamp,
            text=summarize_text(chunk, path.name),
            signals=signals,
            confidence=0.58 if signals else 0.25,
        ))
    return evidence


def flatten_json_text(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception:
        return text
    chunks: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj[:200]:
                walk(value)
        elif isinstance(obj, str):
            chunks.append(obj)

    walk(data)
    return "\n".join(chunks)[:20000]


def summarize_text(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return fallback
    return cleaned[:360]


def detect_signals(text: str) -> list[str]:
    found: list[str] = []
    for group in [DIAGNOSTIC_AXES, CORE_PRIMITIVES, META_PRIMITIVES]:
        for axis, keywords in group.items():
            if score_keywords(text, keywords):
                found.append(axis)
    return sorted(set(found))


def source_inventory(mode: str, input_path: Path | None) -> dict[str, Any]:
    sources = []
    sources.append({
        "source": "zo_workspace",
        "available": DEFAULT_WORKSPACE.exists(),
        "path": str(DEFAULT_WORKSPACE),
        "notes": "Used in zo-native mode for build, skill, prompt, and artifact evidence.",
    })
    for name, path in [
        ("codex", Path.home() / ".codex"),
        ("claude_code", Path.home() / ".claude"),
    ]:
        sources.append({
            "source": name,
            "available": bool(path and path.exists()),
            "path": str(path) if path else None,
            "notes": "Optional baseline/export source.",
        })
    sources.append({
        "source": "chatgpt_export",
        "available": bool(input_path and input_path.exists()),
        "path": str(input_path) if input_path else None,
        "notes": "Optional baseline/export source; pass --input pointing to an export directory or archive.",
    })
    return {"mode": mode, "generated_at": now_iso(), "sources": sources}


def build_inventory(mode: str, input_path: Path | None, evidence: list[Evidence], semantic_payload: dict[str, Any]) -> dict[str, Any]:
    base = source_inventory(mode, input_path)
    source_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    root_counts: dict[str, int] = {}
    top_paths: list[str] = []
    for item in evidence:
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
        kind_counts[item.kind] = kind_counts.get(item.kind, 0) + 1
        root = evidence_root(item.path)
        root_counts[root] = root_counts.get(root, 0) + 1
        for signal in item.signals:
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
        if len(top_paths) < 12:
            top_paths.append(item.path)
    warnings: list[str] = []
    if not evidence:
        warnings.append("No usable evidence records were collected.")
    if len(evidence) < 8:
        warnings.append("Low evidence count; score should be treated as a weak signal.")
    if source_counts and set(source_counts) == {"workspace"}:
        warnings.append("Workspace-only evidence; direct conversation/export traces may change the profile.")
    if kind_counts.get("artifact", 0) > max(4, kind_counts.get("operator_message", 0) * 4):
        warnings.append("Artifact-heavy evidence; operator-message behavior may be underrepresented.")
    if root_counts:
        dominant_root, dominant_count = max(root_counts.items(), key=lambda item: item[1])
        if dominant_count / max(1, len(evidence)) >= 0.65 and len(evidence) >= 3:
            warnings.append(f"Source coverage is skewed toward `{dominant_root}`; score may undercount broader live AI usage.")
    if semantic_payload.get("requested") and semantic_payload.get("status") not in {"completed", "disabled"}:
        warnings.append("Semantic adjudication did not fully complete; deterministic evidence scoring remains material.")
    missing: list[str] = []
    if "operator_message" not in kind_counts:
        missing.append("direct AI conversation/operator-message traces")
    if "baseline" not in source_counts and mode == "zo-native":
        missing.append("portable baseline exports from Claude/Codex/ChatGPT-style histories")
    return base | {
        "used": {
            "evidence_records": len(evidence),
            "total_evidence_items_scanned": len(evidence),
            "included_source_types": sorted(source_counts),
            "included_evidence_kinds": sorted(kind_counts),
            "source_counts": source_counts,
            "kind_counts": kind_counts,
            "root_counts": dict(sorted(root_counts.items(), key=lambda item: item[1], reverse=True)),
            "top_roots": [
                {"root": root, "count": count}
                for root, count in sorted(root_counts.items(), key=lambda item: item[1], reverse=True)[:8]
            ],
            "signal_counts": dict(sorted(signal_counts.items(), key=lambda item: item[1], reverse=True)),
            "top_paths": top_paths,
        },
        "skipped_or_unavailable_source_types": [
            source["source"]
            for source in base["sources"]
            if not source.get("available") or (mode == "baseline" and source["source"] == "zo_workspace")
        ],
        "skew_warnings": warnings,
        "suggested_next_evidence": missing,
    }


def evidence_root(path: str) -> str:
    cleaned = path.split("#", 1)[0]
    try:
        p = Path(cleaned)
    except Exception:
        return cleaned or "unknown"
    if p.is_absolute():
        try:
            return str(p.relative_to(DEFAULT_WORKSPACE)).split("/", 2)[0] or str(p)
        except ValueError:
            parts = p.parts
            return "/".join(parts[:4]) if len(parts) >= 4 else str(p)
    parts = cleaned.split("/")
    if len(parts) >= 3 and parts[0] in {"N5", "Skills", "Prompts", "Documents", "Projects", "Personal"}:
        return "/".join(parts[:3 if parts[0] == "N5" and parts[1] == "builds" else 2])
    return parts[0] if parts and parts[0] else "unknown"


def semantic_status(requested: bool, provider: str = "auto") -> dict[str, Any]:
    if not requested:
        return {
            "requested": False,
            "provider": "none",
            "status": "disabled",
            "note": "Semantic pass disabled by --no-semantic; scores are deterministic keyword heuristics.",
        }
    if provider == "zo":
        return {
            "requested": True,
            "provider": "zo_ask",
            "status": "ready",
            "note": "Zo semantic provider requested. This build validates token availability but still uses deterministic axis aggregation until semantic adjudication is implemented.",
        }
    return {
        "requested": True,
        "provider": "heuristic_fallback",
        "status": "fallback",
        "note": "Semantic provider is heuristic fallback; this is not an LLM-backed adjudication pass.",
    }


def validate_semantic_provider(args: argparse.Namespace) -> tuple[bool, dict[str, Any], str, str]:
    requested = not args.no_semantic
    provider = getattr(args, "semantic_provider", "auto")
    if not requested:
        return False, semantic_status(False, provider), "deterministic_keyword_heuristic_v0", "Semantic scoring disabled; deterministic keyword heuristics only."
    if provider == "zo":
        token = os.environ.get("ZO_CLIENT_IDENTITY_TOKEN")
        if not token:
            raise SystemExit("--semantic-provider zo requires ZO_CLIENT_IDENTITY_TOKEN")
        status = semantic_status(True, "zo")
        return True, status, "zo_semantic_adjudication_v0", "Zo-backed semantic adjudication reviewed sampled evidence and adjusted axis confidence. Treat scores as directional until broader calibration lands."
    status = semantic_status(True, "heuristic")
    return True, status, "semantic_proxy_heuristic_v0", "Semantic scoring is currently a deterministic proxy, not an LLM-backed adjudication pass. Treat the score as directional until semantic calibration is upgraded."


def quality_multiplier(quality: str) -> float:
    return QUALITY_MULTIPLIERS.get(str(quality).lower(), 1.0)


def all_axis_names() -> set[str]:
    names: set[str] = set()
    for group in [DIAGNOSTIC_AXES, CORE_PRIMITIVES, META_PRIMITIVES]:
        names.update(group.keys())
    return names


def redact_for_semantic(text: str, limit: int = 1200) -> str:
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"sk-[A-Za-z0-9_\-]{12,}", "[REDACTED_KEY]", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", text)
    return text[:limit]


def evidence_packets(evidence: list[Evidence], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(evidence, key=lambda e: (len(e.signals), e.confidence, e.id), reverse=True)
    packets: list[dict[str, Any]] = []
    for item in ranked[:limit]:
        packets.append({
            "evidence_id": item.id,
            "source": item.source,
            "kind": item.kind,
            "path_or_ref": item.path,
            "observed_text": redact_for_semantic(item.text),
            "deterministic_signals": item.signals,
            "candidate_axes": item.signals,
            "privacy_level": "private",
            "confidence_prior": item.confidence,
        })
    return packets


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        value = json.loads(match.group(0))
        if isinstance(value, dict):
            return value
    raise ValueError("semantic response was not a JSON object")


def call_zo_ask(prompt: str) -> str:
    mock = os.environ.get("AI_WIZARD_ZO_ASK_MOCK_RESPONSE")
    if mock is not None:
        return mock
    token = os.environ.get("ZO_CLIENT_IDENTITY_TOKEN")
    if not token:
        raise RuntimeError("missing ZO_CLIENT_IDENTITY_TOKEN")
    body = json.dumps({"input": prompt, "model_name": ZO_MODEL}).encode("utf-8")
    req = urllib.request.Request(
        ZO_ASK_URL,
        data=body,
        headers={
            "authorization": token,
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read())
    output = payload.get("output")
    if isinstance(output, dict):
        return json.dumps(output)
    if isinstance(output, str):
        return output
    raise RuntimeError("Zo ask response missing output")


def semantic_prompt(packets: list[dict[str, Any]]) -> str:
    return (
        "You are the Zo-backed semantic adjudicator for AI Wizard, an observed AI fluency profile.\n"
        "Review compact evidence packets. Do not infer private facts beyond the packet. "
        "Return strict JSON only, no markdown.\n\n"
        "Allowed axes: "
        + ", ".join(sorted(all_axis_names()))
        + "\nAllowed quality values: noise, weak, moderate, strong, exemplary.\n"
        "Score only axes that are actually demonstrated by the packet. Values are 0.0 to 1.0.\n"
        "Output shape: {\"evidence_reviews\":[{\"evidence_id\":\"...\",\"quality\":\"moderate\","
        "\"axis_scores\":{\"pipeline_thinking\":0.8},\"supported_claims\":[\"...\"],"
        "\"risk_flags\":[\"...\"],\"level_up_hint\":\"...\"}],\"batch_quality_notes\":\"...\"}\n\n"
        "Evidence packets:\n"
        + json.dumps(packets, indent=2)
    )


def normalize_review(raw: dict[str, Any], known_ids: set[str]) -> dict[str, Any] | None:
    evidence_id = raw.get("evidence_id")
    if evidence_id not in known_ids:
        return None
    quality = str(raw.get("quality", "moderate")).lower()
    if quality not in QUALITY_MULTIPLIERS:
        quality = "moderate"
    axis_scores: dict[str, float] = {}
    for axis, value in (raw.get("axis_scores") or {}).items():
        if axis not in all_axis_names():
            continue
        try:
            axis_scores[axis] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue
    return {
        "evidence_id": evidence_id,
        "quality": quality,
        "axis_scores": axis_scores,
        "supported_claims": [str(x)[:240] for x in (raw.get("supported_claims") or [])[:4]],
        "risk_flags": [str(x)[:240] for x in (raw.get("risk_flags") or [])[:4]],
        "level_up_hint": str(raw.get("level_up_hint") or "")[:300],
    }


def run_zo_semantic_reviews(evidence: list[Evidence], cap: int, batch_size: int = 8) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return run_zo_semantic_reviews_resumable(evidence, cap, batch_size=batch_size)


def load_checkpoint_reviews(path: Path, evidence: list[Evidence]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    known_ids = {item.id for item in evidence}
    reviews: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in path.read_text(errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        review = normalize_review(raw, known_ids)
        if review and review["evidence_id"] not in seen:
            reviews.append(review)
            seen.add(review["evidence_id"])
    return reviews


def append_checkpoint_reviews(path: Path, reviews: list[dict[str, Any]]) -> None:
    if not reviews:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        for review in reviews:
            handle.write(json.dumps(review, sort_keys=True) + "\n")


def run_zo_semantic_reviews_resumable(
    evidence: list[Evidence],
    cap: int,
    batch_size: int = 8,
    checkpoint_path: Path | None = None,
    resume: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packets = evidence_packets(evidence, cap)
    reviews: list[dict[str, Any]] = load_checkpoint_reviews(checkpoint_path, evidence) if checkpoint_path and resume else []
    reviewed_ids = {review["evidence_id"] for review in reviews}
    failures: list[str] = []
    missing_packets = [packet for packet in packets if packet["evidence_id"] not in reviewed_ids]
    for idx in range(0, len(missing_packets), batch_size):
        batch = missing_packets[idx:idx + batch_size]
        try:
            payload = parse_json_object(call_zo_ask(semantic_prompt(batch)))
            known_ids = {p["evidence_id"] for p in batch}
            raw_reviews = payload.get("evidence_reviews") or []
            if not isinstance(raw_reviews, list):
                raise ValueError("evidence_reviews was not a list")
            batch_reviews: list[dict[str, Any]] = []
            for raw in raw_reviews:
                if isinstance(raw, dict):
                    review = normalize_review(raw, known_ids)
                    if review and review["evidence_id"] not in reviewed_ids:
                        batch_reviews.append(review)
                        reviewed_ids.add(review["evidence_id"])
            reviews.extend(batch_reviews)
            if checkpoint_path:
                append_checkpoint_reviews(checkpoint_path, batch_reviews)
        except Exception as exc:
            failures.append(f"batch {idx // batch_size + 1}: {type(exc).__name__}: {exc}")
    status = "completed" if packets and not failures and len(reviews) == len(packets) else "partial" if reviews else "failed"
    return reviews, {
        "provider": "zo_ask",
        "status": status,
        "items_sampled": len(packets),
        "items_reviewed": len(reviews),
        "items_reused": len([review for review in reviews if review["evidence_id"] not in {packet["evidence_id"] for packet in missing_packets}]),
        "failures": failures[:5],
        "raw_private_excerpt_included": False,
        "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
    }


def load_semantic_reviews(path: Path, evidence: list[Evidence]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Semantic review file does not exist: {path}")
    known_ids = {item.id for item in evidence}
    reviews: list[dict[str, Any]] = []
    rejected = 0
    for line in path.read_text(errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            rejected += 1
            continue
        if not isinstance(raw, dict):
            rejected += 1
            continue
        review = normalize_review(raw, known_ids)
        if review:
            reviews.append(review)
        else:
            rejected += 1
    return reviews, {
        "provider": "semantic_review_replay",
        "status": "completed" if reviews and not rejected else "partial" if reviews else "failed",
        "items_sampled": len(known_ids),
        "items_reviewed": len(reviews),
        "failures": [f"rejected_reviews={rejected}"] if rejected else [],
        "raw_private_excerpt_included": False,
        "replay_path": str(path),
    }


def analyze_axes(evidence: list[Evidence], semantic: bool, reviews: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    text = "\n".join(e.text + " " + " ".join(e.signals) for e in evidence)
    reviews_by_axis: dict[str, list[tuple[str, float, str]]] = {}
    for review in reviews or []:
        multiplier = quality_multiplier(review.get("quality", "moderate"))
        for axis, axis_score in (review.get("axis_scores") or {}).items():
            reviews_by_axis.setdefault(axis, []).append((review["evidence_id"], float(axis_score), review.get("quality", "moderate")))
    sections = {
        "diagnostic_instincts": DIAGNOSTIC_AXES,
        "vibe_pill_primitives": CORE_PRIMITIVES,
        "meta_primitives": META_PRIMITIVES,
    }
    result: dict[str, Any] = {}
    for section, axes in sections.items():
        result[section] = {}
        for axis, keywords in axes.items():
            keyword_hits = score_keywords(text, keywords)
            evidence_hits = [e.id for e in evidence if axis in e.signals][:8]
            raw = min(1.0, (keyword_hits / max(4, len(keywords))) + (len(evidence_hits) * 0.04))
            semantic_hits = reviews_by_axis.get(axis, [])
            if semantic_hits:
                reviewed_score = sum(score * quality_multiplier(quality) for _, score, quality in semantic_hits) / len(semantic_hits)
                reviewed_score = min(1.0, reviewed_score)
                raw = max(raw * 0.55 + reviewed_score * 0.45, reviewed_score * 0.72)
                evidence_hits = list(dict.fromkeys(evidence_hits + [eid for eid, _, _ in semantic_hits]))[:8]
            if not semantic:
                raw *= 0.82
            result[section][axis] = {
                "score": round(raw, 3),
                "evidence_ids": evidence_hits,
                "confidence": round(min(0.92, 0.35 + len(evidence_hits) * 0.07 + (0.1 if semantic else 0) + (0.12 if semantic_hits else 0)), 3),
            }
    return result


def dimension_coverage(evidence: list[Evidence], axes: dict[str, Any]) -> dict[str, Any]:
    by_id = {item.id: item for item in evidence}
    coverage: dict[str, Any] = {}
    for section, section_axes in axes.items():
        coverage[section] = {}
        for axis, payload in section_axes.items():
            ids = list(payload.get("evidence_ids") or [])
            representative: list[dict[str, str]] = []
            seen_sources: set[str] = set()
            for evidence_id in ids:
                item = by_id.get(evidence_id)
                if not item:
                    continue
                representative.append({
                    "id": item.id,
                    "source": item.source,
                    "kind": item.kind,
                    "path": item.path,
                })
                seen_sources.add(item.source)
                if len(representative) >= 3:
                    break
            count = len(ids)
            score_confidence = float(payload.get("confidence", 0))
            if count >= 6 and len(seen_sources) >= 2 and score_confidence >= 0.65:
                confidence = "high"
            elif count >= 2 and score_confidence >= 0.45:
                confidence = "medium"
            else:
                confidence = "low"
            missing_notes: list[str] = []
            if count == 0:
                missing_notes.append("No direct evidence matched this dimension.")
            elif count < 2:
                missing_notes.append("Only one matching evidence item; treat dimension score as tentative.")
            if len(seen_sources) <= 1 and len(evidence) > count:
                missing_notes.append("Representative evidence comes from a narrow source set.")
            coverage[section][axis] = {
                "evidence_count": count,
                "representative_sources": representative,
                "confidence": confidence,
                "missing_evidence_notes": missing_notes,
            }
    return coverage


def low_or_skewed_coverage(inventory: dict[str, Any], dimension_payload: dict[str, Any]) -> bool:
    if inventory.get("skew_warnings"):
        return True
    low = 0
    total = 0
    for section in dimension_payload.values():
        for payload in section.values():
            total += 1
            if payload.get("confidence") == "low":
                low += 1
    return total > 0 and low / total >= 0.35


def score_interpretation(profile_status: str, inventory: dict[str, Any], dimension_payload: dict[str, Any]) -> dict[str, Any]:
    warnings = []
    if profile_status == "insufficient_evidence":
        warnings.append("Score is low-confidence because usable evidence was sparse or unavailable.")
    if low_or_skewed_coverage(inventory, dimension_payload):
        warnings.append("Score is an observed-artifact score, not a personal ceiling.")
    warnings.extend(inventory.get("skew_warnings") or [])
    return {
        "primary_warning": warnings[0] if warnings else "",
        "warnings": list(dict.fromkeys(warnings)),
    }


def maturity_stage(axis_scores: dict[str, Any]) -> dict[str, Any]:
    primitive_scores = axis_scores["vibe_pill_primitives"]
    meta_scores = axis_scores["meta_primitives"]
    avg_core = sum(v["score"] for v in primitive_scores.values()) / len(primitive_scores)
    avg_meta = sum(v["score"] for v in meta_scores.values()) / len(meta_scores)
    combined = (avg_core * 0.62) + (avg_meta * 0.38)
    if combined >= 0.86:
        level, label = 6, "Technically Dangerous"
    elif combined >= 0.72:
        level, label = 5, "Compounding Builder"
    elif combined >= 0.58:
        level, label = 4, "Systems Operator"
    elif combined >= 0.44:
        level, label = 3, "Tool Builder"
    elif combined >= 0.30:
        level, label = 2, "Workflow Designer"
    elif combined >= 0.16:
        level, label = 1, "Prompt Practitioner"
    else:
        level, label = 0, "AI Consumer"
    return {"level": level, "label": label, "confidence": round(min(0.9, 0.45 + combined * 0.45), 3)}


def archetype(score: int) -> dict[str, Any]:
    if score < 375:
        return {"name": "White Rabbit", "optional_marketing_layer": True}
    if score < 600:
        return {"name": "Kung Fu Master", "optional_marketing_layer": True}
    if score < 820:
        return {"name": "Spoon Bender", "optional_marketing_layer": True}
    return {"name": "The One", "optional_marketing_layer": True}


def compute_score(axis_scores: dict[str, Any], coverage: float, semantic: bool) -> dict[str, Any]:
    if coverage <= 0:
        return {
            "overall": 0,
            "band": "insufficient-evidence",
            "confidence": 0.1,
            "range": {"low": 0, "high": 120},
            "explanation": {
                "diagnostic_instincts": 0.0,
                "vibe_pill_primitives": 0.0,
                "meta_primitives": 0.0,
            },
        }
    weights = {
        "diagnostic_instincts": 0.28,
        "vibe_pill_primitives": 0.47,
        "meta_primitives": 0.25,
    }
    total = 0.0
    explanation = {}
    for section, weight in weights.items():
        avg = sum(v["score"] for v in axis_scores[section].values()) / len(axis_scores[section])
        explanation[section] = round(avg, 3)
        total += avg * weight
    confidence_adjusted = total * (0.72 + min(0.22, coverage * 0.22))
    if semantic:
        confidence_adjusted += 0.04
    score = max(0, min(1000, round(confidence_adjusted * 1000)))
    confidence = round(min(0.9, 0.4 + coverage * 0.3 + (0.12 if semantic else 0)), 3)
    uncertainty = round((1.0 - confidence) * 170)
    return {
        "overall": score,
        "band": "advanced" if score >= 820 else "strong" if score >= 650 else "developing" if score >= 400 else "emerging",
        "confidence": confidence,
        "range": {
            "low": max(0, score - uncertainty),
            "high": min(1000, score + uncertainty),
        },
        "explanation": explanation,
    }


def risks_and_next_steps(axis_scores: dict[str, Any]) -> tuple[list[str], list[str]]:
    flat = []
    for section, axes in axis_scores.items():
        for axis, payload in axes.items():
            flat.append((axis, payload["score"], section))
    weak = sorted(flat, key=lambda x: x[1])[:4]
    risks = [f"Thin evidence for {axis.replace('_', ' ')}." for axis, score, _ in weak if score < 0.55]
    next_steps = []
    for axis, _, section in weak[:3]:
        if axis == "feedback_loops":
            next_steps.append("Build one logging/history loop so a workflow gets better with use.")
        elif axis == "state_awareness":
            next_steps.append("Add explicit state/status tracking to the most-used AI workflow.")
        elif axis == "error_recovery":
            next_steps.append("Create a small debug ledger that captures error, hypothesis, fix, and result.")
        elif axis == "orchestration_trust_boundaries":
            next_steps.append("Add a human approval gate before any external-facing AI action.")
        else:
            next_steps.append(f"Design a focused build that demonstrates {axis.replace('_', ' ')}.")
    return risks or ["No major risk detected from available evidence; confidence still depends on source coverage."], next_steps


def evidence_dossier(evidence: list[Evidence], limit: int = 20) -> list[dict[str, Any]]:
    ranked = sorted(evidence, key=lambda e: (len(e.signals), e.confidence), reverse=True)
    return [asdict(e) | {"text": e.text[:240]} for e in ranked[:limit]]


def generated_artifacts(artifact_dir: Path) -> list[str]:
    if not artifact_dir.exists():
        return []
    return sorted(path.name for path in artifact_dir.iterdir() if path.is_file())


def run_limitations(profile: dict[str, Any], inventory: dict[str, Any]) -> list[str]:
    limitations = list(inventory.get("skew_warnings") or [])
    interpretation = profile.get("score_interpretation") or {}
    limitations.extend(interpretation.get("warnings") or [])
    semantic = profile.get("semantic", {})
    if semantic.get("failures"):
        limitations.append("Semantic provider failures were recorded; inspect semantic.failures before using the score externally.")
    if profile.get("profile_status") == "insufficient_evidence":
        limitations.append("Profile status is insufficient_evidence.")
    return limitations or ["No major run limitations detected beyond normal observed-evidence caveats."]


def build_run_audit(profile: dict[str, Any], inventory: dict[str, Any], artifact_dir: Path, elapsed_seconds: float) -> dict[str, Any]:
    return {
        "run_id": profile["run_id"],
        "generated_at": now_iso(),
        "status": profile["profile_status"],
        "mode": profile["mode"],
        "depth": profile["depth"],
        "artifact_dir": str(artifact_dir),
        "artifacts": generated_artifacts(artifact_dir),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "coverage": profile["coverage"],
        "inventory_summary": inventory.get("used", {}),
        "semantic": profile["semantic"],
        "score": profile["score"],
        "maturity_stage": profile["maturity_stage"],
        "limitations": run_limitations(profile, inventory),
        "next_actions": profile["next_build_plan"][:4],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def render_markdown(profile: dict[str, Any], include_private: bool = False) -> str:
    coverage = profile.get("coverage", {})
    score_warning = (profile.get("score_interpretation") or {}).get("primary_warning")
    coverage_sources = ", ".join(sorted((coverage.get("source_counts") or {}).keys())) or "none"
    coverage_kinds = ", ".join(sorted((coverage.get("kind_counts") or {}).keys())) or "none"
    lines = [
        "---",
        f"created: {datetime.now(timezone.utc).date().isoformat()}",
        f"last_edited: {datetime.now(timezone.utc).date().isoformat()}",
        "version: 0.1",
        "provenance: ai-wizard",
        "---",
        "",
        "# AI Wizard Profile",
        "",
        f"**Stage:** {profile['maturity_stage']['level']} — {profile['maturity_stage']['label']}",
        f"**Archetype:** {profile['archetype']['name']}",
        f"**Score:** {profile['score']['overall']}/1000 ({profile['score']['band']})",
        f"**Score Range:** {profile['score']['range']['low']}–{profile['score']['range']['high']}",
        f"**Confidence:** {profile['score']['confidence']}",
        f"**Semantic:** {profile['semantic']['provider']} / {profile['semantic']['status']}",
        f"**Coverage:** {coverage.get('evidence_records', 0)} items; sources={coverage_sources}; kinds={coverage_kinds}",
        *([f"**Interpretation Warning:** {score_warning}"] if score_warning else []),
        "",
        "## Coverage Summary",
        "",
        *((f"- {warning}" for warning in (coverage.get("skew_warnings") or [])[:4]) if coverage.get("skew_warnings") else ["- No major coverage skew warning was detected."]),
        *([f"- Low-confidence dimensions: {', '.join([axis.replace('_', ' ') for section in (coverage.get('dimensions') or {}).values() for axis, payload in section.items() if payload.get('confidence') == 'low'][:8])}."] if any(payload.get("confidence") == "low" for section in (coverage.get("dimensions") or {}).values() for payload in section.values()) else []),
        "",
        "## Strength Map",
        "",
    ]
    for section, axes in profile["axes"].items():
        lines.append(f"### {section.replace('_', ' ').title()}")
        for axis, payload in axes.items():
            lines.append(f"- **{axis.replace('_', ' ').title()}**: {payload['score']} confidence {payload['confidence']}")
        lines.append("")
    lines.extend(["## Risks", ""])
    lines.extend(f"- {risk}" for risk in profile["risks"])
    lines.extend(["", "## Next Build Plan", ""])
    lines.extend(f"- {step}" for step in profile["next_build_plan"])
    lines.extend(["", "## Evidence Dossier", ""])
    for item in profile["evidence_dossier"]:
        text = item["text"] if include_private else "[redacted summary available in private JSON]"
        lines.append(f"- `{item['id']}` {item['source']} {item['kind']} {item['path']} signals={', '.join(item['signals'])} {text}")
    return "\n".join(lines) + "\n"


def render_share_card(profile: dict[str, Any]) -> str:
    stage = profile["maturity_stage"]
    score = profile["score"]
    coverage = profile.get("coverage", {})
    warnings = (profile.get("score_interpretation") or {}).get("warnings") or []
    top_axes = []
    for section, axes in profile["axes"].items():
        for axis, payload in axes.items():
            top_axes.append((payload["score"], axis))
    top = ", ".join(axis.replace("_", " ") for _, axis in sorted(top_axes, reverse=True)[:3])
    return "\n".join([
        "---",
        f"created: {datetime.now(timezone.utc).date().isoformat()}",
        f"last_edited: {datetime.now(timezone.utc).date().isoformat()}",
        "version: 0.1",
        "provenance: ai-wizard",
        "---",
        "",
        "# AI Wizard Share Card",
        "",
        f"**Profile:** Stage {stage['level']} — {stage['label']}",
        f"**Archetype:** {profile['archetype']['name']}",
        f"**Score:** {score['overall']}/1000 (range {score['range']['low']}–{score['range']['high']})",
        f"**Strongest signals:** {top}",
        f"**Coverage:** {coverage.get('evidence_records', 0)} evidence items across {len(coverage.get('source_counts') or {})} source type(s)",
        f"**Coverage note:** {warnings[0] if warnings else 'No major source skew warning detected.'}",
        "",
        "This public summary is redacted. It does not include raw private evidence.",
        "",
    ])


def init_history() -> None:
    db = history_db()
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            create table if not exists runs (
              run_id text primary key,
              created_at text not null,
              mode text not null,
              depth text not null,
              score integer not null,
              stage integer not null,
              stage_label text not null,
              artifact_dir text not null
            )
            """
        )


def save_history(profile: dict[str, Any], artifact_dir: Path) -> None:
    init_history()
    with sqlite3.connect(history_db()) as conn:
        conn.execute(
            "insert or replace into runs values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                profile["run_id"],
                profile["generated_at"],
                profile["mode"],
                profile["depth"],
                profile["score"]["overall"],
                profile["maturity_stage"]["level"],
                profile["maturity_stage"]["label"],
                str(artifact_dir),
            ),
        )


def make_profile(args: argparse.Namespace, artifact_dir: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    semantic, semantic_payload, analysis_method, methodology_warning = validate_semantic_provider(args)
    evidence: list[Evidence] = []
    if args.mode == "zo-native":
        evidence.extend(collect_workspace_artifacts(limit=args.artifact_limit))
    if args.input:
        evidence.extend(collect_export_artifacts(Path(args.input), source=args.mode, limit=args.artifact_limit, max_scan_files=args.max_scan_files))
    if args.mode == "baseline" and not args.input:
        raise SystemExit("baseline mode requires --input")
    if args.depth == "capped" and semantic:
        evidence = evidence[: args.semantic_cap]
    semantic_reviews: list[dict[str, Any]] = []
    provider = getattr(args, "semantic_provider", "auto")
    replay_path = getattr(args, "semantic_reviews", None)
    if semantic and replay_path and evidence:
        semantic_reviews, review_status = load_semantic_reviews(Path(replay_path), evidence)
        semantic_payload.update(review_status)
        methodology_warning = "Semantic scores replay saved adjudication reviews; no new semantic provider call was made."
        analysis_method = "semantic_review_replay_v0"
    elif semantic and provider == "zo" and evidence:
        review_cap = args.semantic_cap if args.depth == "capped" else len(evidence)
        checkpoint = artifact_dir / "semantic-reviews.jsonl" if artifact_dir else None
        semantic_reviews, review_status = run_zo_semantic_reviews_resumable(
            evidence,
            review_cap,
            checkpoint_path=checkpoint,
            resume=getattr(args, "semantic_resume", False),
        )
        semantic_payload.update(review_status)
        if review_status["status"] == "completed":
            semantic_payload["note"] = "Zo semantic provider completed evidence adjudication and wrote replayable reviews."
        elif review_status["status"] == "partial":
            semantic_payload["note"] = "Zo semantic provider partially completed; unreviewed evidence used deterministic fallback."
        else:
            semantic_payload["note"] = "Zo semantic provider failed; deterministic fallback used for scoring."
    axes = analyze_axes(evidence, semantic=semantic, reviews=semantic_reviews)
    inventory = build_inventory(args.mode, Path(args.input) if args.input else None, evidence, semantic_payload)
    dimension_payload = dimension_coverage(evidence, axes)
    reference_records = min(args.semantic_cap, 24) if args.depth == "capped" else 250
    coverage = min(1.0, len(evidence) / max(1, reference_records))
    score = compute_score(axes, coverage=coverage, semantic=semantic)
    stage = maturity_stage(axes)
    risks, next_steps = risks_and_next_steps(axes)
    run_basis = f"{now_iso()}-{args.mode}-{len(evidence)}-{score['overall']}"
    run_id = hashlib.sha1(run_basis.encode()).hexdigest()[:12]
    profile = {
        "product": "AI Wizard",
        "profile_type": "observed_ai_fluency_profile",
        "profile_status": "ok" if evidence else "insufficient_evidence",
        "run_id": run_id,
        "generated_at": now_iso(),
        "mode": args.mode,
        "depth": "deterministic" if args.no_semantic else args.depth,
        "semantic": semantic_payload,
        "analysis_method": analysis_method,
        "methodology_warning": methodology_warning,
        "coverage": {"evidence_records": len(evidence), "cap": args.semantic_cap if args.depth == "capped" else None},
        "maturity_stage": stage,
        "archetype": archetype(score["overall"]),
        "score": score,
        "axes": axes,
        "risks": risks,
        "next_build_plan": next_steps,
        "evidence_dossier": evidence_dossier(evidence),
        "semantic_reviews": semantic_reviews,
    }
    profile["coverage"] |= {
        "source_counts": inventory["used"]["source_counts"],
        "kind_counts": inventory["used"]["kind_counts"],
        "root_counts": inventory["used"]["root_counts"],
        "top_roots": inventory["used"]["top_roots"],
        "included_source_types": inventory["used"]["included_source_types"],
        "skipped_or_unavailable_source_types": inventory["skipped_or_unavailable_source_types"],
        "skew_warnings": inventory["skew_warnings"],
        "dimensions": dimension_payload,
    }
    profile["score_interpretation"] = score_interpretation(profile["profile_status"], inventory, dimension_payload)
    return profile, inventory


def command_scan(args: argparse.Namespace) -> None:
    inv = source_inventory(args.mode, Path(args.input) if args.input else None)
    print(json.dumps(inv, indent=2))


def command_profile(args: argparse.Namespace) -> None:
    started = perf_counter()
    out_root = Path(args.out) if args.out else build_artifact_root()
    provisional_basis = f"{now_iso()}-{args.mode}-{args.input or ''}-{args.semantic_provider}-{args.semantic_cap}"
    provisional_id = hashlib.sha1(provisional_basis.encode()).hexdigest()[:12]
    artifact_dir = out_root / provisional_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    profile, inventory = make_profile(args, artifact_dir=artifact_dir)
    final_dir = out_root / profile["run_id"]
    if final_dir != artifact_dir:
        if final_dir.exists():
            artifact_dir = final_dir
        else:
            artifact_dir.rename(final_dir)
            artifact_dir = final_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_json(artifact_dir / "inventory.json", inventory)
    write_json(artifact_dir / "profile.json", profile)
    write_json(artifact_dir / "score.json", profile["score"])
    reviews = profile.get("semantic_reviews") or []
    if reviews:
        (artifact_dir / "semantic-reviews.jsonl").write_text(
            "\n".join(json.dumps(review, sort_keys=True) for review in reviews) + "\n"
        )
        profile["semantic"]["replay_path"] = str(artifact_dir / "semantic-reviews.jsonl")
        write_json(artifact_dir / "profile.json", profile)
    (artifact_dir / "dossier.md").write_text(render_markdown(profile, include_private=args.include_excerpts))
    (artifact_dir / "share-card.md").write_text(render_share_card(profile))
    write_json(artifact_dir / "events-summary.json", {
        "run_id": profile["run_id"],
        "evidence_records": profile["coverage"]["evidence_records"],
        "sources": sorted({item["source"] for item in profile["evidence_dossier"]}),
    })
    (artifact_dir / "next-build-plan.md").write_text("\n".join([
        "---",
        f"created: {datetime.now(timezone.utc).date().isoformat()}",
        f"last_edited: {datetime.now(timezone.utc).date().isoformat()}",
        "version: 0.1",
        "provenance: ai-wizard",
        "---",
        "",
        "# Next Build Plan",
        "",
        *[f"- {step}" for step in profile["next_build_plan"]],
        "",
    ]))
    if not args.skip_history:
        save_history(profile, artifact_dir)
    audit = build_run_audit(profile, inventory, artifact_dir, perf_counter() - started)
    write_json(artifact_dir / "run-audit.json", audit)
    print(json.dumps({
        "run_id": profile["run_id"],
        "artifact_dir": str(artifact_dir),
        "score": profile["score"]["overall"],
        "score_range": profile["score"]["range"],
        "stage": profile["maturity_stage"],
    }, indent=2))


def latest_run_dir() -> Path:
    root = build_artifact_root()
    if not root.exists():
        raise SystemExit("No AI Wizard run directory exists yet.")
    candidates = [path for path in root.iterdir() if path.is_dir() and (path / "profile.json").exists()]
    if not candidates:
        raise SystemExit("No AI Wizard profile runs found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def command_report(args: argparse.Namespace) -> None:
    run_dir = latest_run_dir() if args.latest else Path(args.run)
    profile_path = run_dir / "profile.json"
    if not profile_path.exists():
        raise SystemExit(f"profile.json not found in run directory: {run_dir}")
    profile = json.loads(profile_path.read_text())
    inventory = {}
    inventory_path = run_dir / "inventory.json"
    if inventory_path.exists():
        inventory = json.loads(inventory_path.read_text())
    audit_path = run_dir / "run-audit.json"
    audit = json.loads(audit_path.read_text()) if audit_path.exists() else {}
    report = {
        "run_id": profile.get("run_id"),
        "run_dir": str(run_dir),
        "status": profile.get("profile_status"),
        "stage": profile.get("maturity_stage"),
        "score": profile.get("score"),
        "semantic": profile.get("semantic"),
        "coverage": profile.get("coverage"),
        "inventory": inventory.get("used", {}),
        "artifacts": generated_artifacts(run_dir),
        "limitations": audit.get("limitations") or run_limitations(profile, inventory or {"skew_warnings": []}),
        "next_actions": audit.get("next_actions") or profile.get("next_build_plan", [])[:4],
    }
    print(json.dumps(report, indent=2))


def command_history(_: argparse.Namespace) -> None:
    init_history()
    with sqlite3.connect(history_db()) as conn:
        rows = conn.execute(
            "select run_id, created_at, mode, depth, score, stage, stage_label, artifact_dir from runs order by created_at desc limit 20"
        ).fetchall()
    print(json.dumps([
        {
            "run_id": r[0],
            "created_at": r[1],
            "mode": r[2],
            "depth": r[3],
            "score": r[4],
            "stage": r[5],
            "stage_label": r[6],
            "artifact_dir": r[7],
        }
        for r in rows
    ], indent=2))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AI Wizard observed AI fluency profiler")
    sub = p.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--mode", choices=["zo-native", "baseline"], default="zo-native")
    scan.add_argument("--input")
    scan.set_defaults(func=command_scan)
    prof = sub.add_parser("profile")
    prof.add_argument("--mode", choices=["zo-native", "baseline"], default="zo-native")
    prof.add_argument("--input")
    prof.add_argument("--depth", choices=["capped", "full"], default="capped")
    prof.add_argument("--semantic-cap", type=int, default=120)
    prof.add_argument("--artifact-limit", type=int, default=250)
    prof.add_argument("--max-scan-files", type=int, default=250, help="Maximum export files to inspect before stopping; bounds large Claude/Codex histories.")
    prof.add_argument("--semantic-provider", choices=["auto", "heuristic", "zo"], default="auto", help="Semantic provider contract. auto currently uses heuristic fallback unless upgraded.")
    prof.add_argument("--semantic-reviews", help="Replay a saved semantic-reviews.jsonl file instead of calling a semantic provider.")
    prof.add_argument("--semantic-resume", action="store_true", help="Reuse semantic-reviews.jsonl in the target run directory and only request missing Zo reviews.")
    prof.add_argument("--no-semantic", action="store_true")
    prof.add_argument("--include-excerpts", action="store_true")
    prof.add_argument("--skip-history", action="store_true", help="Do not write this run to the persistent history DB")
    prof.add_argument("--out")
    prof.set_defaults(func=command_profile)
    hist = sub.add_parser("history")
    hist.set_defaults(func=command_history)
    rep = sub.add_parser("report")
    rep.add_argument("--run", help="Artifact directory containing profile.json")
    rep.add_argument("--latest", action="store_true", help="Report on the latest persisted AI Wizard run")
    rep.set_defaults(func=command_report)
    return p


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
