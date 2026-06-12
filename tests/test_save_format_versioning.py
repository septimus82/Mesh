from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import savegame
from engine.persistence_io import SAVE_FORMAT_VERSION, migrate_save_payload
from engine.save_manager import SaveManager


def test_migrate_v0_payload_inserts_version():
    payload = {"hello": "world"}
    migrated = migrate_save_payload(dict(payload))
    assert migrated["save_format_version"] == SAVE_FORMAT_VERSION


def test_migrate_rejects_future_version():
    with pytest.raises(ValueError, match=r"Unsupported save_format_version"):
        migrate_save_payload({"save_format_version": SAVE_FORMAT_VERSION + 1})


def test_snapshot_load_rejects_future_version_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    path = Path("saves/quick.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "save_format_version": SAVE_FORMAT_VERSION + 1,
        "version": savegame.SNAPSHOT_VERSION,
        "world_file": "worlds/act1_prologue.json",
        "world_id": "act1_prologue",
        "scene_id": "packs/core_regions/scenes/Act1_Prologue_Cabin.json",
        "gold": 1,
        "flags": [],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    window = type("W", (), {})()
    window.game_state_controller = object()

    assert savegame.load_quick_snapshot(window, path=path) is False
    err = capsys.readouterr().err
    assert "Unsupported save_format_version" in err


def test_save_manager_load_migrates_v0_payload(tmp_path):
    # Minimal save file that still exercises migration hook.
    class _W:
        def __init__(self):
            from unittest.mock import MagicMock

            self.scene_controller = MagicMock()
            self.scene_controller.current_scene_path = "scenes/test.json"
            self.ui_controller = MagicMock()
            self.player_hud = MagicMock()
            self.request_scene_change = MagicMock()
            self.game_state_controller = MagicMock()
            self.game_state_controller.import_state = MagicMock()

    window = _W()
    manager = SaveManager(window, save_dir=str(tmp_path))

    # v0: missing save_format_version
    slot_path = manager.get_save_path("slot1")
    slot_path.write_text(
        json.dumps({"game_state": {"flags": {}, "counters": {"gold": 0}}, "meta": {"version": 2}}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    assert manager.load_game("slot1") is True
    window.request_scene_change.assert_called_once()
