from __future__ import annotations


def test_recent_scenes_records_unique_and_capped() -> None:
    from engine.game import GameWindow

    window = type("W", (), {"recent_scenes": []})()

    GameWindow.record_recent_scene(window, r"scenes\foo.json")
    assert window.recent_scenes == ["scenes/foo.json"]

    for i in range(30):
        GameWindow.record_recent_scene(window, f"scenes/s{i}.json")

    assert len(window.recent_scenes) == 20
    assert window.recent_scenes[0] == "scenes/s29.json"

    GameWindow.record_recent_scene(window, "scenes/s10.json")
    assert window.recent_scenes[0] == "scenes/s10.json"
    assert window.recent_scenes.count("scenes/s10.json") == 1

