from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine.scene_loader import SceneLoader
from engine.scene_runtime.persistence import build_scene_snapshot
from engine.schema_validation import SchemaValidationError, validate

pytestmark = pytest.mark.fast


def _scene_paths() -> list[Path]:
    root = Path.cwd()
    return sorted(root.glob("scenes/*.json")) + sorted(root.glob("packs/**/scenes/*.json"))


def _sprite_from_entity(entity: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        center_x=float(entity.get("x", 0.0)),
        center_y=float(entity.get("y", 0.0)),
        scale=float(entity.get("scale", 1.0)),
        angle=float(entity.get("rotation", 0.0)),
        mesh_entity_data=copy.deepcopy(entity),
    )


def _controller_for_scene(scene: dict[str, Any], *, source: dict[str, Any] | None = None) -> SimpleNamespace:
    sprites = [_sprite_from_entity(entity) for entity in scene.get("entities", []) if isinstance(entity, dict)]
    layers: dict[str, list[Any]] = {}
    for layer in scene.get("layers", []):
        if isinstance(layer, dict) and isinstance(layer.get("name"), str):
            layers[layer["name"]] = []
    layers.setdefault("entities", [])
    for sprite in sprites:
        entity = sprite.mesh_entity_data
        layer_name = entity.get("layer", "entities") if isinstance(entity, dict) else "entities"
        layers.setdefault(str(layer_name), []).append(sprite)

    window = SimpleNamespace(
        camera_controller=SimpleNamespace(
            zoom_state=SimpleNamespace(current=1.0, target=1.0, speed=0.1, min_zoom=0.25, max_zoom=4.0),
        ),
        game_state=SimpleNamespace(snapshot=lambda: {}),
        game_state_controller=SimpleNamespace(export_state=lambda: {}),
        scene_loader=SceneLoader(),
    )
    return SimpleNamespace(
        _loaded_scene_data=copy.deepcopy(scene),
        _loaded_scene_source_data=copy.deepcopy(source if source is not None else scene),
        all_sprites=sprites,
        layers=layers,
        tilemap_instance=None,
        window=window,
    )


def test_dogfood_corruption_fixture_reproduces_schema_violations() -> None:
    path = Path("tests/fixtures/door_field.dogfood-save-corruption.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(payload, "scene.schema.json", path)

    message = str(exc_info.value)
    assert "/entities/15" in message
    assert "Health" in message
    assert "drop_table_id" in message


def test_ambient_light_schema_does_not_require_point_radius() -> None:
    payload = {
        "name": "Ambient Only",
        "entities": [],
        "lights": [{"type": "ambient", "color": "#ffffff", "intensity": 0.25, "mode": "soft"}],
    }

    assert validate(payload, "scene.schema.json", "ambient_only.json") is payload


def test_editor_serializer_does_not_persist_runtime_encounter_or_component_fields() -> None:
    source = {
        "name": "Runtime Fields",
        "entities": [
            {"id": "marker_without_sprite", "tag": "spawn_point", "x": 0, "y": 0},
            {"id": "enemy_placeholder", "name": "Theme Enemy Placeholder", "prefab_id": "theme_enemy_placeholder", "x": 1, "y": 2},
        ],
    }
    runtime = copy.deepcopy(source)
    runtime["entities"] = [runtime["entities"][1]]
    runtime["entities"][0]["name"] = "ThemedEnemy"
    runtime["entities"][0]["prefab_id"] = "rat"
    runtime["entities"][0]["sprite"] = "assets/rat.png"
    runtime["entities"][0]["drop_table_id"] = "nature_drops"
    runtime["entities"][0]["Health"] = {}

    controller = _controller_for_scene(runtime, source=source)

    snapshot = build_scene_snapshot(controller)

    assert [entity["id"] for entity in snapshot["entities"]] == ["marker_without_sprite", "enemy_placeholder"]
    saved_entity = snapshot["entities"][1]
    assert saved_entity["prefab_id"] == "theme_enemy_placeholder"
    assert "name" not in saved_entity
    assert "drop_table_id" not in saved_entity
    assert "Health" not in saved_entity
    assert "sprite" not in saved_entity
    validate(snapshot, "scene.schema.json", "runtime_fields.json")


def test_editor_serializer_omits_lights_when_scene_authored_no_lights() -> None:
    scene = {"name": "No Lights", "entities": []}

    snapshot = build_scene_snapshot(_controller_for_scene(SceneLoader().apply_scene_defaults(scene), source=scene))

    assert "lights" not in snapshot
    validate(snapshot, "scene.schema.json", "no_lights.json")


@pytest.mark.parametrize("scene_path", _scene_paths(), ids=lambda path: path.as_posix())
def test_all_checked_in_scenes_load_editor_save_and_validate(scene_path: Path) -> None:
    loaded = SceneLoader().load_scene(str(scene_path))

    snapshot = build_scene_snapshot(_controller_for_scene(loaded))

    validate(snapshot, "scene.schema.json", scene_path)
