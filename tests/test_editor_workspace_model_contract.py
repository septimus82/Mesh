"""Contract tests for editor_workspace_model."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from engine.editor.editor_workspace_model import (
    WorkspaceSnapshot,
    apply_loaded_payload,
    build_save_payload,
    compute_workspace_paths,
    merge_user_settings,
    normalize_project_path,
    resolve_settings_precedence,
    update_recent_projects,
)
from engine.workspace_settings import WorkspaceSettings


def test_compute_workspace_paths_web_returns_none_paths() -> None:
    paths = compute_workspace_paths("C:/repo", platform="win32", is_web=True)
    assert paths.workspace_path is None
    assert paths.projects_path is None
    assert paths.user_settings_path is None


def test_compute_workspace_paths_native_returns_expected_files() -> None:
    root = Path("C:/repo")
    paths = compute_workspace_paths(root, platform="win32", is_web=False)
    assert paths.workspace_path == root / "workspace.json"
    assert paths.projects_path == root / "projects.json"
    assert paths.user_settings_path == root / "user_settings.json"


def test_resolve_settings_precedence_merges_in_order() -> None:
    defaults = {"a": 1, "b": 2}
    project = {"b": 3}
    workspace = {"c": 4}
    user = {"a": 9}
    resolved = resolve_settings_precedence(defaults, project, workspace, user)
    assert resolved == {"a": 9, "b": 3, "c": 4}


def test_build_save_payload_matches_asdict() -> None:
    settings = WorkspaceSettings(entity_panels_open=True, outliner_focus="inspector")
    snapshot = WorkspaceSnapshot(settings=settings)
    payload = build_save_payload(snapshot)
    assert payload == asdict(settings)


def test_apply_loaded_payload_uses_workspace_settings_from_dict() -> None:
    current = WorkspaceSnapshot(settings=WorkspaceSettings())
    payload = {"entity_panels_open": True, "outliner_focus": "inspector"}
    updated = apply_loaded_payload(current, payload)
    assert updated.settings.entity_panels_open is True
    assert updated.settings.outliner_focus == "inspector"


def test_normalize_project_path_trims_and_normalizes() -> None:
    assert normalize_project_path(" ") == ""
    assert normalize_project_path("C:/tmp") != ""


def test_update_recent_projects_dedupes_and_truncates() -> None:
    current = ["a", "b", "c"]
    updated = update_recent_projects(current, "b", now_iso="2024-01-01", max_entries=3)
    assert updated == ["b", "a", "c"]
    limited = update_recent_projects(updated, "d", now_iso="2024-01-01", max_entries=2)
    assert limited == ["d", "b"]


def test_merge_user_settings_precedence() -> None:
    defaults = {"a": 1, "b": 2}
    project = {"b": 3}
    workspace = {"c": 4}
    user = {"a": 9}
    merged = merge_user_settings(defaults, user, workspace, project)
    assert merged == {"a": 9, "b": 3, "c": 4}
