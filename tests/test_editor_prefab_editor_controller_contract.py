from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_prefab_editor_controller import EditorPrefabEditorController, _get_path, _set_path

pytestmark = [pytest.mark.fast]


def _editor(tmp_path: Path, overlay: object | None = None) -> SimpleNamespace:
    feedback_calls: list[tuple[str, str]] = []
    editor = SimpleNamespace(
        window=SimpleNamespace(prefab_editor_overlay=overlay),
        feedback=SimpleNamespace(
            error=lambda message: feedback_calls.append(("error", str(message))),
            info=lambda message: feedback_calls.append(("info", str(message))),
        ),
        _get_repo_root=lambda: tmp_path,
        feedback_calls=feedback_calls,
    )
    return editor


def _prefab(prefab_id: str = "torch_wisp") -> dict[str, object]:
    return {
        "id": prefab_id,
        "display_name": "Torch Wisp",
        "entity": {
            "sprite": "assets/placeholder.png",
            "encounter_cost": 2,
            "behaviours": ["EnemyAI"],
        },
        "tags": ["enemy"],
        "metadata": {"author": "core"},
    }


def test_prefab_editor_controller_enter_cancel_and_dirty(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))

    controller.enter_edit_mode(_prefab())
    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() == "id"
    assert controller.is_dirty() is False

    assert controller.handle_prefab_editor_text_input("_x") is True
    assert controller.is_dirty() is True

    controller.cancel_edit_mode()
    assert controller.is_edit_mode_active() is False
    assert controller.is_dirty() is False
    assert controller.last_error_message() is None


def test_prefab_editor_controller_deep_copies_edit_buffer(tmp_path: Path) -> None:
    source = _prefab()
    controller = EditorPrefabEditorController(_editor(tmp_path))

    controller.enter_edit_mode(source)
    assert controller.edit_buffer is not None
    assert isinstance(controller.edit_buffer["entity"], dict)
    controller.edit_buffer["entity"]["sprite"] = "assets/changed.png"

    assert source["entity"]["sprite"] == "assets/placeholder.png"


def test_prefab_editor_path_helpers_handle_nested_and_missing_paths() -> None:
    payload: dict[str, object] = {"id": "torch_wisp", "entity": {"sprite": "old.png"}}

    assert _get_path(payload, "id") == "torch_wisp"
    assert _get_path(payload, "entity.sprite") == "old.png"
    assert _get_path(payload, "entity.missing") is None
    assert _get_path({"entity": "not a dict"}, "entity.sprite") is None
    assert _get_path(payload, "") is None


def test_prefab_editor_path_helpers_create_and_replace_intermediate_dicts() -> None:
    payload: dict[str, object] = {}

    _set_path(payload, "id", "torch_wisp")
    _set_path(payload, "entity.sprite", "assets/placeholder.png")
    assert payload == {"id": "torch_wisp", "entity": {"sprite": "assets/placeholder.png"}}

    payload["entity"] = "not a dict"
    _set_path(payload, "entity.encounter_cost", "2")
    assert payload["entity"] == {"encounter_cost": "2"}

    _set_path(payload, "", "ignored")
    assert "" not in payload


def test_prefab_editor_controller_enter_unfocuses_without_saving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[object] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda *args, **kwargs: saved.append((args, kwargs)))
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller.handle_prefab_editor_key(optional_arcade.arcade.key.ENTER, 0) is True

    assert controller.is_edit_mode_active() is True
    assert controller.focused_field() is None
    assert saved == []


def test_prefab_editor_controller_escape_cancels_edit_mode(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller.handle_prefab_editor_key(optional_arcade.arcade.key.ESCAPE, 0) is True

    assert controller.is_edit_mode_active() is False


def test_prefab_editor_controller_commit_save_replaces_by_original_id_after_id_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[list[dict[str, object]], Path]] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])

    def _save(prefabs: list[dict[str, object]], target: Path) -> None:
        saved.append((prefabs, target))

    monkeypatch.setattr(prefab_editor_model, "save_prefabs", _save)
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab("old_id"))
    controller.id_input().text = "new_id"

    ok = controller.commit_save([_prefab("old_id"), _prefab("other")], tmp_path / "assets" / "prefabs.json")

    assert ok is True
    assert controller.is_edit_mode_active() is False
    assert saved[0][0][0]["id"] == "new_id"
    assert saved[0][0][1]["id"] == "other"
    assert editor.feedback_calls[-1] == ("info", "Prefab saved")


def test_prefab_editor_controller_commit_save_reports_validation_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[object] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: ["id is required"])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda *args, **kwargs: saved.append((args, kwargs)))
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab("old_id"))
    controller.id_input().text = ""

    ok = controller.commit_save([_prefab("old_id")], tmp_path / "assets" / "prefabs.json")

    assert ok is False
    assert controller.last_error_message() == "id is required"
    assert editor.feedback_calls[-1] == ("error", "id is required")
    assert saved == []


def test_prefab_editor_controller_tab_switch_keeps_edit_buffer(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())
    controller.handle_prefab_editor_text_input("_draft")

    assert controller.is_edit_mode_active() is True
    assert controller.edit_buffer is not None
    assert controller.edit_buffer["id"] == "torch_wisp_draft"


def test_prefab_editor_controller_focus_cycle_forward_backward_wraps(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())

    assert controller.focused_field() == "id"
    for expected in ("display_name", "entity.sprite", "entity.encounter_cost", "id"):
        controller.cycle_focus_forward()
        assert controller.focused_field() == expected
        assert controller.text_input(expected).focused is True

    controller.cycle_focus_backward()
    assert controller.focused_field() == "entity.encounter_cost"
    assert controller.text_input("entity.encounter_cost").focused is True


def test_prefab_editor_controller_focus_cycle_noops_when_not_editing(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))

    controller.cycle_focus_forward()
    controller.cycle_focus_backward()

    assert controller.focused_field() is None


def test_prefab_editor_controller_text_input_updates_nested_focused_field(tmp_path: Path) -> None:
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab())
    controller.cycle_focus_forward()
    controller.cycle_focus_forward()

    assert controller.focused_field() == "entity.sprite"
    assert controller.handle_prefab_editor_text_input("_x") is True

    assert controller.edit_buffer is not None
    assert controller.edit_buffer["entity"]["sprite"] == "assets/placeholder.png_x"


def test_prefab_editor_controller_commit_save_coerces_encounter_cost_int(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[list[dict[str, object]]] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda prefabs, _target: saved.append(prefabs))
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab("old_id"))
    controller.text_input("entity.encounter_cost").text = "7"

    assert controller.commit_save([_prefab("old_id")], tmp_path / "assets" / "prefabs.json") is True

    assert saved[0][0]["entity"]["encounter_cost"] == 7


def test_prefab_editor_controller_commit_save_removes_empty_encounter_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[list[dict[str, object]]] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda prefabs, _target: saved.append(prefabs))
    controller = EditorPrefabEditorController(_editor(tmp_path))
    controller.enter_edit_mode(_prefab("old_id"))
    controller.text_input("entity.encounter_cost").text = " "

    assert controller.commit_save([_prefab("old_id")], tmp_path / "assets" / "prefabs.json") is True

    assert "encounter_cost" not in saved[0][0]["entity"]


def test_prefab_editor_controller_commit_save_rejects_invalid_encounter_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[object] = []
    from engine.editor import prefab_editor_model

    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda *args, **kwargs: saved.append((args, kwargs)))
    editor = _editor(tmp_path)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab("old_id"))
    controller.text_input("entity.encounter_cost").text = "abc"

    ok = controller.commit_save([_prefab("old_id")], tmp_path / "assets" / "prefabs.json")

    assert ok is False
    assert controller.last_error_message() == "entity.encounter_cost must be an integer"
    assert editor.feedback_calls[-1] == ("error", "entity.encounter_cost must be an integer")
    assert saved == []


def test_prefab_editor_controller_uses_model_default_path_for_button_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[Path] = []
    from engine.editor import prefab_editor_model
    from engine.ui_overlays.widgets import Rect

    overlay = SimpleNamespace(
        selected_prefab_dict=lambda: _prefab("old_id"),
        all_prefab_dicts=lambda: [_prefab("old_id")],
        reload_model=lambda: None,
    )
    editor = _editor(tmp_path, overlay)
    controller = EditorPrefabEditorController(editor)
    controller.enter_edit_mode(_prefab("old_id"))
    controller.set_button_rects({"save": Rect(0.0, 0.0, 20.0, 20.0)})
    monkeypatch.setattr(prefab_editor_model, "validate_prefab_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(prefab_editor_model, "save_prefabs", lambda _prefabs, target: saved.append(target))

    assert controller.handle_prefab_editor_mouse_click(10.0, 10.0) is True

    assert saved == [tmp_path / prefab_editor_model.DEFAULT_PREFAB_FILE_PATH]
