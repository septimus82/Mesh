"""A scene saved with the live camera zoom (engine.scene_runtime.persistence.build_scene_snapshot): the zoom goes into
``settings.camera.zoom`` whether or not the authored room has a camera block. Before the fix, a room whose settings had
no ``camera`` (or no ``settings`` at all) got the zoom written into a detached default dict, so the save carried none and
the room reopened at 1.0 (found in the repository health audit: live zoom 2.5, ``"settings": {}``, no zoom saved).

Real production code throughout: the snapshot, the loader's scene defaults, compaction, the camera controller (its
Arcade camera stubbed, as the other headless camera tests do), the atomic JSON writer the console's ``scene save`` and
the editor's save use, and ``SceneLoader.load_scene`` with ``CameraController.configure_from_scene`` to reopen."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from engine import json_io
from engine.camera_controller import CameraController
from engine.scene_loader import SceneLoader
from engine.scene_runtime.persistence import build_scene_snapshot
from engine.scene_serializer import compact_scene_payload


class _StubCamera:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.position = (0.0, 0.0)
        self.zoom = 1.0


def _camera(current: float = 2.5, target: float = 3.0) -> CameraController:
    with patch("engine.camera_controller.ArcadeCamera", _StubCamera):
        camera = CameraController(cast(Any, SimpleNamespace(width=800, height=600)))
    camera.zoom_state.current, camera.zoom_state.target = current, target
    return camera


def _controller(scene: dict[str, Any], camera: CameraController | None = None) -> SimpleNamespace:
    """What build_scene_snapshot reads from a scene controller: the authored room, its window's camera, state and
    loader; no sprites or tilemap (the camera block is what is under test)."""
    window = SimpleNamespace(camera_controller=camera or _camera(), game_state=SimpleNamespace(snapshot=lambda: {}),
                             scene_loader=SceneLoader())
    return SimpleNamespace(window=window, _loaded_scene_source_data=scene, all_sprites=[], layers={},
                           tilemap_instance=None)


LIVE_ZOOM = {"initial": 2.5, "target": 3.0, "speed": 5.0, "min": 0.25, "max": 4.0}


@pytest.mark.fast
@pytest.mark.parametrize("scene", [
    {"entities": []},  # no settings at all
    {"entities": [], "settings": {}},  # settings without a camera (the audit's case)
    {"entities": [], "settings": {"background_color": "#203040", "music_volume": 0.4}},
], ids=["no-settings", "empty-settings", "other-settings-only"])
def test_a_room_without_a_camera_block_saves_the_live_zoom(scene: dict[str, Any]) -> None:
    authored = copy.deepcopy(scene)
    snap = build_scene_snapshot(_controller(scene))
    assert snap["settings"]["camera"] == {"zoom": LIVE_ZOOM}
    for key, value in (authored.get("settings") or {}).items():
        assert snap["settings"][key] == value, key
    assert scene == authored, "the authored room itself is untouched"
    assert compact_scene_payload(snap)["settings"]["camera"] == {"zoom": LIVE_ZOOM}, "kept when compacted"


@pytest.mark.fast
def test_authored_camera_settings_survive_and_the_live_zoom_replaces_the_authored_zoom() -> None:
    camera_block = {"lerp_factor": 3.5, "deadzone_px": 12, "bounds": {"left": 0, "right": 640, "bottom": 0, "top": 480},
                    "areas": [{"id": "hall", "x": 0, "y": 0, "width": 320, "height": 240, "zoom": 1.5}],
                    "zoom": {"initial": 1.25, "target": 1.25, "speed": 2.0, "min": 0.5, "max": 2.0}}
    scene = {"entities": [], "settings": {"camera": camera_block, "background_color": "#101010", "world_width": 640}}
    snap = build_scene_snapshot(_controller(copy.deepcopy(scene)))
    saved = snap["settings"]["camera"]
    assert {k: v for k, v in saved.items() if k != "zoom"} == {k: v for k, v in camera_block.items() if k != "zoom"}
    assert saved["zoom"] == LIVE_ZOOM, "the live zoom is what is saved (the authored zoom is its starting value)"
    assert snap["settings"]["background_color"] == "#101010" and snap["settings"]["world_width"] == 640


@pytest.mark.fast
@pytest.mark.parametrize("camera_value", [{}, None, 5, "wide", [1, 2]],
                         ids=["empty", "null", "number", "string", "list"])
def test_an_empty_or_unreadable_camera_block_becomes_one_holding_the_live_zoom(camera_value: Any) -> None:
    snap = build_scene_snapshot(_controller({"entities": [], "settings": {"camera": camera_value, "music": "a.ogg"}}))
    assert snap["settings"]["camera"] == {"zoom": LIVE_ZOOM}
    assert snap["settings"]["music"] == "a.ogg"


@pytest.mark.fast
def test_the_snapshot_is_json_serialisable_and_the_same_every_time() -> None:
    controller = _controller({"entities": [], "settings": {"background_color": "#000000"}})
    first, second = build_scene_snapshot(controller), build_scene_snapshot(controller)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert json.loads(json.dumps(first)) == first


@pytest.mark.integration  # (writes and reads scene files)
@pytest.mark.parametrize("compact", [False, True], ids=["full", "compact"])
@pytest.mark.parametrize("settings", [None, {}, {"background_color": "#203040"}],
                         ids=["no-settings", "empty-settings", "other-settings-only"])
def test_the_saved_zoom_reopens_through_the_real_save_and_load_path(tmp_path: Path, compact: bool,
                                                                    settings: dict[str, Any] | None) -> None:
    scene: dict[str, Any] = {"entities": [], **({"settings": settings} if settings is not None else {})}
    snap = build_scene_snapshot(_controller(scene), compact=compact)
    path = tmp_path / "room.json"
    json_io.write_json_atomic(str(path), snap)  # (what `scene save` and the editor's save write)
    loaded = SceneLoader().load_scene(str(path))
    reopened = _camera(current=1.0, target=1.0)
    reopened.configure_from_scene(loaded["settings"])
    assert (reopened.zoom_state.current, reopened.zoom_state.target) == (2.5, 3.0)
    assert (reopened.zoom_state.min_zoom, reopened.zoom_state.max_zoom) == (0.25, 4.0)
