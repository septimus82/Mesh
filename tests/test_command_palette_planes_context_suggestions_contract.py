from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.command_palette_preview import build_arg_suggestions
from engine.ui_overlays.providers import command_palette_provider

pytestmark = pytest.mark.fast


def test_planes_move_to_suggestions_without_context_unchanged() -> None:
    suggestions = build_arg_suggestions("planes.move_to", "")
    assert suggestions == ["top", "bottom", "last", "0", "1", "2", "index=0", "index=1", "index=2"]


def test_planes_move_to_suggestions_with_context_add_indices_deterministically() -> None:
    suggestions = build_arg_suggestions("planes.move_to", "", context={"plane_count": 6})
    assert suggestions == [
        "top",
        "bottom",
        "last",
        "0",
        "1",
        "2",
        "index=0",
        "index=1",
        "index=2",
        "index=3",
        "index=4",
        "index=5",
    ]


def test_planes_move_to_suggestions_with_context_falls_back_to_plane_ids_count() -> None:
    suggestions = build_arg_suggestions(
        "planes.move_to",
        "index=",
        context={"plane_ids": [f"plane_{i:03d}" for i in range(20)]},
    )
    assert suggestions == [f"index={i}" for i in range(10)]


def test_provider_passes_planes_context_to_suggestions(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, object] | None] = []

    def _fake_build_arg_suggestions(command_id: str, raw_arg: str, context=None):  # type: ignore[no-untyped-def]
        if command_id == "planes.move_to":
            captured.append(context)
        return ["top", "bottom", "last"]

    monkeypatch.setattr("engine.command_palette_preview.build_arg_suggestions", _fake_build_arg_suggestions)

    window = SimpleNamespace(
        show_debug=True,
        command_palette_enabled=True,
        command_palette_query="",
        command_palette_index=0,
        command_palette_prompt_active=True,
        command_palette_prompt_text="",
        command_palette_prompt_kind="text",
        command_palette_prompt_query="",
        command_palette_prompt_index=0,
        command_palette_prompt_placeholder="top / bottom / last / index",
        command_palette_prompt_title="Planes: Move To...",
        command_palette_prompt_command_id="planes.move_to",
        command_palette_prompt_steps=(),
        command_palette_prompt_step_index=0,
        scene_dirty=False,
        scene_dirty_counter=0,
        scene_persist_armed=False,
        undo_stack=[],
        redo_stack=[],
        capture_state=None,
        entity_paint_state=None,
        tile_paint_state=None,
        scene_controller=SimpleNamespace(
            _loaded_scene_data={
                "background_planes": [
                    {"id": "plane_003"},
                    {"id": "plane_001"},
                    {"id": "plane_002"},
                ]
            }
        ),
        background_plane_editor_state=SimpleNamespace(selected_plane_id="plane_002"),
    )

    payload = command_palette_provider(window)
    assert payload.get("prompt_rows") == [
        {"value": "top", "label": "top"},
        {"value": "bottom", "label": "bottom"},
        {"value": "last", "label": "last"},
    ]
    assert len(captured) == 1
    assert captured[0] == {
        "plane_count": 3,
        "plane_ids": ["plane_001", "plane_002", "plane_003"],
        "selected_plane_id": "plane_002",
    }
