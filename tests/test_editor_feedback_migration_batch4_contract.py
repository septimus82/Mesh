from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from engine.editor.editor_actions_parts import debug_actions, hd2d_actions

pytestmark = [pytest.mark.fast]


class _Feedback:
    def __init__(self) -> None:
        self.emissions = []

    def info(self, message: str, *, ttl: float | None = None) -> None:
        self.emissions.append(("info", str(message), ttl))

    def warning(self, message: str, *, ttl: float | None = None) -> None:
        self.emissions.append(("warning", str(message), ttl))

    def error(self, message: str, *, ttl: float | None = None, sticky: bool = False) -> None:  # noqa: ARG002
        self.emissions.append(("error", str(message), ttl))


def _window(editor: object | None = None) -> NS:
    return NS(editor_controller=editor, player_hud=NS(calls=[], enqueue_toast=lambda msg, **kw: None))


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ("info", "Debug bundle exported: out.json", None)),
        ({"severity": "warning", "seconds": 2.5}, ("warning", "Debug bundle exported: out.json", 2.5)),
        ({"severity": "error", "seconds": 2.5}, ("error", "Debug bundle exported: out.json", 2.5)),
    ],
)
def test_debug_toast_routes_default_warning_and_error(kwargs, expected) -> None:
    editor = NS(feedback=_Feedback())
    debug_actions._debug_toast(_window(editor), "Debug bundle exported: out.json", **kwargs)
    assert editor.feedback.emissions == [expected]


def test_debug_toast_falls_back_to_hud_without_feedback() -> None:
    calls = []
    window = NS(player_hud=NS(enqueue_toast=lambda msg, **kw: calls.append((msg, kw))))
    debug_actions._debug_toast(window, "No events to copy", severity="warning", seconds=2.5)
    assert calls == [("No events to copy", {"seconds": 2.5})]


@pytest.mark.parametrize(
    ("method_name", "message"),
    [
        ("get_selected_quest_diagnostic_text", "No quest diagnostic selected"),
        ("get_filtered_event_rows_text", "No events to copy"),
        ("get_cutscene_summary_text", "No cutscene summary available"),
    ],
)
def test_debug_empty_copy_actions_emit_warning_feedback(method_name, message) -> None:
    panel = NS(
        get_selected_quest_diagnostic_text=lambda: "",
        get_filtered_event_rows_text=lambda: "",
        get_cutscene_summary_text=lambda: "",
    )
    setattr(panel, method_name, lambda: "")
    editor = NS(active=True, feedback=_Feedback(), debug_panels=panel)
    action = {
        "get_selected_quest_diagnostic_text": debug_actions._action_debug_copy_quest_diagnostic,
        "get_filtered_event_rows_text": debug_actions._action_debug_copy_filtered_events,
        "get_cutscene_summary_text": debug_actions._action_debug_copy_cutscene_summary,
    }[method_name]
    action(_window(editor))
    assert editor.feedback.emissions == [("warning", message, None)]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ("info", "Radius: 96px", None)),
        ({"severity": "warning", "ttl": 2.5}, ("warning", "Radius: 96px", 2.5)),
    ],
)
def test_hd2d_emit_feedback_routes_default_and_explicit_severity(kwargs, expected) -> None:
    editor = NS(feedback=_Feedback())
    hd2d_actions._emit_feedback(_window(editor), "Radius: 96px", **kwargs)
    assert editor.feedback.emissions == [expected]


def test_hd2d_emit_feedback_falls_back_to_hud_without_feedback() -> None:
    calls = []
    window = NS(player_hud=NS(enqueue_toast=lambda msg, **kw: calls.append((msg, kw))))
    hd2d_actions._emit_feedback(window, "Nothing to paste", severity="warning", ttl=2.5)
    assert calls == [("Nothing to paste", {"seconds": 2.5})]


def _hd_window(editor: NS, scene: dict | None = None) -> NS:
    return NS(editor_controller=editor, scene_controller=NS(_loaded_scene_data=scene or {}))


def test_hd2d_copy_overrides_empty_patch_emits_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.editor.editor_selection_model.selected_entity_id", lambda _editor: "e1")
    monkeypatch.setattr("engine.editor.hd2d_controller_helpers_model.compute_clipboard_patch_from_entity", lambda _entity: {})
    monkeypatch.setattr("engine.editor.hd2d_controller_helpers_model.count_clipboard_patch_fields", lambda _patch: 0)
    editor = NS(active=True, feedback=_Feedback())
    scene = {"entities": {"e1": {"id": "e1"}}}
    hd2d_actions._copy_entity_hd2d_overrides(_hd_window(editor, scene))
    assert editor.feedback.emissions == [("info", "Copied HD-2D overrides · e1 (empty)", None)]


def test_hd2d_paste_without_clipboard_emits_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.editor.editor_selection_model.selected_entity_id", lambda _editor: "e1")
    monkeypatch.setattr("engine.editor.hd2d_controller_helpers_model.validate_clipboard_patch", lambda _patch: False)
    editor = NS(active=True, feedback=_Feedback(), _hd2d_overrides_clipboard=None)
    hd2d_actions._paste_entity_hd2d_overrides(_hd_window(editor))
    assert editor.feedback.emissions == [("warning", "Nothing to paste", None)]


def test_hd2d_clear_without_overrides_emits_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.editor.editor_selection_model.selected_entity_id", lambda _editor: "e1")
    monkeypatch.setattr("engine.editor.hd2d_entity_overrides_model.has_any_override", lambda _entity: False)
    editor = NS(active=True, feedback=_Feedback())
    scene = {"entities": {"e1": {"id": "e1"}}}
    hd2d_actions._clear_all_entity_hd2d_overrides(_hd_window(editor, scene))
    assert editor.feedback.emissions == [("warning", "No overrides to clear", None)]


def test_hd2d_batch_no_targets_emits_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.editor.editor_selection_model.selected_entity_id", lambda _editor: "e1")
    monkeypatch.setattr("engine.editor.hd2d_controller_helpers_model.validate_clipboard_patch", lambda _patch: True)
    monkeypatch.setattr("engine.editor.hd2d_override_batch_apply_model.compute_batch_apply_targets", lambda *a, **k: [])
    editor = NS(active=True, feedback=_Feedback(), _hd2d_overrides_clipboard={"x": 1})
    hd2d_actions._batch_paste_hd2d_overrides(_hd_window(editor, {"entities": {"e1": {}}}))
    assert editor.feedback.emissions == [("warning", "No entities in range", None)]


def test_hd2d_radius_adjustment_emits_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.editor.hd2d_controller_helpers_model.compute_next_batch_radius", lambda _cur, _delta: 112)
    monkeypatch.setattr("engine.editor.hd2d_controller_helpers_model.format_batch_radius_display", lambda radius: f"Radius: {radius}px")
    monkeypatch.setattr(hd2d_actions, "_save_hd2d_batch_radius_to_workspace", lambda _window, _radius: None)
    editor = NS(active=True, feedback=_Feedback(), _hd2d_batch_radius_px=96)
    hd2d_actions._adjust_hd2d_batch_radius(_window(editor), 16)
    assert editor.feedback.emissions == [("info", "Radius: 112px", None)]
