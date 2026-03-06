from engine.scene_controller import SceneController


def test_scene_controller_import_surface_smoke() -> None:
    expected_callables = [
        "load_scene",
        "reload_scene",
        "reload_current_scene",
        "update",
        "draw",
        "request_scene_reload",
        "request_scene_change",
        "queue_scene_change",
        "_perform_scene_change",
        "_snapshot_player_state",
        "_restore_player_state",
        "_snapshot_camera_state",
        "_restore_camera_state",
        "_apply_scene_state",
        "build_scene_snapshot",
        "get_loaded_scene_payload",
        "get_authored_scene_payload",
        "debug_apply_authored_scene_payload",
        "apply_spawn",
        "get_spawn",
        "find_entity",
        "get_all_entities",
        "find_sprite_by_name",
    ]

    for name in expected_callables:
        assert hasattr(SceneController, name)
        assert callable(getattr(SceneController, name))
