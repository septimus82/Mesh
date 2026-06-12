from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from engine.editor.editor_asset_browser_controller import EditorAssetBrowserController
from engine.editor.editor_clipboard_controller import EditorClipboardController
from engine.editor.editor_lights_controller import EditorLightsController

pytestmark = [pytest.mark.fast]


class _Feedback:
    def __init__(self) -> None:
        self.emissions = []

    def info(self, message: str, *, ttl: float | None = None) -> None:
        self.emissions.append(("info", str(message), ttl))

    def warning(self, message: str, *, ttl: float | None = None) -> None:
        self.emissions.append(("warning", str(message), ttl))


def _editor(**attrs) -> NS:
    base = NS(active=True, feedback=_Feedback(), selected_entity=None, window=NS())
    base.__dict__.update(attrs)
    return base


def test_copy_selected_entity_emits_info_feedback() -> None:
    editor = _editor(selected_entity=NS(mesh_entity_data={"id": "src"}))
    EditorClipboardController(editor).copy_selected_entity()
    assert editor.feedback.emissions == [("info", "Copied: src", None)]


def test_paste_entity_empty_clipboard_emits_warning_feedback() -> None:
    editor = _editor()
    EditorClipboardController(editor).paste_entity()
    assert editor.feedback.emissions == [("warning", "Nothing to paste", None)]


def test_paste_entity_success_emits_info_feedback() -> None:
    editor = _editor(
        window=NS(scene_controller=NS(all_sprites=[]), camera_controller=NS(camera=NS(position=(5, 7)))),
        shape=NS(reset_zone_selection_state=lambda: None, sync_zone_selection_state=lambda _selected: None),
        _create_entity_internal=lambda _data: object(),
        _push_command=lambda _cmd: None,
    )
    clipboard = EditorClipboardController(editor)
    clipboard.entity_clipboard = {"id": "src"}
    clipboard.entity_clipboard_source_id = "src"
    clipboard.paste_entity()
    assert editor.feedback.emissions == [("info", "Pasted: src_copy_1", None)]

@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (NS(kind="image", display_name="test.png", rel_path="assets/test.png"), "Placement Mode: test.png"),
        (NS(kind="sound", display_name="sound.wav", rel_path="assets/sound.wav"), "Copied: assets/sound.wav"),
    ],
)
def test_asset_browser_activation_emits_info_feedback(row, expected) -> None:
    editor = NS(
        feedback=_Feedback(),
        window=NS(),
        _asset_browser_filtered_rows=[row],
        asset_browser_selection_index=0,
        asset_place_active=False,
        asset_place_path=None,
        asset_place_kind=None,
        asset_browser_active=True,
    )
    EditorAssetBrowserController(editor)._activate_selected_asset()
    assert editor.feedback.emissions == [("info", expected, None)]

def test_copy_find_asset_path_emits_info_feedback() -> None:
    editor = NS(feedback=_Feedback(), window=NS())
    assert EditorAssetBrowserController(editor)._copy_find_asset_path("config.json") is True
    assert editor.feedback.emissions == [("info", "Copied path: config.json", None)]

@pytest.mark.parametrize(
    ("method_name", "arg", "expected"),
    [
        ("apply_lighting_preset", "torch_cave", "Applied: torch_cave"),
        ("capture_lighting_preset", "custom_1", "Saved: custom_1"),
    ],
)
def test_lighting_preset_actions_emit_info_feedback_after_state_update(method_name, arg, expected) -> None:
    editor = _editor(
        window=NS(scene_controller=NS(_loaded_scene_data={"settings": {}})),
        lighting_preset_label=None,
        lighting_preset_until=0.0,
        _mark_dirty=lambda: None,
    )
    assert getattr(EditorLightsController(editor), method_name)(arg) is True
    assert editor.lighting_preset_label == expected
    assert editor.feedback.emissions == [("info", expected, 2.5)]
