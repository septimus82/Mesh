"""AS-4: generated sidecars, v2 backups and temp files are never listed as save slots."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.save_manager import SaveManager

pytestmark = pytest.mark.integration


def _window() -> MagicMock:
    window = MagicMock()
    window.game_state_controller.export_state.return_value = {}
    window.scene_controller.current_scene_path = "scenes/test.json"
    window.scene_controller.build_scene_snapshot.return_value = {"version": 1, "state": {}, "entities": []}
    return window


def test_only_real_slots_are_listed_beside_sidecars_backups_and_temp_files(tmp_path: Path) -> None:
    save_dir = tmp_path / "saves"
    manager = SaveManager(_window(), save_dir=str(save_dir))
    assert manager.save_game("good") is True
    (save_dir / "broken.json").write_text("{not json", encoding="utf-8")
    assert manager.load_game("broken") is False  # the game's own refused load writes the sidecars
    sidecars = sorted(p.name for p in save_dir.glob("broken.json.diagnostics.*"))
    assert sidecars == ["broken.json.diagnostics.json", "broken.json.diagnostics.txt"]
    (save_dir / "good.json.v2.bak").write_text("{}", encoding="utf-8")
    (save_dir / "good.json.v2.abcd1234.bak").write_text("{}", encoding="utf-8")
    (save_dir / ".good.json.123.deadbeef.tmp").write_text("{}", encoding="utf-8")

    assert manager.list_saves() == ["broken", "good"]
    assert manager.load_game("good") is True
