import json
import types
from pathlib import Path

import engine.optional_arcade as optional_arcade
from engine.ui import DevBrowserOverlay
from tests._typing import as_any


def _stub_window():
    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    return window


def _lines_to_map(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def test_scene_preview_counts_and_schema_flags_are_deterministic(tmp_path: Path) -> None:
    scene_path = tmp_path / "my_scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "entities": [
                    {"id": " A ", "name": "N1", "behaviours": []},
                    {"id": "a", "name": "N2"},
                    {"name": "NoId", "behaviours": []},
                    {"id": "B", "behaviours": ["TriggerZone"], "behaviour_config": {"TriggerZone": {}}},
                    {
                        "id": "C",
                        "behaviours": ["TriggerZone"],
                        "behaviour_config": {"TriggerZone": {"zone_id": " Z "}},
                        "mesh_name": " MeshZ ",
                    },
                    {
                        "id": "D",
                        "behaviours": ["TriggerZone"],
                        "behaviour_config": {"TriggerZone": {"zone_id": "z"}},
                        "mesh_name": "meshz",
                    },
                    {"id": "E", "behaviours": ["SceneTransition"]},
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    overlay = DevBrowserOverlay(as_any(_stub_window()))
    overlay.mode = "scenes"
    overlay._items = [{"label": "my_scene.json", "scene_path": str(scene_path)}]
    overlay.selected_index = 0

    lines = overlay._get_preview_lines()
    assert lines[0] == "Preview (Scene)"
    parsed = _lines_to_map(lines)

    assert parsed["file"] == "my_scene.json"
    assert parsed["entity_count"] == "7"
    assert parsed["trigger_zone_count"] == "3"
    assert parsed["transition_count"] == "1"
    assert parsed["unique_ids_count"] == "5"
    assert parsed["duplicate_ids_count"] == "1"
    assert parsed["zone_id_count"] == "1"
    assert parsed["duplicate_zone_id_count"] == "1"
    assert parsed["mesh_name_count"] == "4"
    assert parsed["duplicate_mesh_name_count"] == "1"
    assert (
        parsed["schema_strict"]
        == "missing_id=1 missing_zone_id=1 duplicate_ids=1 duplicate_zone_ids=1"
    )


def test_world_preview_counts_and_start_scene_existence(tmp_path: Path) -> None:
    world_path = tmp_path / "my_world.json"
    world_path.write_text(
        json.dumps(
            {
                "id": "w1",
                "start_scene": "s2",
                "scenes": {
                    "s2": {"path": "scenes/b.json"},
                    "s1": {"path": "scenes/a.json"},
                },
                "links": [{}, {}],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    overlay = DevBrowserOverlay(as_any(_stub_window()))
    overlay.mode = "worlds"
    overlay._items = [{"label": "my_world.json", "world_path": str(world_path)}]
    overlay.selected_index = 0

    lines = overlay._get_preview_lines()
    assert lines[0] == "Preview (World)"
    parsed = _lines_to_map(lines)

    assert parsed["file"] == "my_world.json"
    assert parsed["world_id"] == "w1"
    assert parsed["scene_count"] == "2"
    assert parsed["scenes"] == "s1,s2"
    assert parsed["start_scene"] == "s2 (ok)"
    assert parsed["link_count"] == "2"


def test_world_start_scene_missing_is_reported(tmp_path: Path) -> None:
    world_path = tmp_path / "my_world.json"
    world_path.write_text(
        json.dumps(
            {
                "id": "w1",
                "start_scene": "missing",
                "scenes": {
                    "s1": {"path": "scenes/a.json"},
                },
                "links": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    overlay = DevBrowserOverlay(as_any(_stub_window()))
    overlay.mode = "worlds"
    overlay._items = [{"label": "my_world.json", "world_path": str(world_path)}]
    overlay.selected_index = 0

    parsed = _lines_to_map(overlay._get_preview_lines())
    assert parsed["start_scene"] == "missing (missing)"


def test_p_toggles_preview_without_affecting_state() -> None:
    overlay = DevBrowserOverlay(as_any(_stub_window()))
    overlay.visible = True
    overlay.mode = "scenes"
    overlay.filter_text = "abc"
    overlay.selected_index = 1
    overlay.jump_mode = True
    overlay.jump_text = "Z"
    overlay.jump_list_open = True
    overlay.jump_list_index = 3

    before = (
        overlay.mode,
        overlay.filter_text,
        overlay.selected_index,
        overlay.jump_mode,
        overlay.jump_text,
        overlay.jump_list_open,
        overlay.jump_list_index,
    )

    initial = overlay.preview_visible
    assert overlay.on_key_press(optional_arcade.arcade.key.P, 0) is True
    assert overlay.preview_visible is (not initial)
    assert (
        overlay.mode,
        overlay.filter_text,
        overlay.selected_index,
        overlay.jump_mode,
        overlay.jump_text,
        overlay.jump_list_open,
        overlay.jump_list_index,
    ) == before

