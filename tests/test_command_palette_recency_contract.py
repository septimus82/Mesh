from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor import command_palette_rank_model as rank_model
from engine.editor.command_palette_rank_model import score_command
from engine.editor.editor_command_palette_controller import activate
from engine.editor_commands import Command, filter_commands

pytestmark = pytest.mark.fast


def setup_function() -> None:
    rank_model._RECENT_COMMAND_IDS.clear()


def _score(command_id: str) -> tuple[float, int, int, int, str, str]:
    score = score_command(command_id, "Copy", ("copy",), "copy")
    assert score is not None
    return score


def _record(command_id: str) -> None:
    getattr(rank_model, "record_" + "command_executed")(command_id)


def _command(command_id: str, title: str) -> Command:
    return Command(id=command_id, title=title, keywords=(title.lower(),), run=lambda _window: None)


def test_empty_recency_leaves_score_at_baseline() -> None:
    assert _score("editor.copy")[0] == 0.0


def test_single_recent_command_gets_half_point_bonus() -> None:
    before = _score("editor.copy")

    _record("editor.copy")

    after = _score("editor.copy")
    other = _score("editor.other")
    assert after[0] == before[0] - 0.5
    assert other[0] == before[0]


def test_five_recent_commands_all_get_bonus() -> None:
    for index in range(5):
        _record(f"editor.recent.{index}")

    assert [_score(f"editor.recent.{index}")[0] for index in range(5)] == [-0.5] * 5


def test_sixth_recent_command_evicts_oldest() -> None:
    for index in range(6):
        _record(f"editor.recent.{index}")

    assert _score("editor.recent.0")[0] == 0.0
    assert _score("editor.recent.5")[0] == -0.5


def test_repeated_command_moves_to_front_without_duplicate() -> None:
    for command_id in ("editor.a", "editor.b", "editor.c", "editor.a"):
        _record(command_id)

    assert tuple(rank_model._RECENT_COMMAND_IDS) == ("editor.a", "editor.c", "editor.b")


def test_recent_score_composes_with_existing_filter_ranking() -> None:
    commands = [
        _command("editor.alpha", "Copy Alpha"),
        _command("editor.beta", "Copy Beta"),
    ]

    _record("editor.beta")

    assert [command.id for command in filter_commands(commands, "copy")] == [
        "editor.beta",
        "editor.alpha",
    ]


def test_palette_activation_records_selected_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    commands = [
        Command(id="editor.alpha", title="Alpha", keywords=("alpha",), run=lambda _window: calls.append("alpha")),
        Command(id="editor.beta", title="Beta", keywords=("beta",), run=lambda _window: calls.append("beta")),
    ]
    editor = SimpleNamespace(
        window=SimpleNamespace(),
        search=SimpleNamespace(get_command_palette_state=lambda: ("", 1), clear_command_palette_state=lambda: None),
        panels=SimpleNamespace(close_command_palette=lambda: None),
    )

    monkeypatch.setattr("engine.editor_commands.get_all_commands", lambda _window: commands)
    monkeypatch.setattr("engine.editor_commands.filter_commands", lambda commands, _query, focus_target=None: list(commands))
    monkeypatch.setattr("engine.editor_commands.get_palette_focus_target", lambda _editor: None)

    assert activate(editor) is True
    assert calls == ["beta"]
    assert _score("editor.beta")[0] == -0.5
