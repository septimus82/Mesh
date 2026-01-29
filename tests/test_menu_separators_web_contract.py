"""Contract tests for menu separator behavior on web runtime."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.editor import menu_bar_model


def _build_groups() -> list[menu_bar_model.MenuGroup]:
    controller = MagicMock()
    controller.selected_entity = None
    controller.undo_stack = []
    controller.redo_stack = []
    controller.scene_dirty = False
    window = MagicMock()
    return menu_bar_model.build_menu_groups(controller, window)


def _group_labels(groups: list[menu_bar_model.MenuGroup], title: str) -> list[str]:
    group = next(g for g in groups if g.title == title)
    return [item.label for item in group.items]


def _group_ids(groups: list[menu_bar_model.MenuGroup], title: str) -> list[str]:
    group = next(g for g in groups if g.title == title)
    return [item.id for item in group.items]


def test_web_file_menu_no_trailing_separator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYGBAG", "1")
    labels = _group_labels(_build_groups(), "File")
    assert labels
    assert labels[-1] != "-"


def test_web_file_menu_no_separator_when_only_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYGBAG", "1")
    labels = _group_labels(_build_groups(), "File")
    assert labels.count("-") == 0


def test_web_no_double_separators_with_suppressed_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYGBAG", "1")
    custom = dict(menu_bar_model.MENU_ACTION_ORDER)
    custom["View"] = (
        "editor.entity_panels.toggle",
        "|",
        "app.export_web_demo",
        "|",
        "editor.ghost_originals.toggle",
    )
    monkeypatch.setattr(menu_bar_model, "MENU_ACTION_ORDER", custom)
    labels = _group_labels(_build_groups(), "View")
    for idx in range(1, len(labels)):
        assert not (labels[idx - 1] == "-" and labels[idx] == "-")
    assert labels.count("-") == 1


def test_non_web_separators_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYGBAG", raising=False)
    ids = _group_ids(_build_groups(), "File")
    separators = [item_id for item_id in ids if "separator" in item_id]
    assert len(separators) == 2
