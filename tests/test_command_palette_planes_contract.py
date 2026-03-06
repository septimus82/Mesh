from __future__ import annotations

import pytest

from engine.command_palette_preview import build_arg_preview, build_arg_suggestions

pytestmark = pytest.mark.fast


def test_planes_command_ids_present() -> None:
    from engine.command_palette import build_default_commands

    ids = [c.id for c in build_default_commands(object())]
    expected = {
        "planes.add",
        "planes.duplicate",
        "planes.remove",
        "planes.move_up",
        "planes.move_down",
        "planes.move_top",
        "planes.move_bottom",
        "planes.move_to",
        "planes.toggle_repeat",
        "planes.toggle_repeat_x",
        "planes.toggle_repeat_y",
        "planes.select",
        "planes.select_prev",
        "planes.select_next",
    }
    assert expected.issubset(set(ids))


def test_planes_suggestions_are_deterministic() -> None:
    first = build_arg_suggestions("planes.toggle_repeat", "")
    second = build_arg_suggestions("planes.toggle_repeat", "")
    assert first == second
    assert first[:3] == ["x", "y", "both"]


def test_planes_move_to_preview_and_suggestions() -> None:
    payload = build_arg_preview("planes.move_to", "last")
    assert payload == {"ok": True, "preview": "move plane: last", "error": None}
    suggestions = build_arg_suggestions("planes.move_to", "")
    assert suggestions[:6] == ["top", "bottom", "last", "0", "1", "2"]


def test_planes_select_preview_from_registry_parser_wrapper() -> None:
    payload = build_arg_preview("planes.select", "next")
    assert payload == {"ok": True, "preview": "select plane: next", "error": None}


def test_planes_action_handler_delegates_to_editor_action_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import command_palette_registry as registry
    from engine import command_palette_registry_actions as actions

    calls: list[str] = []

    def _fake_run_editor_action(_window: object, action_id: str) -> bool:
        calls.append(action_id)
        return True

    monkeypatch.setattr(actions, "_run_editor_action", _fake_run_editor_action)
    registry.action_planes_move_up(object(), None)
    assert calls == ["editor.background_planes.move_up"]


def test_planes_move_to_delegates_with_index(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from engine import command_palette_registry as registry
    from engine import command_palette_registry_actions as actions

    calls: list[str] = []

    def _fake_run_editor_action(_window: object, action_id: str) -> bool:
        calls.append(action_id)
        return True

    window = SimpleNamespace()
    monkeypatch.setattr(actions, "_run_editor_action", _fake_run_editor_action)
    registry.action_planes_move_to(window, "2")
    assert calls == ["editor.background_planes.move_to_index"]
    assert not hasattr(window, "command_palette_planes_move_to_index")
