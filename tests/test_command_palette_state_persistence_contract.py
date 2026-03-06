from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.command_palette_controller import (
    clear_command_palette_recent_commands,
    get_command_palette_prompt_history_entries,
    get_command_palette_recent_command_ids,
    handle_command_palette_activate,
    handle_command_palette_toggle,
)
from engine.command_palette_state import (
    dump_palette_state,
    load_command_palette_state,
    load_palette_state,
    resolve_command_palette_state_path,
    save_command_palette_state,
)

pytestmark = pytest.mark.fast


def _make_prompt_command(cmd_id: str) -> SimpleNamespace:
    prompt = SimpleNamespace(kind="text", placeholder="", default_value_fn=lambda _window: "")
    return SimpleNamespace(
        id=cmd_id,
        title=f"Command {cmd_id}",
        section="Selection",
        prompt=prompt,
        prompts=None,
        macro_id="",
        action=lambda _window, _raw_arg: None,
        is_enabled=lambda _window: (True, ""),
    )


def _make_window() -> SimpleNamespace:
    return SimpleNamespace(
        show_debug=True,
        command_palette_enabled=False,
        command_palette_help_enabled=False,
        command_palette_prompt_active=False,
        command_palette_prompt_command_id="",
        command_palette_query="",
        command_palette_index=0,
        command_palette_prompt_steps=(),
        command_palette_prompt_step_index=0,
        command_palette_prompt_values={},
        command_palette_prompt_text="",
        command_palette_prompt_kind="text",
        command_palette_prompt_index=0,
        command_palette_prompt_query="",
        command_palette_prompt_placeholder="",
        command_palette_prompt_title="",
    )


def _patch_commands(monkeypatch: pytest.MonkeyPatch, commands: list[SimpleNamespace]) -> None:
    import engine.command_palette as palette_mod

    monkeypatch.setattr(palette_mod, "build_default_commands", lambda _window: list(commands))


def test_palette_state_dump_load_roundtrip() -> None:
    payload = dump_palette_state(
        recents=["cmd.c", "cmd.a"],
        history={"cmd.b": ["left", "right"], "cmd.a": ["x=1"]},
    )
    assert payload["schema_version"] == 1
    recents, history = load_palette_state(payload)
    assert recents == ["cmd.c", "cmd.a"]
    assert history == {"cmd.a": ["x=1"], "cmd.b": ["left", "right"]}


def test_default_state_path_is_under_mesh_dir_not_repo_root(tmp_path: Path) -> None:
    path = resolve_command_palette_state_path(repo_root=tmp_path)
    assert path == tmp_path / ".mesh" / "command_palette_state.json"
    assert path.parent != tmp_path


def test_palette_state_missing_and_corrupt_file_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "command_palette_state.json"
    monkeypatch.setenv("MESH_COMMAND_PALETTE_STATE_PATH", str(state_path))
    assert load_command_palette_state() == ([], {})

    state_path.write_text("{not valid json", encoding="utf-8")
    assert load_command_palette_state() == ([], {})


def test_palette_state_caps_enforced() -> None:
    recents, history = load_palette_state(
        {
            "schema_version": 1,
            "recents": ["", "cmd.a", "cmd.b", "cmd.a", "cmd.c"],
            "history": {
                "cmd.z": ["", "1", "2", "3"],
                "cmd.a": ["left", "right"],
                "": ["invalid"],
            },
        },
        max_recents=2,
        max_entries_per_command=2,
        max_commands=1,
    )
    assert recents == ["cmd.a", "cmd.b"]
    assert history == {"cmd.a": ["left", "right"]}


def test_controller_persists_recents_and_prompt_history_across_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "command_palette_state.json"
    monkeypatch.setenv("MESH_COMMAND_PALETTE_STATE_PATH", str(state_path))
    _patch_commands(monkeypatch, [_make_prompt_command("selection.align")])

    window1 = _make_window()
    assert handle_command_palette_toggle(window1) is True
    assert window1.command_palette_enabled is True
    window1.command_palette_prompt_active = True
    window1.command_palette_prompt_command_id = "selection.align"
    window1.command_palette_prompt_text = "left"
    window1.command_palette_prompt_kind = "text"
    assert handle_command_palette_activate(window1, snapshot=SimpleNamespace(), repeat=False) is True
    assert state_path.exists()

    window2 = _make_window()
    assert handle_command_palette_toggle(window2) is True
    assert get_command_palette_recent_command_ids(window2) == ("selection.align",)
    assert get_command_palette_prompt_history_entries(window2, "selection.align") == ("left",)

    removed = clear_command_palette_recent_commands(window2)
    assert removed == 1
    recents, history = load_command_palette_state(path=state_path)
    assert recents == []
    assert history == {"selection.align": ["left"]}


def test_save_palette_state_is_deterministic(tmp_path: Path) -> None:
    state_path = tmp_path / "command_palette_state.json"
    save_command_palette_state(
        recents=["cmd.b", "cmd.a"],
        history={"cmd.b": ["x=1"], "cmd.a": ["left", "right"]},
        path=state_path,
    )
    first = state_path.read_text(encoding="utf-8")
    save_command_palette_state(
        recents=["cmd.b", "cmd.a"],
        history={"cmd.b": ["x=1"], "cmd.a": ["left", "right"]},
        path=state_path,
    )
    second = state_path.read_text(encoding="utf-8")
    assert second == first
