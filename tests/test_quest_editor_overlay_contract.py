from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.editor.widgets.panel_primitives as panel_primitives
from engine.editor.quest_editor_model import QuestEditorModel
from engine.ui_overlays.quest_editor_overlay import (
    QUEST_EDITOR_READ_ONLY_COMPLEX_FIELDS,
    QuestEditorOverlay,
)
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


def _window_for_tab(right_tab: str) -> SimpleNamespace:
    controller = SimpleNamespace(active=True, dock=make_dock_stub(right_tab=right_tab))
    return SimpleNamespace(width=1280, height=720, editor_controller=controller)


def _quest_path(tmp_path: Path, quests: list[dict[str, object]] | None = None) -> Path:
    path = tmp_path / "assets" / "data" / "quests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "quests": quests
                if quests is not None
                else [
                    {
                        "id": "showcase_tour",
                        "title": "Tour of the Mesh",
                        "description": "Visit the demonstration rooms.",
                        "type": "tour",
                        "start_toast": "Tour started",
                        "complete_toast": "Tour complete",
                        "stages": [{"id": "intro", "title": "Talk", "text": "Talk to the guide."}],
                        "reward": {"inc_counters": {"developer_badge": 1}},
                        "requires_flags": ["intro_complete"],
                    },
                    {
                        "id": "test_quest",
                        "title": "Test Quest",
                        "steps": [],
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _model(tmp_path: Path, quests: list[dict[str, object]] | None = None) -> QuestEditorModel:
    return QuestEditorModel.load(_quest_path(tmp_path, quests))


def _capture_panel_text(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(panel_primitives, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "draw_text_cached", lambda text, *args, **kwargs: captured.append(str(text)))
    return captured


def test_quest_editor_overlay_constructs() -> None:
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))

    assert overlay is not None


def test_quest_editor_overlay_uses_layout_primitives() -> None:
    source = QuestEditorOverlay.draw.__code__.co_names

    assert "EditorPanelBase" in source
    assert "PanelRow" in source
    assert "PanelField" in source
    assert "PanelHeader" in source


def test_quest_editor_overlay_hides_when_right_tab_is_not_quests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Prefabs"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert captured == []


def test_quest_editor_overlay_renders_selected_quest_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Quests" in captured
    assert "Tour of the Mesh" in captured
    assert "showcase_tour" in captured
    assert "Test Quest" in captured
    assert "test_quest" in captured
    assert "ID" in captured
    assert "Title" in captured
    assert "Description" in captured
    assert "Visit the demonstration rooms." in captured
    assert "Type" in captured
    assert "tour" in captured
    assert "Start toast" in captured
    assert "Complete toast" in captured


def test_quest_editor_overlay_renders_complex_field_section(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Complex fields (read-only)" in captured
    assert "Stages" in captured
    assert any("Talk to the guide" in text for text in captured)
    assert "Reward" in captured
    assert '{"inc_counters":{"developer_badge":1}}' in captured
    assert "Requires flags" in captured
    assert "intro_complete" in captured


def test_quest_editor_overlay_documents_read_only_complex_fields() -> None:
    assert QUEST_EDITOR_READ_ONLY_COMPLEX_FIELDS == frozenset(
        {"stages", "steps", "reward", "requires_flags", "blocks_flags"}
    )


def test_quest_editor_overlay_renders_empty_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))
    overlay._model = _model(tmp_path, [])

    overlay.draw()

    assert "No quests found" in captured
    assert "No quest" in captured


def test_quest_editor_overlay_renders_load_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_panel_text(monkeypatch)

    from engine.editor import quest_editor_model

    monkeypatch.setattr(
        quest_editor_model.QuestEditorModel,
        "load",
        classmethod(lambda cls: (_ for _ in ()).throw(FileNotFoundError("missing quests.json"))),
    )
    overlay = QuestEditorOverlay(_window_for_tab("Quests"))

    overlay.draw()

    assert "Unable to load quests" in captured
    assert "missing quests.json" in captured
