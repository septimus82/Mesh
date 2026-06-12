from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine import config
from engine.scene_runtime import scene_load_apply

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


def test_day_night_legacy_keys_load_into_canonical_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"day_start_hour": 7.5, "day_length_seconds": 1200.0}) + "\n",
        encoding="utf-8",
    )

    cfg = config.load_config(str(cfg_path))

    assert cfg.day_night_start_hour == 7.5
    assert cfg.day_night_cycle_length_seconds == 1200.0
    assert not hasattr(cfg, "day_start_hour")
    assert not hasattr(cfg, "day_length_seconds")
    captured = capsys.readouterr()
    assert "Config key 'day_start_hour' is deprecated; use 'day_night_start_hour' instead" in captured.out
    assert (
        "Config key 'day_length_seconds' is deprecated; "
        "use 'day_night_cycle_length_seconds' instead"
    ) in captured.out


def test_day_night_canonical_keys_win_legacy_conflicts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({
            "day_start_hour": 7.5,
            "day_length_seconds": 1200.0,
            "day_night_start_hour": 9.25,
            "day_night_cycle_length_seconds": 1800.0,
        }) + "\n",
        encoding="utf-8",
    )

    cfg = config.load_config(str(cfg_path))

    assert cfg.day_night_start_hour == 9.25
    assert cfg.day_night_cycle_length_seconds == 1800.0
    captured = capsys.readouterr()
    assert "Config keys 'day_start_hour' and 'day_night_start_hour' are both set" in captured.out
    assert (
        "Config keys 'day_length_seconds' and 'day_night_cycle_length_seconds' are both set"
    ) in captured.out


def test_day_night_defaults_unchanged_without_config_keys(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}\n", encoding="utf-8")

    cfg = config.load_config(str(cfg_path))

    assert cfg.day_night_start_hour == 21.0
    assert cfg.day_night_cycle_length_seconds == 600.0


def test_save_config_migrates_day_night_aliases_to_canonical_keys(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"day_start_hour": 7.5, "day_length_seconds": 1200.0}) + "\n",
        encoding="utf-8",
    )
    cfg = config.load_config(str(cfg_path))
    out_path = tmp_path / "saved.json"

    config.save_config(cfg, str(out_path))

    saved = json.loads(out_path.read_text(encoding="utf-8"))
    assert saved["day_night_start_hour"] == 7.5
    assert saved["day_night_cycle_length_seconds"] == 1200.0
    assert "day_start_hour" not in saved
    assert "day_length_seconds" not in saved


def test_scene_day_night_cycle_length_setting_still_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float] = []
    day_night = SimpleNamespace(
        enabled=False,
        set_hour=lambda _hour: None,
        set_cycle_length_seconds=lambda seconds: calls.append(seconds),
    )
    controller = SimpleNamespace(window=SimpleNamespace(day_night=day_night, set_next_spawn_point=lambda _id: None))
    monkeypatch.setattr(scene_load_apply.optional_arcade.arcade, "get_window", lambda: object())
    monkeypatch.setattr(scene_load_apply.optional_arcade.arcade, "set_background_color", lambda _color: None)

    scene_load_apply.apply_scene_settings(controller, {"day_night_cycle_length_seconds": "1200"})

    assert calls == [1200.0]


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
