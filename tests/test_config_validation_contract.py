from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine import config

pytestmark = [pytest.mark.fast]


def _load_with_validation_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    diag_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] | None = None,
) -> config.EngineConfig:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(config, "validate", lambda _raw, _schema, _path: None)
    if diag_calls is not None:
        monkeypatch.setattr(config, "diag_error", lambda *args, **kwargs: diag_calls.append((args, kwargs)))
    return config.load_config(str(cfg_path))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("width", True), ("width", 0), ("width", -1), ("width", "1280"),
        ("height", True), ("height", 0), ("height", -1), ("height", "720"),
        ("title", ""), ("title", 123),
        ("start_scene", ""), ("start_scene", "scene_id"), ("start_scene", 123), ("start_scene", None),
        ("main_menu_scene", ""), ("main_menu_scene", "menu"), ("main_menu_scene", 123),
        ("world_file", ""), ("world_file", "world"), ("world_file", 123),
        ("content_roots", "content"), ("content_roots", [""]), ("content_roots", [123]),
    ],
)
def test_invalid_config_values_preserve_default_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    key: str,
    value: Any,
) -> None:
    diag_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    cfg = _load_with_validation_disabled(tmp_path, monkeypatch, {key: value}, diag_calls)

    assert getattr(cfg, key) == getattr(config.EngineConfig(), key)
    assert len(diag_calls) == 1
    args, kwargs = diag_calls[0]
    assert args[0] == "config.invalid_value"
    assert f"Invalid config key '{key}'" in args[1]
    assert args[2] == "engine.config"
    assert kwargs["context"] == {"key": key}
    captured = capsys.readouterr()
    assert f"[Mesh][Config] ERROR: Invalid config key '{key}':" in captured.out


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("width", 1280), ("width", 1),
        ("height", 720), ("height", 1),
        ("title", "Mesh"), ("title", "Demo"),
        ("start_scene", "scenes/cellar.json"),
        ("main_menu_scene", None), ("main_menu_scene", "scenes/menu.json"),
        ("world_file", None), ("world_file", "worlds/main.json"),
        ("content_roots", []), ("content_roots", ["."]), ("content_roots", ["content", "mods/x"]),
    ],
)
def test_valid_config_values_are_applied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    key: str,
    value: Any,
) -> None:
    diag_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    cfg = _load_with_validation_disabled(tmp_path, monkeypatch, {key: value}, diag_calls)

    assert getattr(cfg, key) == value
    assert diag_calls == []
    assert "[Mesh][Config] ERROR: Invalid config key" not in capsys.readouterr().out


def test_auto_open_quest_log_defaults_false_and_schema_accepts_field(tmp_path: Path) -> None:
    absent_path = tmp_path / "absent.json"
    absent_path.write_text("{}", encoding="utf-8")

    absent = config.load_config(str(absent_path))

    assert absent.auto_open_quest_log is False

    present_path = tmp_path / "present.json"
    present_path.write_text(json.dumps({"auto_open_quest_log": True}) + "\n", encoding="utf-8")

    present = config.load_config(str(present_path))

    assert present.auto_open_quest_log is True


def test_multiple_invalid_config_values_default_and_emit_one_diagnostic_each(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {
        "width": 0,
        "title": "",
        "start_scene": "scene_id",
        "world_file": "world",
        "content_roots": [""],
    }
    diag_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    cfg = _load_with_validation_disabled(tmp_path, monkeypatch, payload, diag_calls)

    defaults = config.EngineConfig()
    assert cfg.width == defaults.width
    assert cfg.title == defaults.title
    assert cfg.start_scene == defaults.start_scene
    assert cfg.world_file == defaults.world_file
    assert cfg.content_roots == defaults.content_roots
    assert [call[0][0] for call in diag_calls] == ["config.invalid_value"] * len(payload)
    assert {call[1]["context"]["key"] for call in diag_calls} == set(payload)
    assert capsys.readouterr().out.count("[Mesh][Config] ERROR: Invalid config key") == len(payload)
