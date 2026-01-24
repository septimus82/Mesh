from __future__ import annotations

from engine.editor_light_occluder_ops import (
    LIGHT_COLOR_PRESETS,
    LIGHTING_PRESETS,
    add_light,
    add_occluder,
    capture_lighting_preset,
    apply_lighting_preset,
    apply_occluder_command,
    build_add_point_cmd,
    build_insert_point_cmd,
    build_move_point_cmd,
    build_remove_point_cmd,
    cycle_light_color,
    find_closest_edge_insert_index,
    invert_occluder_command,
    snap_world_point,
    update_light_property,
)


def test_add_light_persists_payload() -> None:
    scene: dict = {}
    index, light = add_light(scene, 10.0, 20.0)
    assert index == 0
    assert scene["lights"][0] is light
    assert light["x"] == 10.0
    assert light["y"] == 20.0
    assert light["radius"] == 160.0
    assert light["color"] == LIGHT_COLOR_PRESETS[1]
    assert light["mode"] == "soft"


def test_add_occluder_persists_polygon() -> None:
    scene: dict = {}
    index, occ = add_occluder(scene, [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0)])
    assert index == 0
    assert scene["occluders"][0] is occ
    assert occ["type"] == "poly"
    assert occ["points"] == [[0.0, 0.0], [2.0, 0.0], [2.0, 1.0]]


def test_cycle_light_color_updates_payload() -> None:
    scene: dict = {}
    _, light = add_light(scene, 0.0, 0.0)
    before = light["color"]
    _, new_color = cycle_light_color(light)
    assert light["color"] == new_color
    assert new_color != before


def test_occluder_add_point_undo_redo() -> None:
    scene: dict = {}
    _, occ = add_occluder(scene, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    cmd = build_add_point_cmd(occ_index=0, point_index=1, point=(0.5, 0.0), occ_id=occ["id"])
    apply_occluder_command(scene, {"kind": cmd.kind, "payload": cmd.payload})
    assert scene["occluders"][0]["points"][1] == [0.5, 0.0]
    undo = invert_occluder_command(cmd)
    apply_occluder_command(scene, {"kind": undo.kind, "payload": undo.payload})
    assert scene["occluders"][0]["points"] == [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]
    apply_occluder_command(scene, {"kind": cmd.kind, "payload": cmd.payload})
    assert scene["occluders"][0]["points"][1] == [0.5, 0.0]


def test_occluder_remove_point_undo_redo() -> None:
    scene: dict = {}
    _, occ = add_occluder(scene, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    cmd = build_remove_point_cmd(occ_index=0, point_index=1, point=[1.0, 0.0], occ_id=occ["id"])
    apply_occluder_command(scene, {"kind": cmd.kind, "payload": cmd.payload})
    assert scene["occluders"][0]["points"] == [[0.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    undo = invert_occluder_command(cmd)
    apply_occluder_command(scene, {"kind": undo.kind, "payload": undo.payload})
    assert scene["occluders"][0]["points"] == [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]


def test_occluder_move_point_undo_redo() -> None:
    scene: dict = {}
    _, occ = add_occluder(scene, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    cmd = build_move_point_cmd(
        occ_index=0,
        point_index=1,
        before=[1.0, 0.0],
        after=[2.0, 0.5],
        occ_id=occ["id"],
    )
    apply_occluder_command(scene, {"kind": cmd.kind, "payload": cmd.payload})
    assert scene["occluders"][0]["points"][1] == [2.0, 0.5]
    undo = invert_occluder_command(cmd)
    apply_occluder_command(scene, {"kind": undo.kind, "payload": undo.payload})
    assert scene["occluders"][0]["points"][1] == [1.0, 0.0]


def test_occluder_insert_point_closest_edge() -> None:
    scene: dict = {}
    _, occ = add_occluder(scene, [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)])
    insert_idx, proj = find_closest_edge_insert_index(scene["occluders"][0]["points"], (1.0, 0.2))
    assert insert_idx == 1
    cmd = build_insert_point_cmd(
        occ_index=0,
        insert_index=insert_idx,
        point=proj,
        occ_id=occ["id"],
    )
    apply_occluder_command(scene, {"kind": cmd.kind, "payload": cmd.payload})
    assert len(scene["occluders"][0]["points"]) == 4
    assert scene["occluders"][0]["points"][1] == [1.0, 0.0]
    undo = invert_occluder_command(cmd)
    apply_occluder_command(scene, {"kind": undo.kind, "payload": undo.payload})
    assert scene["occluders"][0]["points"] == [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0]]


def test_snap_world_point_grid8() -> None:
    snapped = snap_world_point((9.0, 14.0), "grid8", None)
    assert snapped == (8.0, 16.0)


def test_snap_world_point_grid16() -> None:
    snapped = snap_world_point((17.0, 2.0), "grid16", None)
    assert snapped == (16.0, 0.0)


def test_snap_world_point_tile_center() -> None:
    snapped = snap_world_point((17.0, 15.0), "tile_center", 16)
    assert snapped == (24.0, 8.0)


def test_insert_point_with_snap() -> None:
    scene: dict = {}
    _, occ = add_occluder(scene, [(0.0, 0.0), (16.0, 0.0), (16.0, 16.0)])
    insert_idx, proj = find_closest_edge_insert_index(scene["occluders"][0]["points"], (5.0, 1.0))
    snapped = snap_world_point(proj, "grid8", None)
    cmd = build_insert_point_cmd(
        occ_index=0,
        insert_index=insert_idx,
        point=snapped,
        occ_id=occ["id"],
    )
    apply_occluder_command(scene, {"kind": cmd.kind, "payload": cmd.payload})
    assert scene["occluders"][0]["points"][insert_idx] == [8.0, 0.0]
    undo = invert_occluder_command(cmd)
    apply_occluder_command(scene, {"kind": undo.kind, "payload": undo.payload})
    assert scene["occluders"][0]["points"] == [[0.0, 0.0], [16.0, 0.0], [16.0, 16.0]]


def test_update_light_property_radius_persists() -> None:
    scene: dict = {}
    add_light(scene, 0.0, 0.0)
    ok = update_light_property(scene, 0, "radius_px", 200.0)
    assert ok is True
    assert scene["lights"][0]["radius"] == 200.0


def test_update_light_property_flicker_amount_clamped() -> None:
    scene: dict = {}
    add_light(scene, 0.0, 0.0)
    ok = update_light_property(scene, 0, "flicker_amount", 2.5)
    assert ok is True
    assert scene["lights"][0]["flicker_amount"] == 1.0


def test_update_light_property_cookie_rotation_wraps() -> None:
    scene: dict = {}
    add_light(scene, 0.0, 0.0)
    ok = update_light_property(scene, 0, "cookie_rotation_deg", 370.0)
    assert ok is True
    assert scene["lights"][0]["cookie_rotation_deg"] == 10.0


def test_apply_lighting_preset_updates_settings() -> None:
    for preset_id, preset in LIGHTING_PRESETS.items():
        scene: dict = {}
        apply_lighting_preset(scene, preset_id)
        settings = scene.get("settings")
        assert isinstance(settings, dict)
        assert settings["ambient_light_rgba"] == list(preset["ambient_light_rgba"])
        assert settings["ambient_darkness_alpha"] == int(preset["ambient_darkness_alpha"])


def test_apply_lighting_preset_idempotent() -> None:
    scene: dict = {}
    apply_lighting_preset(scene, "torch_cave")
    settings = dict(scene.get("settings", {}))
    apply_lighting_preset(scene, "torch_cave")
    assert scene.get("settings") == settings


def test_capture_custom_lighting_preset_writes_settings() -> None:
    scene = {
        "settings": {
            "ambient_light_rgba": [10, 20, 30, 255],
            "ambient_darkness_alpha": 200,
            "default_light_color_rgba": [1, 2, 3, 255],
            "default_flicker_enabled": True,
        }
    }
    capture_lighting_preset(scene, "custom_1")
    presets = scene["settings"]["custom_lighting_presets"]
    assert presets["custom_1"]["ambient_light_rgba"] == [10, 20, 30, 255]
    assert presets["custom_1"]["ambient_darkness_alpha"] == 200
    assert presets["custom_1"]["default_light_color_rgba"] == [1, 2, 3, 255]
    assert presets["custom_1"]["default_flicker_enabled"] is True


def test_capture_custom_preset_idempotent() -> None:
    scene = {"settings": {"ambient_light_rgba": [1, 2, 3, 255]}}
    capture_lighting_preset(scene, "custom_1")
    before = scene["settings"]["custom_lighting_presets"]["custom_1"]
    capture_lighting_preset(scene, "custom_1")
    assert scene["settings"]["custom_lighting_presets"]["custom_1"] == before


def test_apply_custom_preset_restores_settings() -> None:
    scene = {"settings": {"ambient_light_rgba": [1, 1, 1, 255], "ambient_darkness_alpha": 250}}
    capture_lighting_preset(scene, "custom_1")
    scene["settings"]["ambient_light_rgba"] = [9, 9, 9, 255]
    scene["settings"]["ambient_darkness_alpha"] = 123
    apply_lighting_preset(scene, "custom_1")
    assert scene["settings"]["ambient_light_rgba"] == [1, 1, 1, 255]
    assert scene["settings"]["ambient_darkness_alpha"] == 250


def test_apply_missing_custom_preset_noop() -> None:
    scene = {"settings": {"ambient_light_rgba": [9, 9, 9, 255]}}
    apply_lighting_preset(scene, "custom_2")
    assert scene["settings"]["ambient_light_rgba"] == [9, 9, 9, 255]
