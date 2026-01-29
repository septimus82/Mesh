"""Contract tests for project_explorer_model."""

from __future__ import annotations

from pathlib import Path

from engine.editor.project_explorer_model import (
    ProjectRow,
    activation_intent_for_row,
    filter_project_rows,
    scan_project_tree,
)


def test_scan_excludes_hidden_and_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "packs" / "core" / "scenes").mkdir(parents=True)
    (tmp_path / "packs" / ".hidden").mkdir(parents=True)
    (tmp_path / "assets" / "__pycache__").mkdir(parents=True)
    (tmp_path / "assets" / "props").mkdir(parents=True)
    (tmp_path / "assets" / "props" / "tree.png").write_text("x", encoding="utf-8")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    rows = scan_project_tree(tmp_path)
    rel_paths = [row.rel_path for row in rows]

    assert "packs" in rel_paths
    assert "assets" in rel_paths
    assert "config.json" in rel_paths
    assert all(".hidden" not in path for path in rel_paths)
    assert all("__pycache__" not in path for path in rel_paths)


def test_scan_ordering_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "assets" / "b_dir").mkdir(parents=True)
    (tmp_path / "assets" / "a_dir").mkdir(parents=True)
    (tmp_path / "assets" / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "assets" / "a.txt").write_text("a", encoding="utf-8")

    rows = scan_project_tree(tmp_path)
    rel_paths = [row.rel_path for row in rows]

    assert rel_paths.index("assets/a_dir") < rel_paths.index("assets/b_dir")
    assert rel_paths.index("assets/a.txt") > rel_paths.index("assets/b_dir")
    assert rel_paths.index("assets/b.txt") > rel_paths.index("assets/b_dir")


def test_filter_keeps_parents() -> None:
    rows = [
        ProjectRow(rel_path="assets", name="assets", depth=0, is_dir=True),
        ProjectRow(rel_path="assets/props", name="props", depth=1, is_dir=True),
        ProjectRow(rel_path="assets/props/tree.png", name="tree.png", depth=2, is_dir=False),
        ProjectRow(rel_path="assets/props/rock.png", name="rock.png", depth=2, is_dir=False),
    ]
    filtered = filter_project_rows(rows, "tree")
    rel_paths = [row.rel_path for row in filtered]
    # Matched rows come first (ranked), then parent folders
    assert rel_paths == ["assets/props/tree.png", "assets", "assets/props"]


def test_activation_intents() -> None:
    scene_row = ProjectRow(
        rel_path="packs/core/scenes/demo.json",
        name="demo.json",
        depth=2,
        is_dir=False,
    )
    asset_row = ProjectRow(
        rel_path="assets/props/tree.png",
        name="tree.png",
        depth=2,
        is_dir=False,
    )
    other_row = ProjectRow(
        rel_path="config.json",
        name="config.json",
        depth=0,
        is_dir=False,
    )
    dir_row = ProjectRow(
        rel_path="assets",
        name="assets",
        depth=0,
        is_dir=True,
    )

    assert activation_intent_for_row(scene_row)["kind"] == "open_scene"
    assert activation_intent_for_row(asset_row)["kind"] == "spawn_asset"
    assert activation_intent_for_row(other_row)["kind"] == "copy_path"
    assert activation_intent_for_row(dir_row)["kind"] == "none"
