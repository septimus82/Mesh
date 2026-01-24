from __future__ import annotations


def test_normalize_scene_path_forward_slashes_and_dot_prefix() -> None:
    from engine.tooling.path_norm import normalize_scene_path

    assert normalize_scene_path(r"packs\core_regions\scenes\Ashen_dungeon.json") == "packs/core_regions/scenes/Ashen_dungeon.json"
    assert normalize_scene_path("./scenes/door_field.json") == "scenes/door_field.json"
    assert normalize_scene_path(r".\scenes\door_field.json") == "scenes/door_field.json"
    assert normalize_scene_path("Not a path") == "Not a path"
