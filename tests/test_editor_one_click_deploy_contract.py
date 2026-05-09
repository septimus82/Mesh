from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_build_controller import EditorBuildController
from engine.editor.editor_overlay_controller import EditorOverlayController
from engine.editor.state import EditorBuildSession
from engine.editor_commands import get_all_commands, run_command
from engine.game_runtime import input_dispatch
from tests._typing import as_any

pytestmark = pytest.mark.fast


class _FakeProcess:
    def __init__(self, returncode: int | None = None, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    def poll(self) -> int | None:
        return self.returncode

    def communicate(self) -> tuple[str, str]:
        return self._stdout, self._stderr


class _Feedback:
    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.error_messages: list[str] = []

    def info(self, message: str, **_kwargs: Any) -> None:
        self.info_messages.append(str(message))

    def warning(self, message: str, **_kwargs: Any) -> None:
        self.warning_messages.append(str(message))

    def error(self, message: str, **_kwargs: Any) -> None:
        self.error_messages.append(str(message))


def _editor(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        active=True,
        build_session=EditorBuildSession(),
        feedback=_Feedback(),
        window=SimpleNamespace(paused=False),
        _get_repo_root=lambda: tmp_path,
    )


def test_build_for_windows_command_palette_action_starts_build(tmp_path: Path) -> None:
    calls: list[str] = []
    editor = SimpleNamespace(build=SimpleNamespace(build_windows=lambda: calls.append("build")))
    window = SimpleNamespace(editor_controller=editor)

    commands = {command.id: command.title for command in get_all_commands(window)}
    assert commands["editor.build.windows"] == "Build for Windows"
    assert run_command("editor.build.windows", window) is True

    assert calls == ["build"]


def test_build_windows_starts_package_player_subprocess_and_pauses_editor(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    fake_process = _FakeProcess(returncode=None)

    def _popen(cmd: list[str], **kwargs: Any) -> _FakeProcess:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return fake_process

    editor = _editor(tmp_path)
    controller = EditorBuildController(editor, popen_factory=as_any(_popen), open_folder=lambda _path: None)

    assert controller.build_windows() is True

    assert captured["cmd"] == [
        captured["cmd"][0],
        "-m",
        "mesh_cli",
        "package-player",
        "--out",
        str(tmp_path / "artifacts" / "player_pkg"),
        "--smoke",
    ]
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert editor.build_session.is_running is True
    assert editor.active is False
    assert editor.window.paused is True


def test_building_overlay_draws_while_build_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[str] = []
    ticks: list[str] = []
    monkeypatch.setattr("engine.editor.editor_overlay_controller._draw_rectangle_filled", lambda *a, **k: None)
    monkeypatch.setattr(
        "engine.editor.editor_overlay_controller.optional_arcade.arcade.draw_text",
        lambda text, *a, **k: drawn.append(str(text)),
    )
    editor = SimpleNamespace(
        active=False,
        build=SimpleNamespace(tick=lambda: ticks.append("tick")),
        build_session=SimpleNamespace(is_running=True),
        play_session=SimpleNamespace(is_playing=False),
        window=SimpleNamespace(width=800, height=600),
    )

    EditorOverlayController(editor).draw_overlay()

    assert ticks == ["tick"]
    assert "Building..." in drawn
    assert "This may take about 30 seconds" in drawn


def test_successful_build_restores_editor_feedback_and_opens_output(tmp_path: Path) -> None:
    opened: list[str] = []
    editor = _editor(tmp_path)
    process = _FakeProcess(returncode=0, stdout="ok", stderr="")
    controller = EditorBuildController(
        editor,
        popen_factory=as_any(lambda *_args, **_kwargs: process),
        open_folder=opened.append,
    )
    controller.build_windows()

    controller.tick()

    assert editor.build_session.is_running is False
    assert editor.active is True
    assert editor.window.paused is True
    assert opened == [str(tmp_path / "artifacts" / "player_pkg")]
    assert editor.feedback.info_messages[-1] == f"Build complete: {tmp_path / 'artifacts' / 'player_pkg'}"


def test_failed_build_restores_editor_logs_stderr_and_reports_error(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    process = _FakeProcess(returncode=7, stdout="out", stderr="bad things")
    controller = EditorBuildController(
        editor,
        popen_factory=as_any(lambda *_args, **_kwargs: process),
        open_folder=lambda _path: None,
    )
    controller.build_windows()

    controller.tick()

    log_path = tmp_path / "artifacts" / "editor_build_windows_stderr.log"
    assert editor.build_session.is_running is False
    assert editor.active is True
    assert "out" in log_path.read_text(encoding="utf-8")
    assert "bad things" in log_path.read_text(encoding="utf-8")
    assert editor.feedback.error_messages[-1] == f"Build failed: 7. See {log_path}"


def test_build_running_blocks_runtime_input(tmp_path: Path) -> None:
    calls: list[str] = []
    window = SimpleNamespace(
        editor_controller=SimpleNamespace(build_session=SimpleNamespace(is_running=True)),
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(on_key_press=lambda *_args: calls.append("ui")),
        input_controller=SimpleNamespace(
            on_key_press=lambda *_args: calls.append("input"),
            on_mouse_press=lambda *_args: calls.append("mouse"),
        ),
    )

    input_dispatch.on_key_press(as_any(window), optional_arcade.arcade.key.A, 0)
    input_dispatch.on_mouse_press(as_any(window), 1.0, 2.0, 1, 0)

    assert calls == []


def test_runtime_keys_reach_editor_input_when_editor_is_active() -> None:
    calls: list[tuple[int, int]] = []
    window = SimpleNamespace(
        editor_controller=SimpleNamespace(
            active=True,
            build_session=SimpleNamespace(is_running=False),
            play_session=SimpleNamespace(is_playing=False),
            handle_input=lambda key, modifiers: calls.append((int(key), int(modifiers))) or True,
        ),
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(on_key_press=lambda *_args: False),
        input_controller=SimpleNamespace(on_key_press=lambda *_args: calls.append(("input", 0))),
        game_over=False,
    )

    input_dispatch.on_key_press(as_any(window), optional_arcade.arcade.key.S, optional_arcade.arcade.key.MOD_CTRL)

    assert calls == [(optional_arcade.arcade.key.S, optional_arcade.arcade.key.MOD_CTRL)]


def test_duplicate_build_request_warns_without_spawning(tmp_path: Path) -> None:
    editor = _editor(tmp_path)
    editor.build_session.is_running = True
    controller = EditorBuildController(
        editor,
        popen_factory=as_any(lambda *_args, **_kwargs: pytest.fail("should not spawn")),
        open_folder=lambda _path: None,
    )

    assert controller.build_windows() is False

    assert editor.feedback.warning_messages == ["Build already running."]
