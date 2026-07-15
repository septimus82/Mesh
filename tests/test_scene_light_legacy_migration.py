from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.behaviours.scene_transition import SceneTransition
from engine.migrations import DEFAULT_LEGACY_LIGHT_MODE, migrate_scene
from engine.scene_loader import SceneLoader
from engine.schema_validation import validate

pytestmark = pytest.mark.fast


def test_legacy_scene_light_without_mode_receives_default() -> None:
    scene = _legacy_light_scene()

    migrated = migrate_scene(scene)

    assert migrated["lights"][0]["mode"] == DEFAULT_LEGACY_LIGHT_MODE
    assert scene["lights"][0].get("mode") is None


def test_light_with_existing_mode_keeps_value() -> None:
    scene = _legacy_light_scene(mode="hard")

    migrated = migrate_scene(scene)

    assert migrated["lights"][0]["mode"] == "hard"
    assert migrated is scene


def test_scene_with_no_lights_still_loads(tmp_path: Path) -> None:
    scene_path = tmp_path / "no_lights.json"
    scene_path.write_text(json.dumps({"name": "No Lights", "entities": []}), encoding="utf-8")

    loaded = SceneLoader().load_scene(str(scene_path))

    assert loaded["name"] == "No Lights"
    assert loaded["entities"] == []


def test_migrated_legacy_light_scene_passes_scene_schema_validation(tmp_path: Path) -> None:
    scene_path = tmp_path / "legacy_light.json"
    scene = _legacy_light_scene()

    migrated = migrate_scene(scene)

    assert validate(migrated, "scene.schema.json", scene_path) is migrated


def test_legacy_light_migration_is_idempotent_and_preserves_unrelated_data() -> None:
    scene = _legacy_light_scene()
    scene["settings"] = {"music": "assets/music/theme.ogg"}
    scene["entities"] = [{"id": "marker", "x": 1, "y": 2}]
    before = copy.deepcopy(scene)

    once = migrate_scene(scene)
    twice = migrate_scene(once)

    assert once == twice
    assert scene == before
    assert once["settings"] == before["settings"]
    assert once["entities"] == before["entities"]


def test_migration_handles_missing_and_malformed_lights_safely() -> None:
    no_lights = {"name": "No Lights", "entities": []}
    malformed_lights = {"name": "Bad Lights", "entities": [], "lights": ["bad", None]}

    assert migrate_scene(no_lights) is no_lights
    assert migrate_scene(malformed_lights) is malformed_lights


def test_scene_loader_migrates_legacy_lights_before_validation(tmp_path: Path) -> None:
    scene_path = tmp_path / "legacy_light_load.json"
    scene_path.write_text(json.dumps(_legacy_light_scene()), encoding="utf-8")

    loaded = SceneLoader().load_scene(str(scene_path))

    assert loaded["lights"][0]["mode"] == DEFAULT_LEGACY_LIGHT_MODE


def test_scene_transition_into_legacy_light_scene_no_longer_crashes(tmp_path: Path) -> None:
    scene_path = tmp_path / "legacy_transition_target.json"
    scene_path.write_text(json.dumps(_legacy_light_scene()), encoding="utf-8")
    loaded: dict[str, object] = {}

    def request_scene_change(path: str) -> None:
        loaded["scene"] = SceneLoader().load_scene(path)

    entity = SimpleNamespace(
        mesh_name="LegacyLightDoor",
        mesh_entity_data={},
    )
    window = SimpleNamespace(
        console_log=MagicMock(),
        emit_signal=MagicMock(),
        request_scene_change=request_scene_change,
        set_next_spawn_point=MagicMock(),
    )
    behaviour = SceneTransition(entity, window, target_scene=str(scene_path), spawn_id="field_return")

    behaviour.on_interact(window, SimpleNamespace(mesh_name="Player"))

    assert loaded["scene"]["lights"][0]["mode"] == DEFAULT_LEGACY_LIGHT_MODE
    window.set_next_spawn_point.assert_called_once_with("field_return")


def _legacy_light_scene(*, mode: str | None = None) -> dict:
    light = {
        "id": "legacy_light",
        "type": "point",
        "x": 32.0,
        "y": 48.0,
        "radius": 96.0,
        "color": "#ffddaa",
    }
    if mode is not None:
        light["mode"] = mode
    return {
        "name": "Legacy Light Scene",
        "entities": [],
        "lights": [light],
    }
