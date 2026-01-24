from engine.scene_controller import SceneController


def test_scene_controller_import_surface_smoke() -> None:
    expected_callables = [
        "load_scene",
        "reload_scene",
        "update",
        "draw",
        "request_scene_reload",
        "request_scene_change",
        "queue_scene_change",
        "apply_spawn",
        "get_spawn",
        "find_entity",
        "get_all_entities",
        "find_sprite_by_name",
    ]

    for name in expected_callables:
        assert hasattr(SceneController, name)
        assert callable(getattr(SceneController, name))

