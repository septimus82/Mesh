"""Contract tests for scene_lint_ops."""

from __future__ import annotations

from pathlib import Path

from engine.editor.scene_lint_model import build_scene_lint_issues
from engine.editor.scene_lint_ops import (
    apply_all_safe_fixes,
    apply_fix_all,
    apply_fix_command,
    build_fix_command_for_issue,
    invert_fix_command,
)


def test_fix_duplicate_ids_is_deterministic(tmp_path: Path) -> None:
    scene = {
        "entities": [
            {"id": "dup"},
            {"id": "dup"},
            {"id": "dup_fix_1"},
        ]
    }
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    dup_issue = next(issue for issue in issues if issue.kind == "DUPLICATE_ID")
    cmd = build_fix_command_for_issue(scene, dup_issue, tmp_path)
    assert cmd is not None
    fixed = apply_fix_command(scene, cmd, tmp_path)

    entities = fixed.get("entities", [])
    assert entities[0]["id"] == "dup"
    assert entities[1]["id"] == "dup_fix_2"


def test_fix_missing_id_assigns_entity_n(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "ok"}, {"entity_id": ""}]}
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    missing = next(issue for issue in issues if issue.kind == "MISSING_ID")
    cmd = build_fix_command_for_issue(scene, missing, tmp_path)
    assert cmd is not None
    fixed = apply_fix_command(scene, cmd, tmp_path)
    assert fixed["entities"][1]["entity_id"] == "entity_1"


def test_clear_prefab_removes_overrides(tmp_path: Path) -> None:
    scene = {
        "entities": [
            {"id": "a", "prefab_id": "bad", "prefab_overrides": {"x": 1}},
        ]
    }
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: False)
    invalid = next(issue for issue in issues if issue.kind == "INVALID_PREFAB_REF")
    cmd = build_fix_command_for_issue(scene, invalid, tmp_path)
    assert cmd is not None
    fixed = apply_fix_command(scene, cmd, tmp_path)
    assert "prefab_id" not in fixed["entities"][0]
    assert "prefab_overrides" not in fixed["entities"][0]


def test_clear_asset_removes_asset_field(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "a", "sprite": "assets/missing.png"}]}
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    missing = next(issue for issue in issues if issue.kind == "MISSING_ASSET")
    cmd = build_fix_command_for_issue(scene, missing, tmp_path)
    assert cmd is not None
    fixed = apply_fix_command(scene, cmd, tmp_path)
    assert "sprite" not in fixed["entities"][0]


def test_sanitize_transform_clamps_invalid(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "a", "x": float("inf"), "scale": float("nan")}]}
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    invalid = next(issue for issue in issues if issue.kind == "INVALID_TRANSFORM")
    cmd = build_fix_command_for_issue(scene, invalid, tmp_path)
    assert cmd is not None
    fixed = apply_fix_command(scene, cmd, tmp_path)
    assert fixed["entities"][0]["x"] == 0.0
    assert fixed["entities"][0]["scale"] == 1.0


def test_apply_fix_is_idempotent(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "a", "sprite": "assets/missing.png"}]}
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    missing = next(issue for issue in issues if issue.kind == "MISSING_ASSET")
    cmd = build_fix_command_for_issue(scene, missing, tmp_path)
    assert cmd is not None
    first = apply_fix_command(scene, cmd, tmp_path)
    second = apply_fix_command(first, cmd, tmp_path)
    assert first == second


def test_fix_all_compound_command(tmp_path: Path) -> None:
    scene = {
        "entities": [
            {"id": "dup"},
            {"id": "dup"},
            {"entity_id": ""},
        ]
    }
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    fixed, cmd = apply_fix_all(scene, issues, tmp_path)
    assert cmd.commands
    assert len(cmd.commands) >= 2
    assert fixed["entities"][1]["id"].startswith("dup_fix_")
    assert fixed["entities"][2]["entity_id"].startswith("entity_")


def test_apply_all_safe_skips_risky(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "dup"}, {"id": "dup"}]}
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    safe_issue = next(issue for issue in issues if issue.kind == "DUPLICATE_ID")
    risky_issue = safe_issue.__class__(
        issue_id="risky",
        kind=safe_issue.kind,
        message=safe_issue.message,
        entity_id=safe_issue.entity_id,
        scene_id=safe_issue.scene_id,
        severity=safe_issue.severity,
        risk="risky",
        fix_kind=safe_issue.fix_kind,
        fixable=safe_issue.fixable,
        meta=safe_issue.meta,
    )
    new_scene, applied, skipped = apply_all_safe_fixes(scene, [risky_issue, safe_issue], tmp_path)
    assert applied == 1
    assert skipped == 1
    assert new_scene["entities"][1]["id"].startswith("dup_fix_")


def test_apply_all_safe_no_safe_fixes(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "dup"}, {"id": "dup"}]}
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    risky_issue = issues[0].__class__(
        issue_id="risky",
        kind=issues[0].kind,
        message=issues[0].message,
        entity_id=issues[0].entity_id,
        scene_id=issues[0].scene_id,
        severity=issues[0].severity,
        risk="risky",
        fix_kind=issues[0].fix_kind,
        fixable=issues[0].fixable,
        meta=issues[0].meta,
    )
    new_scene, applied, skipped = apply_all_safe_fixes(scene, [risky_issue], tmp_path)
    assert applied == 0
    assert skipped == 1
    assert new_scene == scene


def test_invert_fix_command_round_trip(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "a", "sprite": "assets/missing.png"}]}
    issues = build_scene_lint_issues(scene, tmp_path, prefab_resolver=lambda _: True)
    missing = next(issue for issue in issues if issue.kind == "MISSING_ASSET")
    cmd = build_fix_command_for_issue(scene, missing, tmp_path)
    assert cmd is not None
    fixed = apply_fix_command(scene, cmd, tmp_path)
    inverse = invert_fix_command(scene, cmd, fixed)
    restored = apply_fix_command(fixed, inverse, tmp_path)
    assert restored == scene
