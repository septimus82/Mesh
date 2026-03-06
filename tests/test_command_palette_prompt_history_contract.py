from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.command_palette_controller import (
    get_command_palette_prompt_history_entries,
    handle_command_palette_activate,
    handle_command_palette_history_navigate,
    handle_command_palette_navigate,
    handle_command_palette_prompt_text_changed,
)
from engine.input_runtime.capture_key_router_model import (
    SCOPE_COMMAND_PALETTE,
    build_route_table,
)

pytestmark = pytest.mark.fast


def _patch_commands(monkeypatch: pytest.MonkeyPatch, commands: list[SimpleNamespace]) -> None:
    import engine.command_palette as palette_mod

    monkeypatch.setattr(palette_mod, "build_default_commands", lambda _window: list(commands))


def _make_prompt_command(cmd_id: str, calls: list[str]) -> SimpleNamespace:
    prompt = SimpleNamespace(
        kind="text",
        placeholder="",
        default_value_fn=lambda _window: "",
    )

    def _action(_window: object, raw_arg: str | None) -> None:
        calls.append(str(raw_arg or ""))

    return SimpleNamespace(
        id=cmd_id,
        title=f"Command {cmd_id}",
        prompt=prompt,
        prompts=None,
        macro_id="",
        action=_action,
        is_enabled=lambda _window: (True, ""),
    )


def _run_prompt_execute(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cmd_id: str,
    raw_arg: str,
    calls: list[str],
    window: SimpleNamespace | None = None,
) -> SimpleNamespace:
    if window is None:
        window = SimpleNamespace()
    cmd = _make_prompt_command(cmd_id, calls)
    _patch_commands(monkeypatch, [cmd])

    window.show_debug = True
    window.command_palette_enabled = True
    window.command_palette_query = ""
    window.command_palette_index = 0
    window.command_palette_prompt_active = True
    window.command_palette_prompt_command_id = cmd_id
    window.command_palette_prompt_steps = ()
    window.command_palette_prompt_step_index = 0
    window.command_palette_prompt_values = {}
    window.command_palette_prompt_text = raw_arg
    window.command_palette_prompt_kind = "text"
    window.command_palette_prompt_index = 0
    window.command_palette_prompt_query = ""

    handled = handle_command_palette_activate(window, snapshot=SimpleNamespace(), repeat=False)
    assert handled is True
    return window


def test_prompt_history_push_on_execute_and_dedupe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    window = _run_prompt_execute(monkeypatch, cmd_id="hist.cmd", raw_arg="foo", calls=calls)
    assert calls == ["foo"]
    assert get_command_palette_prompt_history_entries(window, "hist.cmd") == ("foo",)

    _run_prompt_execute(
        monkeypatch,
        cmd_id="hist.cmd",
        raw_arg="foo",
        calls=calls,
        window=window,
    )
    assert get_command_palette_prompt_history_entries(window, "hist.cmd") == ("foo",)


def test_prompt_history_cycle_prev_next_with_scratch_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    window = _run_prompt_execute(monkeypatch, cmd_id="hist.cmd", raw_arg="one", calls=calls)
    _run_prompt_execute(monkeypatch, cmd_id="hist.cmd", raw_arg="two", calls=calls, window=window)

    window.command_palette_prompt_active = True
    window.command_palette_prompt_kind = "text"
    window.command_palette_prompt_command_id = "hist.cmd"
    window.command_palette_prompt_text = "scratch"
    window.command_palette_prompt_index = 0

    assert handle_command_palette_history_navigate(window, -1) is True
    assert window.command_palette_prompt_text == "two"
    assert handle_command_palette_history_navigate(window, -1) is True
    assert window.command_palette_prompt_text == "one"
    assert handle_command_palette_history_navigate(window, 1) is True
    assert window.command_palette_prompt_text == "two"
    assert handle_command_palette_history_navigate(window, 1) is True
    assert window.command_palette_prompt_text == "scratch"


def test_prompt_history_isolated_by_command_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    window = _run_prompt_execute(monkeypatch, cmd_id="cmd.a", raw_arg="arg-a", calls=calls)
    _run_prompt_execute(monkeypatch, cmd_id="cmd.b", raw_arg="arg-b", calls=calls, window=window)

    window.command_palette_prompt_active = True
    window.command_palette_prompt_kind = "text"
    window.command_palette_prompt_command_id = "cmd.a"
    window.command_palette_prompt_text = ""
    window.command_palette_prompt_index = 0
    assert handle_command_palette_history_navigate(window, -1) is True
    assert window.command_palette_prompt_text == "arg-a"

    window.command_palette_prompt_command_id = "cmd.b"
    window.command_palette_prompt_text = ""
    handle_command_palette_prompt_text_changed(window)
    assert handle_command_palette_history_navigate(window, -1) is True
    assert window.command_palette_prompt_text == "arg-b"


def test_prompt_history_typing_resets_browse_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    window = _run_prompt_execute(monkeypatch, cmd_id="hist.cmd", raw_arg="old", calls=calls)
    _run_prompt_execute(monkeypatch, cmd_id="hist.cmd", raw_arg="new", calls=calls, window=window)

    window.command_palette_prompt_active = True
    window.command_palette_prompt_kind = "text"
    window.command_palette_prompt_command_id = "hist.cmd"
    window.command_palette_prompt_text = "scratch"
    window.command_palette_prompt_index = 0

    assert handle_command_palette_history_navigate(window, -1) is True
    assert window.command_palette_prompt_text == "new"

    window.command_palette_prompt_text = "scratch+typed"
    handle_command_palette_prompt_text_changed(window)
    assert handle_command_palette_history_navigate(window, 1) is True
    assert window.command_palette_prompt_text == "scratch+typed"
    assert handle_command_palette_history_navigate(window, -1) is True
    assert window.command_palette_prompt_text == "new"


def test_suggestions_navigation_unchanged_with_history_support() -> None:
    window = SimpleNamespace(
        command_palette_prompt_active=True,
        command_palette_prompt_kind="text",
        command_palette_prompt_command_id="selection.align",
        command_palette_prompt_text="le",
        command_palette_prompt_index=0,
    )
    assert handle_command_palette_navigate(window, 1) is True
    assert int(window.command_palette_prompt_index) == 1

    prior_text = window.command_palette_prompt_text
    prior_index = int(window.command_palette_prompt_index)
    assert handle_command_palette_history_navigate(window, -1) is True
    assert window.command_palette_prompt_text == prior_text
    assert int(window.command_palette_prompt_index) == prior_index

    assert handle_command_palette_navigate(window, 1) is True
    assert int(window.command_palette_prompt_index) >= prior_index


def test_ctrl_up_down_routes_registered_for_command_palette_scope() -> None:
    key = optional_arcade.arcade.key
    routes = [r for r in build_route_table() if r.scope == SCOPE_COMMAND_PALETTE]
    prev = [
        r
        for r in routes
        if r.action_id == "capture.command_palette.history_prev"
        and int(r.combo.key) == int(key.UP)
        and int(r.combo.mods) == int(key.MOD_CTRL)
    ]
    nxt = [
        r
        for r in routes
        if r.action_id == "capture.command_palette.history_next"
        and int(r.combo.key) == int(key.DOWN)
        and int(r.combo.mods) == int(key.MOD_CTRL)
    ]
    assert prev
    assert nxt
