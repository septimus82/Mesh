"""Contract tests for scene_lint_model."""

from __future__ import annotations

from pathlib import Path

from engine.editor.scene_lint_model import (
    build_scene_lint_issues,
    build_problems_panel_lines,
    clamp_issue_index,
    filter_lint_issues,
)


def test_build_scene_lint_issues_detects_and_sorts(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "ok.png").write_text("ok", encoding="utf-8")

    scene = {
        "id": "scene_1",
        "entities": [
            {"id": "dup", "sprite": "assets/missing.png"},
            {"id": "dup", "x": float("nan"), "prefab_id": "bad_prefab"},
            {"entity_id": "", "sprite": "assets/ok.png"},
        ],
    }

    issues = build_scene_lint_issues(
        scene,
        tmp_path,
        prefab_resolver=lambda pid: pid == "ok_prefab",
    )

    assert [issue.kind for issue in issues] == [
        "DUPLICATE_ID",
        "MISSING_ID",
        "INVALID_PREFAB_REF",
        "INVALID_TRANSFORM",
        "MISSING_ASSET",
    ]

    dup_issue = issues[0]
    renames = dup_issue.meta.get("renames", [])
    assert isinstance(renames, list)
    assert renames[0]["after"] == "dup_fix_1"

    missing_issue = issues[1]
    assert missing_issue.meta.get("after") == "entity_1"


def test_filter_lint_issues_matches_message() -> None:
    scene = {"entities": [{"id": "alpha"}, {"id": "alpha"}]}
    issues = build_scene_lint_issues(scene, Path("."), prefab_resolver=lambda _: True)
    filtered = filter_lint_issues(issues, "duplicate")
    assert [issue.kind for issue in filtered] == ["DUPLICATE_ID"]


def test_clamp_issue_index() -> None:
    assert clamp_issue_index(0, 0) == -1
    assert clamp_issue_index(-5, 3) == 0
    assert clamp_issue_index(10, 3) == 2


def test_build_problems_panel_lines_ascii() -> None:
    scene = {"entities": [{"id": "dup"}, {"id": "dup"}]}
    issues = build_scene_lint_issues(scene, Path("."), prefab_resolver=lambda _: True)
    lines = build_problems_panel_lines(True, "dup", issues, 0)
    assert lines
    assert all(line.isascii() for line in lines)
    assert any("[SAFE]" in line for line in lines)
