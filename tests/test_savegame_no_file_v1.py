from __future__ import annotations

from pathlib import Path


def test_load_savegame_v1_no_file_returns_none(tmp_path: Path) -> None:
    from engine.savegame import load_savegame

    assert load_savegame(tmp_path / "missing.json") is None

