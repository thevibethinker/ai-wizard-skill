import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_wizard.py"
FIXTURE = ROOT / "tests" / "fixtures" / "baseline"
CHATGPT_FIXTURE = ROOT / "tests" / "fixtures" / "chatgpt_export"
GOLDEN_LOW = ROOT / "tests" / "fixtures" / "golden_low"
GOLDEN_MID = ROOT / "tests" / "fixtures" / "golden_mid"
GOLDEN_HIGH = ROOT / "tests" / "fixtures" / "golden_high"


def run_cmd(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    merged_env.setdefault("AI_WIZARD_TRACE_DIRS", "")
    if env:
        merged_env.update(env)
    return subprocess.run(["python3", str(SCRIPT), *args], text=True, capture_output=True, check=True, env=merged_env)


def test_scan_baseline_fixture():
    result = run_cmd("scan", "--mode", "baseline", "--input", str(FIXTURE))
    payload = json.loads(result.stdout)
    assert payload["mode"] == "baseline"
    assert any(source["source"] == "chatgpt_export" for source in payload["sources"])


def test_profile_baseline_fixture(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--no-semantic",
        "--skip-history",
        "--out",
        str(tmp_path),
    )
    payload = json.loads(result.stdout)
    artifact_dir = Path(payload["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["profile_type"] == "observed_ai_fluency_profile"
    assert profile["semantic_mode"] == "heuristic"
    assert profile["semantic_status"] == "not_requested"
    assert profile["raw_score"] == profile["score"]["overall"]
    assert set(profile["calibrated_range"]) == {"low", "high", "rationale"}
    assert profile["calibrated_range"]["low"] <= profile["raw_score"] <= profile["calibrated_range"]["high"]
    assert profile["confidence"] in {"low", "medium", "high"}
    assert profile["semantic_events"]
    assert "vibe_pill_primitives" in profile["axes"]
    assert profile["coverage"]["included_source_types"] == ["conversation_trace"]
    assert profile["dimension_coverage"]["vibe_pill_primitives"]["pipeline_thinking"]["evidence_count"] >= 1
    assert profile["dimension_coverage"]["vibe_pill_primitives"]["pipeline_thinking"]["confidence"] in {"medium", "high"}
    pipeline_dossier = profile["dimension_dossier"]["vibe_pill_primitives"]["pipeline_thinking"]
    assert "strongest_positive_evidence" in pipeline_dossier
    assert "weakest_or_missing_evidence" in pipeline_dossier
    assert "possible_false_positives" in pipeline_dossier
    assert "representative_artifact_paths" in pipeline_dossier
    assert (artifact_dir / "dossier.md").exists()
    assert (artifact_dir / "share-card.md").exists()


def test_zo_native_excludes_ai_wizard_self_artifacts(tmp_path):
    workspace = tmp_path / "workspace"
    self_dir = workspace / "Skills" / "ai-wizard"
    useful_dir = workspace / "N5" / "builds" / "real-build"
    self_dir.mkdir(parents=True)
    useful_dir.mkdir(parents=True)
    (self_dir / "README.md").write_text(
        "pipeline feedback integration orchestration context state error " * 20
    )
    (useful_dir / "PLAN.md").write_text(
        "We verified source data, added a human approval gate, and logged debug state."
    )
    result = run_cmd(
        "profile",
        "--mode",
        "zo-native",
        "--no-semantic",
        "--skip-history",
        "--out",
        str(tmp_path / "out"),
        env={"AI_WIZARD_WORKSPACE": str(workspace)},
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    paths = [item["path"] for item in profile["evidence_dossier"]]
    assert all("Skills/ai-wizard" not in path for path in paths)
    assert any("real-build" in path for path in paths)


def test_public_outputs_do_not_include_private_fixture_text(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--skip-history",
        "--out",
        str(tmp_path),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    share = (artifact_dir / "share-card.md").read_text()
    dossier = (artifact_dir / "dossier.md").read_text()
    assert "customer intake pipeline" not in share
    assert "customer intake pipeline" not in dossier


def test_empty_input_is_insufficient_evidence_not_positive_score(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(empty),
        "--skip-history",
        "--out",
        str(tmp_path / "out"),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["profile_status"] == "insufficient_evidence"
    assert profile["score"]["overall"] == 0
    assert profile["score"]["confidence"] <= 0.2
    assert profile["score_interpretation_warning"]
    assert profile["dimension_coverage"]["meta_primitives"]["state_awareness"]["confidence"] == "low"


def test_scan_does_not_claim_chatgpt_export_without_input():
    result = run_cmd("scan", "--mode", "zo-native")
    payload = json.loads(result.stdout)
    chatgpt = next(source for source in payload["sources"] if source["source"] == "chatgpt_export")
    assert chatgpt["available"] is False
    assert chatgpt["path"] is None
    assert "--input" in chatgpt["notes"]


def test_capped_semantic_profile_uses_real_or_fallback_semantic_status(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--skip-history",
        "--out",
        str(tmp_path),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["semantic"]["requested"] is False
    assert profile["semantic"]["provider"] in {"zo_ask", "heuristic_fallback"}
    assert profile["analysis_method"] != "keyword_heuristic_v0"
    assert profile["semantic_mode"] == "heuristic"
    assert profile["semantic_status"] == "not_requested"


def test_explicit_heuristic_semantic_provider_marks_fallback(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--semantic-provider",
        "heuristic",
        "--skip-history",
        "--out",
        str(tmp_path),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["semantic"]["requested"] is False
    assert profile["semantic"]["provider"] == "heuristic_fallback"
    assert profile["semantic"]["status"] == "not_requested"
    assert profile["semantic_mode"] == "heuristic"
    assert profile["analysis_method"] == "deterministic_keyword_heuristic_v0"


def test_zo_semantic_provider_requires_token(tmp_path):
    env = {"ZO_CLIENT_IDENTITY_TOKEN": ""}
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "profile",
            "--mode",
            "baseline",
            "--input",
            str(FIXTURE),
            "--semantic-provider",
            "zo",
            "--skip-history",
            "--out",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        env={**os.environ, **env},
        check=False,
    )
    assert result.returncode != 0
    assert "ZO_CLIENT_IDENTITY_TOKEN" in result.stderr or "ZO_CLIENT_IDENTITY_TOKEN" in result.stdout


def test_zo_semantic_provider_writes_replayable_reviews(tmp_path):
    response = {
        "evidence_reviews": [
            {
                "evidence_id": "baseline-0000",
                "quality": "exemplary",
                "axis_scores": {
                    "pipeline_thinking": 0.95,
                    "feedback_loops": 0.85,
                    "state_awareness": 0.9,
                },
                "supported_claims": ["Shows an explicit source to transform to delivery pipeline."],
                "risk_flags": ["No obvious external approval gate in the excerpt."],
                "level_up_hint": "Add an explicit human gate before delivery.",
            }
        ],
        "batch_quality_notes": "test fixture",
    }
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--semantic-provider",
        "zo",
        "--semantic-cap",
        "1",
        "--skip-history",
        "--out",
        str(tmp_path),
        env={
            "ZO_CLIENT_IDENTITY_TOKEN": "test-token",
            "AI_WIZARD_ZO_ASK_MOCK_RESPONSE": json.dumps(response),
        },
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["semantic"]["provider"] == "zo_ask"
    assert profile["semantic"]["status"] == "complete"
    assert profile["semantic_mode"] == "semantic-zo"
    assert profile["semantic_status"] == "complete"
    assert profile["semantic"]["items_reviewed"] == 1
    assert (artifact_dir / "semantic-reviews.jsonl").exists()
    assert profile["analysis_method"] == "zo_semantic_adjudication_v0"
    assert profile["axes"]["vibe_pill_primitives"]["pipeline_thinking"]["score"] > 0


def test_zo_semantic_provider_malformed_response_becomes_failed(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--semantic-provider",
        "zo",
        "--semantic-cap",
        "1",
        "--skip-history",
        "--out",
        str(tmp_path),
        env={
            "ZO_CLIENT_IDENTITY_TOKEN": "test-token",
            "AI_WIZARD_ZO_ASK_MOCK_RESPONSE": "not json",
        },
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["semantic"]["provider"] == "zo_ask"
    assert profile["semantic"]["status"] == "failed"
    assert profile["semantic_mode"] == "semantic-zo"
    assert profile["semantic_status"] == "failed"
    assert any(event["type"] == "retry_scheduled" for event in profile["semantic_events"])
    assert any(event["type"] == "fallback_to_heuristic" for event in profile["semantic_events"])
    assert profile["semantic"]["items_reviewed"] == 0
    assert not (artifact_dir / "semantic-reviews.jsonl").exists()


def test_semantic_review_replay_reuses_saved_reviews(tmp_path):
    reviews = tmp_path / "reviews.jsonl"
    reviews.write_text(json.dumps({
        "evidence_id": "baseline-0000",
        "quality": "exemplary",
        "axis_scores": {
            "pipeline_thinking": 1.0,
            "feedback_loops": 0.9,
            "state_awareness": 0.8,
        },
        "supported_claims": ["Replay review"],
        "risk_flags": [],
        "level_up_hint": "Keep replay deterministic.",
    }) + "\n")
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--semantic-reviews",
        str(reviews),
        "--skip-history",
        "--out",
        str(tmp_path / "out"),
        env={"ZO_CLIENT_IDENTITY_TOKEN": ""},
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["semantic"]["provider"] == "semantic_review_replay"
    assert profile["semantic"]["status"] == "complete"
    assert profile["analysis_method"] == "semantic_review_replay_v0"
    assert profile["semantic"]["items_reviewed"] == 1


def test_zo_semantic_checkpoint_resume_skips_completed_batches(tmp_path):
    first_response = {
        "evidence_reviews": [
            {
                "evidence_id": "baseline-0000",
                "quality": "strong",
                "axis_scores": {"pipeline_thinking": 0.8},
                "supported_claims": ["First batch review"],
                "risk_flags": [],
                "level_up_hint": "Keep going.",
            }
        ],
        "batch_quality_notes": "first run",
    }
    out = tmp_path / "out"
    result1 = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--semantic-provider",
        "zo",
        "--semantic-cap",
        "1",
        "--skip-history",
        "--out",
        str(out),
        env={
            "ZO_CLIENT_IDENTITY_TOKEN": "test-token",
            "AI_WIZARD_ZO_ASK_MOCK_RESPONSE": json.dumps(first_response),
        },
    )
    artifact_dir = Path(json.loads(result1.stdout)["artifact_dir"])
    assert (artifact_dir / "semantic-reviews.jsonl").exists()

    result2 = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--semantic-provider",
        "zo",
        "--semantic-cap",
        "1",
        "--semantic-resume",
        "--skip-history",
        "--out",
        str(out),
        env={
            "ZO_CLIENT_IDENTITY_TOKEN": "test-token",
            "AI_WIZARD_ZO_ASK_MOCK_RESPONSE": "not json",
        },
    )
    artifact_dir2 = Path(json.loads(result2.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir2 / "profile.json").read_text())
    assert artifact_dir2 == artifact_dir
    assert profile["semantic_status"] == "complete"
    assert profile["semantic"]["items_reused"] == 1
    assert any(event["type"] == "resume_loaded" for event in profile["semantic_events"])
    assert any(event["type"] == "resume_skipped_batches" for event in profile["semantic_events"])


def test_zo_semantic_retry_can_recover_after_provider_error(tmp_path):
    response = {
        "evidence_reviews": [
            {
                "evidence_id": "baseline-0000",
                "quality": "strong",
                "axis_scores": {"state_awareness": 0.75},
                "supported_claims": ["Recovered review"],
                "risk_flags": [],
                "level_up_hint": "Record retry recovery.",
            }
        ],
        "batch_quality_notes": "retry success",
    }
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--semantic-provider",
        "zo",
        "--semantic-cap",
        "1",
        "--semantic-backoff",
        "0",
        "--skip-history",
        "--out",
        str(tmp_path),
        env={
            "ZO_CLIENT_IDENTITY_TOKEN": "test-token",
            "AI_WIZARD_ZO_ASK_MOCK_RESPONSES": json.dumps([{"raise": "timeout"}, response]),
        },
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["semantic_status"] == "complete"
    assert any(event["type"] == "provider_error" for event in profile["semantic_events"])
    assert any(event["type"] == "retry_scheduled" for event in profile["semantic_events"])


def test_chatgpt_shaped_export_fixture_profiles(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(CHATGPT_FIXTURE),
        "--no-semantic",
        "--skip-history",
        "--out",
        str(tmp_path),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["profile_status"] == "ok"
    assert profile["coverage"]["evidence_records"] >= 1
    assert profile["axes"]["vibe_pill_primitives"]["pipeline_thinking"]["score"] > 0


def test_golden_fixture_scores_are_ordered(tmp_path):
    scores = []
    for name, fixture in [("low", GOLDEN_LOW), ("mid", GOLDEN_MID), ("high", GOLDEN_HIGH)]:
        result = run_cmd(
            "profile",
            "--mode",
            "baseline",
            "--input",
            str(fixture),
            "--no-semantic",
            "--skip-history",
            "--out",
            str(tmp_path / name),
        )
        scores.append(json.loads(result.stdout)["score"])
    assert scores[0] < scores[1] < scores[2]


def test_codex_jsonl_skips_session_meta_and_system_context(tmp_path):
    export_dir = tmp_path / "codex"
    export_dir.mkdir()
    session = export_dir / "rollout.jsonl"
    session.write_text(
        "\n".join([
            json.dumps({
                "timestamp": "2026-05-25T00:00:00Z",
                "type": "session_meta",
                "payload": {
                    "base_instructions": "architecture pipeline approval gate schema debug state " * 20,
                },
            }),
            json.dumps({
                "timestamp": "2026-05-25T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "developer pipeline orchestration context"}],
                },
            }),
            json.dumps({
                "timestamp": "2026-05-25T00:00:02Z",
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "You are operating on a system called Zo. <system_prompt>architecture pipeline approval gate schema debug state</system_prompt>\n\nMake this shorter.",
                },
            }),
        ])
    )
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(export_dir),
        "--no-semantic",
        "--skip-history",
        "--out",
        str(tmp_path / "out"),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    dossier_text = json.dumps(profile["evidence_dossier"])
    assert "base_instructions" not in dossier_text
    assert "developer pipeline orchestration" not in dossier_text
    assert "system_prompt" not in dossier_text
    assert "Make this shorter" in dossier_text
    assert profile["coverage"]["evidence_records"] == 1
    assert profile["score"]["overall"] < 100


def test_export_collection_scans_past_noisy_files_until_evidence_limit(tmp_path):
    export_dir = tmp_path / "codex"
    export_dir.mkdir()
    for idx in range(3):
        noisy = export_dir / f"old-{idx}.jsonl"
        noisy.write_text(json.dumps({
            "timestamp": "2026-05-25T00:00:00Z",
            "type": "session_meta",
            "payload": {"base_instructions": "pipeline approval gate " * 20},
        }) + "\n")
    useful = export_dir / "new.jsonl"
    useful.write_text(json.dumps({
        "timestamp": "2026-05-25T00:00:01Z",
        "type": "event_msg",
        "payload": {
            "type": "user_message",
            "message": "Map the workflow pipeline, add a human approval gate, and log validation failures.",
        },
    }) + "\n")
    os.utime(useful, (2000000000, 2000000000))
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(export_dir),
        "--no-semantic",
        "--skip-history",
        "--artifact-limit",
        "1",
        "--out",
        str(tmp_path / "out"),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["coverage"]["evidence_records"] == 1
    assert profile["score"]["overall"] > 0


def test_inventory_artifact_reports_coverage_and_skew(tmp_path):
    workspace = tmp_path / "workspace"
    build_dir = workspace / "N5" / "builds" / "artifact-heavy"
    build_dir.mkdir(parents=True)
    for idx in range(8):
        (build_dir / f"PLAN-{idx}.md").write_text(
            "Plan the pipeline, validate schema, add approval gate, log state, and fix regression."
        )
    result = run_cmd(
        "profile",
        "--mode",
        "zo-native",
        "--no-semantic",
        "--skip-history",
        "--out",
        str(tmp_path / "out"),
        env={"AI_WIZARD_WORKSPACE": str(workspace)},
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    inventory = json.loads((artifact_dir / "inventory.json").read_text())
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert inventory["total_evidence_items_scanned"] == 8
    assert inventory["included_source_types"] == ["workspace_artifact"]
    assert inventory["top_roots"][0]["name"] == "N5"
    assert any("Artifact-heavy evidence" in warning for warning in inventory["skew_warnings"])
    assert profile["coverage"]["top_roots"][0]["name"] == "N5"
    assert profile["score_interpretation_warning"]


def test_public_outputs_include_compact_coverage_without_raw_text(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--no-semantic",
        "--skip-history",
        "--out",
        str(tmp_path),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    share = (artifact_dir / "share-card.md").read_text()
    dossier = (artifact_dir / "dossier.md").read_text()
    assert "**Coverage:**" in share
    assert "## Coverage Summary" in dossier
    assert "## Dimension Evidence Review" in dossier
    assert "Strongest positive evidence" in dossier
    assert "Weakest or missing evidence" in dossier
    assert "Possible false positives" in dossier
    assert "Representative artifact paths" in dossier
    assert "customer intake pipeline" not in share
    assert "customer intake pipeline" not in dossier


def test_calibrated_range_narrows_with_strong_coverage_and_complete_semantic(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    evidence_index = 0
    for idx in range(24):
        root = export_dir / f"source-{idx % 4}"
        root.mkdir(exist_ok=True)
        trace = root / f"trace-{idx:02d}.jsonl"
        trace.write_text(json.dumps({
            "timestamp": f"2026-05-25T00:00:{idx:02d}Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "Plan the workflow pipeline, validate source schema, add approval gate, log state, and debug regression.",
            },
        }) + "\n")
        evidence_index += 1
    reviews = tmp_path / "reviews.jsonl"
    reviews.write_text(json.dumps({
        "evidence_id": "baseline-0000",
        "quality": "strong",
        "axis_scores": {
            "pipeline_thinking": 0.9,
            "feedback_loops": 0.8,
            "state_awareness": 0.85,
        },
        "supported_claims": ["Fixture demonstrates pipeline and state behavior."],
        "risk_flags": [],
        "level_up_hint": "Keep calibration visible.",
    }) + "\n")
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(export_dir),
        "--semantic-reviews",
        str(reviews),
        "--semantic-cap",
        "24",
        "--skip-history",
        "--out",
        str(tmp_path / "out"),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    width = profile["calibrated_range"]["high"] - profile["calibrated_range"]["low"]
    assert profile["semantic_status"] == "complete"
    assert profile["confidence"] == "high"
    assert width <= 160
    assert "Semantic adjudication completed" in profile["calibrated_range"]["rationale"]


def test_calibrated_range_widens_with_skew_and_failed_semantic(tmp_path):
    workspace = tmp_path / "workspace"
    build_dir = workspace / "N5" / "builds" / "artifact-heavy"
    build_dir.mkdir(parents=True)
    for idx in range(8):
        (build_dir / f"PLAN-{idx}.md").write_text(
            "Plan the pipeline, validate schema, add approval gate, log state, and fix regression."
        )
    result = run_cmd(
        "profile",
        "--mode",
        "zo-native",
        "--semantic-provider",
        "zo",
        "--semantic-cap",
        "8",
        "--semantic-backoff",
        "0",
        "--skip-history",
        "--out",
        str(tmp_path / "out"),
        env={
            "AI_WIZARD_WORKSPACE": str(workspace),
            "ZO_CLIENT_IDENTITY_TOKEN": "test-token",
            "AI_WIZARD_ZO_ASK_MOCK_RESPONSE": "not json",
        },
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    width = profile["calibrated_range"]["high"] - profile["calibrated_range"]["low"]
    assert profile["semantic_status"] == "failed"
    assert profile["confidence"] == "low"
    assert width >= 300
    assert "Source skew warnings exist" in profile["calibrated_range"]["rationale"]
    assert "Semantic adjudication failed" in profile["calibrated_range"]["rationale"]


def test_dogfood_mode_writes_report_and_profile_metadata(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--no-semantic",
        "--dogfood",
        "--skip-history",
        "--out",
        str(tmp_path),
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    report = json.loads((artifact_dir / "dogfood-report.json").read_text())
    markdown = (artifact_dir / "dogfood-report.md").read_text()
    assert profile["dogfood_report"]["path"] == str(artifact_dir / "dogfood-report.json")
    assert profile["dogfood_report"]["markdown_path"] == str(artifact_dir / "dogfood-report.md")
    assert report["report_type"] == "dogfood_evaluator_diagnostics"
    assert report["semantic_status"]["status"] == "not_requested"
    assert report["semantic_status"]["provider"] == "heuristic"
    assert report["evidence_inventory_summary"]["included_source_types"] == ["conversation_trace"]
    assert report["evidence_inventory_summary"]["raw_private_evidence_included"] is False
    assert "Semantic Reliability" in markdown
    assert "Coverage warning" in markdown
    assert "customer intake pipeline" not in markdown


def test_dogfood_report_highlights_semantic_failure_and_fallback_events(tmp_path):
    result = run_cmd(
        "profile",
        "--mode",
        "baseline",
        "--input",
        str(FIXTURE),
        "--semantic-provider",
        "zo",
        "--semantic-cap",
        "1",
        "--semantic-backoff",
        "0",
        "--dogfood",
        "--skip-history",
        "--out",
        str(tmp_path),
        env={
            "ZO_CLIENT_IDENTITY_TOKEN": "test-token",
            "AI_WIZARD_ZO_ASK_MOCK_RESPONSE": "not json",
        },
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    report = json.loads((artifact_dir / "dogfood-report.json").read_text())
    event_types = [event["type"] for event in report["retry_timeout_fallback_events"]["events"]]
    assert report["semantic_status"]["status"] == "failed"
    assert "provider_error" in event_types
    assert "retry_scheduled" in event_types
    assert "fallback_to_heuristic" in event_types
    assert any("Semantic status is failed" in risk for risk in report["scoring_volatility"]["confidence_risks"])


def test_dogfood_report_highlights_sparse_skewed_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    build_dir = workspace / "N5" / "builds" / "sparse"
    build_dir.mkdir(parents=True)
    (build_dir / "PLAN.md").write_text("Plan the pipeline, validate schema, add approval gate, and log state.")
    result = run_cmd(
        "profile",
        "--mode",
        "zo-native",
        "--no-semantic",
        "--dogfood",
        "--skip-history",
        "--out",
        str(tmp_path / "out"),
        env={"AI_WIZARD_WORKSPACE": str(workspace)},
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    report = json.loads((artifact_dir / "dogfood-report.json").read_text())
    risks = report["scoring_volatility"]["confidence_risks"]
    assert report["evidence_inventory_summary"]["evidence_records"] == 1
    assert report["evidence_inventory_summary"]["top_roots"][0]["name"] == "N5"
    assert any("Sparse evidence count" in risk for risk in risks)
    assert any("low evidence" in risk.lower() or "low evidence count" in risk.lower() for risk in risks)


def test_claude_code_jsonl_traces(tmp_path):
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    lines = [
        json.dumps({"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-07-01T00:00:00Z"}),
        json.dumps({"type": "user", "isMeta": True, "message": {"role": "user", "content": "<local-command-caveat>meta</local-command-caveat>"}, "timestamp": "2026-07-01T00:00:01Z"}),
        json.dumps({"type": "user", "message": {"role": "user", "content": "Please validate the schema and add an approval gate before deploy."}, "timestamp": "2026-07-01T00:00:02Z"}),
        json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "tool output"}]}, "timestamp": "2026-07-01T00:00:03Z"}),
        json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "Now debug the pipeline and retry with a checkpoint."}]}, "timestamp": "2026-07-01T00:00:04Z"}),
        json.dumps({"type": "user", "message": {"role": "user", "content": "[Request interrupted by user]"}, "timestamp": "2026-07-01T00:00:05Z"}),
        json.dumps({"type": "user", "message": {"role": "user", "content": "Fix the ai-wizard scorer itself."}, "timestamp": "2026-07-01T00:00:06Z"}),
    ]
    (trace_dir / "session.jsonl").write_text("\n".join(lines))
    import sys
    sys.path.insert(0, str(SCRIPT.parent))
    import importlib
    import ai_wizard
    importlib.reload(ai_wizard)
    items = ai_wizard.collect_conversation_traces(limit=20, trace_dirs=[trace_dir])
    texts = [item.text for item in items]
    assert len(items) == 2
    assert any("validate the schema" in t for t in texts)
    assert any("debug the pipeline" in t for t in texts)
    assert all("ai-wizard" not in t.lower() for t in texts)
    assert all(item.kind == "operator_message" for item in items)


def test_git_history_collector(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "fix: debug regression and add validation gate"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "feat: wire pipeline orchestration"], cwd=repo, check=True)
    import sys
    sys.path.insert(0, str(SCRIPT.parent))
    import importlib
    import ai_wizard
    importlib.reload(ai_wizard)
    items = ai_wizard.collect_git_history(limit=10, repo=repo)
    assert len(items) == 2
    assert items[0].kind == "commit"
    assert items[0].source == "git"
    assert any("orchestration" in item.text for item in items)


def test_sources_flag_workspace_only(tmp_path):
    workspace = tmp_path / "workspace"
    build_dir = workspace / "N5" / "builds" / "b"
    build_dir.mkdir(parents=True)
    for idx in range(4):
        (build_dir / f"PLAN-{idx}.md").write_text("Plan the pipeline and validate schema.")
    result = run_cmd(
        "profile", "--mode", "zo-native", "--no-semantic", "--skip-history",
        "--sources", "workspace",
        "--out", str(tmp_path / "out"),
        env={"AI_WIZARD_WORKSPACE": str(workspace)},
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert all(item["source"] == "workspace" for item in profile["evidence_dossier"])


def test_anthropic_semantic_provider_requires_key(tmp_path):
    env = {**os.environ, "AI_WIZARD_ZO_ASK_MOCK_RESPONSE": ""}
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("AI_WIZARD_ANTHROPIC_MOCK_RESPONSE", None)
    env.pop("AI_WIZARD_ANTHROPIC_MOCK_RESPONSES", None)
    result = subprocess.run(
        ["python3", str(SCRIPT), "profile", "--mode", "baseline", "--input", str(FIXTURE),
         "--semantic-provider", "anthropic", "--skip-history", "--out", str(tmp_path)],
        text=True, capture_output=True, env=env, check=False,
    )
    assert result.returncode != 0
    assert "ANTHROPIC_API_KEY" in result.stderr or "ANTHROPIC_API_KEY" in result.stdout


def test_anthropic_semantic_provider_writes_replayable_reviews(tmp_path):
    response = {
        "evidence_reviews": [
            {
                "evidence_id": "baseline-0000",
                "quality": "strong",
                "axis_scores": {"pipeline_thinking": 0.9, "feedback_loops": 0.8},
                "supported_claims": ["Shows a pipeline with validation."],
                "risk_flags": [],
                "level_up_hint": "Add a human gate.",
            }
        ],
        "batch_quality_notes": "test fixture",
    }
    result = run_cmd(
        "profile", "--mode", "baseline", "--input", str(FIXTURE),
        "--semantic-provider", "anthropic", "--semantic-cap", "1",
        "--skip-history", "--out", str(tmp_path),
        env={"AI_WIZARD_ANTHROPIC_MOCK_RESPONSE": json.dumps(response)},
    )
    artifact_dir = Path(json.loads(result.stdout)["artifact_dir"])
    profile = json.loads((artifact_dir / "profile.json").read_text())
    assert profile["semantic"]["provider"] == "anthropic"
    assert profile["semantic"]["status"] == "complete"
    assert profile["semantic_mode"] == "semantic-anthropic"
    assert profile["semantic_status"] == "complete"
    assert profile["semantic"]["items_reviewed"] == 1
    assert (artifact_dir / "semantic-reviews.jsonl").exists()
    assert profile["analysis_method"] == "anthropic_semantic_adjudication_v0"
    assert profile["axes"]["vibe_pill_primitives"]["pipeline_thinking"]["score"] > 0


def test_codex_bare_rollout_jsonl_traces(tmp_path):
    trace_dir = tmp_path / "codex-sessions"
    trace_dir.mkdir()
    lines = [
        json.dumps({"type": "session_meta", "payload": {"id": "s1"}, "timestamp": "2026-07-01T00:00:00Z"}),
        json.dumps({"type": "message", "role": "user", "content": [{"type": "input_text", "text": "You are Codex, based on GPT-5."}], "timestamp": "2026-07-01T00:00:01Z"}),
        json.dumps({"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Refactor the ingest pipeline and add schema validation with retries."}], "timestamp": "2026-07-01T00:00:02Z"}),
        json.dumps({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done."}], "timestamp": "2026-07-01T00:00:03Z"}),
        json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Now orchestrate the deploy with an approval gate."}]}, "timestamp": "2026-07-01T00:00:04Z"}),
    ]
    (trace_dir / "rollout-2026-07-01.jsonl").write_text("\n".join(lines))
    import sys
    sys.path.insert(0, str(SCRIPT.parent))
    import importlib
    import ai_wizard
    importlib.reload(ai_wizard)
    items = ai_wizard.collect_conversation_traces(limit=20, trace_dirs=[trace_dir])
    texts = [item.text for item in items]
    assert len(items) == 2
    assert any("ingest pipeline" in t for t in texts)
    assert any("approval gate" in t for t in texts)
    assert all("you are codex" not in t.lower() for t in texts)
