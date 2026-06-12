"""Contract tests for case-only rename safety in EditorFileOpsController."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor.editor_file_ops_controller import (
    EditorFileOpsController,
    compute_temp_rename_rel,
    is_case_only_rename,
)


@dataclass
class _Entry:
    rel_path: str
    is_dir: bool = False


class _ProjectExplorer:
    def __init__(self, entry: _Entry) -> None:
        self._row = SimpleNamespace(entry=entry)

    def get_selected_row(self) -> object:
        return self._row

    def refresh_tree(self) -> None:
        pass


class _Window:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.scene_controller = SimpleNamespace(_loaded_scene_data={"entities": []})
        self.player_hud = SimpleNamespace(enqueue_toast=lambda *args, **kwargs: None)


class _Controller:
    def __init__(self, repo_root: Path, entry: _Entry) -> None:
        self.window = _Window(repo_root)
        self.project_explorer = _ProjectExplorer(entry)

    def _push_command(self, _payload: dict) -> None:
        pass


def _make_controller(tmp_path: Path, rel_path: str) -> EditorFileOpsController:
    entry = _Entry(rel_path=rel_path)
    controller = _Controller(tmp_path, entry)
    return EditorFileOpsController(controller)


def _recording_replace(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def _wrapped(src: str | Path, dst: str | Path) -> None:
        calls.append((Path(src), Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr("engine.editor.editor_file_ops_controller.os.replace", _wrapped)
    return calls


def test_case_only_rename_uses_two_step_and_final_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    old_rel = "Foo.txt"
    new_name = "foo.txt"
    old_abs = tmp_path / old_rel
    old_abs.write_text("hello", encoding="utf-8")

    calls = _recording_replace(monkeypatch)
    ops = _make_controller(tmp_path, old_rel)

    # Act
    assert ops.rename_selected_asset(new_name) is True

    # Assert
    new_abs = tmp_path / new_name
    assert new_abs.exists()
    # Ensure directory entries reflect new name (case-sensitive safe)
    entries = set(os.listdir(tmp_path))
    assert new_name in entries
    assert old_rel not in entries
    assert len(calls) == 2
    assert calls[1][1] == new_abs


def test_case_only_temp_name_is_deterministic_and_collision_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old_rel = "Foo.txt"
    new_name = "foo.txt"
    old_abs = tmp_path / old_rel
    old_abs.write_text("hello", encoding="utf-8")

    # Create a colliding temp file
    temp_rel = compute_temp_rename_rel(old_rel, tmp_path)
    (tmp_path / temp_rel).write_text("collision", encoding="utf-8")

    calls = _recording_replace(monkeypatch)
    ops = _make_controller(tmp_path, old_rel)

    assert ops.rename_selected_asset(new_name) is True

    # Ensure a different temp name was used (collision resolved)
    assert len(calls) == 2
    assert calls[0][1].name != Path(temp_rel).name


def test_non_case_only_rename_still_single_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old_rel = "Foo.txt"
    new_name = "Bar.txt"
    old_abs = tmp_path / old_rel
    old_abs.write_text("hello", encoding="utf-8")

    calls = _recording_replace(monkeypatch)
    ops = _make_controller(tmp_path, old_rel)

    assert ops.rename_selected_asset(new_name) is True

    assert len(calls) == 1
    assert (tmp_path / new_name).exists()
    assert not old_abs.exists()


def test_is_case_only_rename() -> None:
    assert is_case_only_rename("Foo.txt", "foo.txt") is True
    assert is_case_only_rename("Foo.txt", "Foo.txt") is False
    assert is_case_only_rename("Foo.txt", "Bar.txt") is False
