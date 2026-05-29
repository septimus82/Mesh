from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_item_editor_controller import EditorItemEditorController

pytestmark = [pytest.mark.fast]


def _editor(tmp_path: Path, overlay: object | None = None) -> SimpleNamespace:
    feedback_calls: list[tuple[str, str]] = []
    editor = SimpleNamespace(
        window=SimpleNamespace(item_editor_overlay=overlay),
        feedback=SimpleNamespace(
            error=lambda message: feedback_calls.append(("error", str(message))),
            info=lambda message: feedback_calls.append(("info", str(message))),
        ),
        _get_repo_root=lambda: tmp_path,
        feedback_calls=feedback_calls,
    )
    return editor


def _item(item_id: str = "healing_potion") -> dict[str, object]:
    return {
        "id": item_id,
        "name": "Healing Potion",
        "description": "Restores HP.",
        "icon": None,
        "stackable": True,
        "max_stack": 5,
        "tags": ["consumable"],
        "effects": {"heal": 25},
    }


def test_item_editor_controller_enter_cancel_and_dirty(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))

    controller.enter_edit_mode(_item())
    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() == "id"
    assert controller.is_dirty() is False

    assert controller.handle_item_editor_text_input("_x") is True
    assert controller.is_dirty() is True

    controller.cancel_edit_mode()
    assert controller.is_edit_mode_active() is False
    assert controller.is_dirty() is False
    assert controller.last_error_message() is None


def test_item_editor_controller_enter_unfocuses_without_saving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[object] = []
    from engine.editor import item_editor_model

    monkeypatch.setattr(item_editor_model, "save_items", lambda *args, **kwargs: saved.append((args, kwargs)))
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())

    assert controller.handle_item_editor_key(optional_arcade.arcade.key.ENTER, 0) is True

    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() is None
    assert saved == []


def test_item_editor_controller_escape_cancels_edit_mode(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())

    assert controller.handle_item_editor_key(optional_arcade.arcade.key.ESCAPE, 0) is True

    assert controller.is_edit_mode_active() is False


def test_item_editor_controller_commit_save_replaces_original_item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import item_editor_model

    def _save(items: list[dict[str, object]], target: Path) -> None:
        saved.append((items, target))

    monkeypatch.setattr(item_editor_model, "save_items", _save)
    editor = _editor(tmp_path)
    controller = EditorItemEditorController(editor)
    controller.enter_edit_mode(_item("old_id"))
    controller.id_input().text = "new_id"

    ok = controller.commit_save([_item("old_id"), _item("other")], tmp_path / "assets" / "data" / "items.json")

    assert ok is True
    assert controller.is_edit_mode_active() is False
    assert saved[0][0][0]["id"] == "new_id"
    assert saved[0][0][1]["id"] == "other"
    assert editor.feedback_calls[-1] == ("info", "Item saved")


def test_item_editor_controller_commit_save_reports_validation_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[object] = []
    from engine.editor import item_editor_model

    monkeypatch.setattr(item_editor_model, "save_items", lambda *args, **kwargs: saved.append((args, kwargs)))
    editor = _editor(tmp_path)
    controller = EditorItemEditorController(editor)
    controller.enter_edit_mode(_item("old_id"))
    controller.id_input().text = ""

    ok = controller.commit_save([_item("old_id")], tmp_path / "assets" / "data" / "items.json")

    assert ok is False
    assert controller.last_error_message() == "id is required"
    assert editor.feedback_calls[-1] == ("error", "id is required")
    assert saved == []


def test_item_editor_controller_tab_switch_keeps_edit_buffer(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())
    controller.handle_item_editor_text_input("_draft")

    assert controller.is_edit_mode_active() is True
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["id"] == "healing_potion_draft"


def test_item_editor_controller_focus_cycle_forward_wraps(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())

    assert controller.focused_field() == "id"
    for expected in ("name", "description", "icon", "max_stack", "id"):
        controller.cycle_focus_forward()
        assert controller.focused_field() == expected
        assert controller.text_input(expected).focused is True


def test_item_editor_controller_focus_cycle_backward_wraps(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())

    controller.cycle_focus_backward()

    assert controller.focused_field() == "max_stack"
    assert controller.text_input("max_stack").focused is True


def test_item_editor_controller_focus_cycle_noops_when_not_editing(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))

    controller.cycle_focus_forward()
    controller.cycle_focus_backward()

    assert controller.focused_field() is None


def test_item_editor_controller_focus_cycle_noops_for_non_cycle_focus(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())
    controller._focused_field = "stackable"

    controller.cycle_focus_forward()

    assert controller.focused_field() == "stackable"


def test_item_editor_controller_text_input_updates_current_focused_field(tmp_path: Path) -> None:
    controller = EditorItemEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_item())
    controller.cycle_focus_forward()

    assert controller.handle_item_editor_text_input(" X") is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["name"] == "Healing Potion X"


def test_item_editor_controller_view_mode_row_click_selects(tmp_path: Path) -> None:
    selected: list[int] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: 1,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorItemEditorController(_editor(tmp_path, overlay))

    assert controller.handle_item_editor_mouse_click(10.0, 10.0) is True

    assert selected == [1]
    assert controller.is_edit_mode_active() is False


def test_item_editor_controller_view_mode_row_miss_keeps_edit_button_working(tmp_path: Path) -> None:
    from engine.ui_overlays.widgets import Rect

    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        selected_item_dict=lambda: _item("old_id"),
    )
    controller = EditorItemEditorController(_editor(tmp_path, overlay))
    controller.set_button_rects({"edit": Rect(0.0, 0.0, 20.0, 20.0)})

    assert controller.handle_item_editor_mouse_click(10.0, 10.0) is True

    assert controller.is_edit_mode_active() is True


def test_item_editor_controller_edit_mode_skips_row_selection(tmp_path: Path) -> None:
    from engine.ui_overlays.widgets import Rect

    selected: list[int] = []
    row_hit_calls: list[tuple[float, float]] = []

    def _row_index_at(x: float, y: float) -> int:
        row_hit_calls.append((x, y))
        return 1

    overlay = SimpleNamespace(
        row_index_at=_row_index_at,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorItemEditorController(_editor(tmp_path, overlay))
    controller.enter_edit_mode(_item("old_id"))
    controller.set_button_rects({"cancel": Rect(0.0, 0.0, 20.0, 20.0)})

    assert controller.handle_item_editor_mouse_click(10.0, 10.0) is True

    assert selected == []
    assert row_hit_calls == []
    assert controller.is_edit_mode_active() is False


def test_item_editor_controller_empty_view_mode_click_falls_through(tmp_path: Path) -> None:
    selected: list[int] = []
    overlay = SimpleNamespace(
        row_index_at=lambda _x, _y: None,
        set_selected_index=lambda index: selected.append(index) or True,
    )
    controller = EditorItemEditorController(_editor(tmp_path, overlay))

    assert controller.handle_item_editor_mouse_click(10.0, 10.0) is False

    assert selected == []
    assert controller.is_edit_mode_active() is False
