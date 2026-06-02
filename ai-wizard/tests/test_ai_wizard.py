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
    assert "vibe_pill_primitives" in profile["axes"]
    assert (artifact_dir / "dossier.md").exists()
    assert (artifact_dir / "share-card.md").exists()
    inventory = json.loads((artifact_dir / "inventory.json").read_text())
    assert inventory["used"]["total_evidence_items_scanned"] == profile["coverage"]["evidence_records"]
    assert inventory["used"]["included_source_types"]
    assert "dimensions" in profile["coverage"]
    pipeline = profile["coverage"]["dimensions"]["vibe_pill_primitives"]["pipeline_thinking"]
    assert set(pipeline) == {"evidence_count", "representative_sources", "confidence", "missing_evidence_notes"}
    assert pipeline["confidence"] in {"low", "medium", "high"}


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
    assert profile["score_interpretation"]["warnings"]
    assert profile["coverage"]["dimensions"]["meta_primitives"]["error_recovery"]["confidence"] == "low"


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
    assert profile["semantic"]["requested"] is True
    assert profile["semantic"]["provider"] in {"zo_ask", "heuristic_fallback"}
    assert profile["analysis_method"] != "keyword_heuristic_v0"
    assert "semantic" in profile["methodology_warning"].lower()


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
    assert profile["semantic"]["requested"] is True
    assert profile["semantic"]["provider"] == "heuristic_fallback"
    assert profile["semantic"]["status"] == "fallback"
    assert profile["analysis_method"] == "semantic_proxy_heuristic_v0"


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
    assert profile["semantic"]["status"] == "completed"
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
    assert profile["semantic"]["status"] == "completed"
    assert profile["analysis_method"] == "semantic_review_replay_v0"
    assert profile["semantic"]["items_reviewed"] == 1


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


def test_workspace_heavy_inventory_warns_about_root_and_artifact_skew(tmp_path):
    workspace = tmp_path / "workspace"
    build_dir = workspace / "N5" / "builds" / "dominant-build"
    build_dir.mkdir(parents=True)
    for idx in range(8):
        (build_dir / f"artifact-{idx}.md").write_text(
            "pipeline source transform store deliver schema approval gate validation debug state"
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
    inventory = json.loads((artifact_dir / "inventory.json").read_text())
    warnings = " ".join(inventory["skew_warnings"])
    assert "Artifact-heavy evidence" in warnings
    assert "dominant-build" in warnings
    assert profile["score_interpretation"]["primary_warning"] == "Score is an observed-artifact score, not a personal ceiling."
    assert profile["coverage"]["top_roots"][0]["root"] == "N5/builds/dominant-build"


def test_public_outputs_include_compact_coverage_not_raw_evidence(tmp_path):
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
    dossier = (artifact_dir / "dossier.md").read_text()
    share = (artifact_dir / "share-card.md").read_text()
    assert "## Coverage Summary" in dossier
    assert "**Coverage:**" in share
    assert "customer intake pipeline" not in share
    assert "customer intake pipeline" not in dossier
