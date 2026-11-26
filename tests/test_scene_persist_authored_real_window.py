"""#665: a developer launch's F3 room save (Ctrl+Shift+S, Ctrl+S), also after F11 tile paint or HOME entity paint,
wrote the loader's runtime tilemap fields (a machine-absolute ``tilemap.resolved_path``, an empty ``tilemap.layers``
beside inline ``tile_layers``) back into the room, so the next load failed ``scene.schema.json`` and the developer's
room no longer started. The save now keeps only authored fields and checks the result against the schema the loader
uses; a payload the loader would reject is refused and the file is left as it was.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from tests.test_dev_tools_gate_real_window import _paint_then_persist, _persist, _press
from tests.test_legacy_editor_gate_real_window import _close

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

TILEMAPS = {
    # inline tile layers with a source map: the loader adds resolved_path and an empty layers list
    "inline": {"path": "maps/room_map.json", "width": 20, "height": 12, "tilewidth": 16, "tileheight": 16,
               "tile_layers": [{"id": "Ground", "z": -100, "parallax": 1.0, "tiles": [0] * 240}]},
    # the legacy format: the loader adds resolved_path
    "legacy": {"path": "maps/room_map.json", "layers": [{"name": "Ground"}]},
}


def _launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tilemap: dict[str, Any]) -> tuple[Any, Path]:
    """``mesh play`` (a developer launch) on ``project/room.json``, from a different current folder."""
    from engine.game import GameWindow

    project, launch = tmp_path / "project", tmp_path / "launch"
    (project / "maps").mkdir(parents=True)
    launch.mkdir()
    (project / "maps" / "room_map.json").write_text(
        json.dumps({"width": 20, "height": 12, "tilewidth": 16, "tileheight": 16, "layers": []}), encoding="utf-8")
    room = project / "room.json"
    room.write_text(json.dumps({"name": "Room", "schema_version": 1, "version": 1, "layers": [], "tilemap": tilemap,
                                "entities": [{"id": "crate", "x": 64.0, "y": 64.0}]}, indent=2), encoding="utf-8")
    monkeypatch.chdir(launch)
    monkeypatch.setenv("MESH_REPO_ROOT", str(project))
    monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    cfg = EngineConfig(width=320, height=200, title="persist", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None)
    setattr(cfg, "_mesh_launch_mode", "play")
    window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    window.load_scene(str(room))
    menu = getattr(window, "main_menu_overlay", None)
    if menu is not None and menu.visible:
        menu.close()
    return window, room


def _assert_loads(room: Path) -> dict[str, Any]:
    from engine.scene_loader import SceneLoader
    from engine.schema_validation import validate

    saved = json.loads(room.read_text(encoding="utf-8"))
    validate(saved, "scene.schema.json", room)  # (raises with the offending pointer)
    assert "resolved_path" not in saved["tilemap"]
    assert SceneLoader().load_scene(str(room), strict=True)["name"] == "Room"
    return saved


@pytest.mark.parametrize("kind", sorted(TILEMAPS))
@pytest.mark.parametrize("route", ["persist", "tile_paint", "entity_paint"])
def test_a_dev_launch_room_save_writes_a_room_that_still_loads(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        route: str, kind: str) -> None:
    window, room = _launch(tmp_path, monkeypatch, TILEMAPS[kind])
    key = optional_arcade.arcade.key
    try:
        if route == "persist":
            _press(window, key.F3)
            window.scene_controller._loaded_scene_source_data["entities"][0]["x"] = 96.0  # (an edit worth saving)
            _persist(window)
        else:
            _paint_then_persist(window, key.F11 if route == "tile_paint" else key.HOME)
        assert window.show_debug is True
        out = capsys.readouterr().out
        assert "SCENE_PERSIST ok" in out, out
        saved = _assert_loads(room)
        assert saved["tilemap"]["path"] == "maps/room_map.json"
        if route == "persist":
            assert saved["entities"][0]["x"] == 96.0  # (the save happened)
        assert window.reload_scene_from_disk() is True
    finally:
        _close(window)


def test_a_payload_the_loader_would_reject_is_refused_and_the_room_is_untouched(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The schema check, not only the strip: anything the structural checks miss but the loader rejects is refused."""
    window, room = _launch(tmp_path, monkeypatch, TILEMAPS["inline"])
    before = room.read_bytes()
    key = optional_arcade.arcade.key
    try:
        _press(window, key.F3)
        window.scene_controller._loaded_scene_source_data["tilemap"]["tile_size"] = 16  # (not a tilemap field)
        _persist(window)
        out = capsys.readouterr().out
        assert "SCENE_PERSIST fail" in out and "Room not saved: schema /tilemap" in out, out
        assert room.read_bytes() == before
        assert window.reload_scene_from_disk() is True
    finally:
        _close(window)
