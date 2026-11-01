"""F7 (#422): a hot reload checks the replacement scene before it takes the running one down.

``reload_scene`` (immediate: Ctrl+R, the console, the editor) cleared the scene's sprites, subscriptions and queued
events before reading the file; a queued reload (``request_scene_reload``, the asset browser) cleared queued events
and the asset caches, then raised out of the update loop. A missing, malformed or invalid scene destroyed the one that
was running. Now both routes load the scene through the scene loader first, strictly (no empty fallback), and a
refusal changes nothing; the scene that was running keeps running. Every attempt leaves one result
(``SceneController.last_reload_result``): the hot-reload error people see, and the editor's live read for an AI.

Real, hidden GameWindows (tests/conftest.py) and real scene files throughout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from engine.game_runtime import scene_ops
from engine.scene_lifecycle_controller import handle_pending_scene_load
from engine.scene_loader import document_key
from engine.scene_runtime import reload_check
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

PICTURE = "assets/placeholder.png"
HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 100, "y": 100, "sprite": PICTURE,
        "behaviours": ["PlayerController"]}
CRATE = {"id": "crate", "name": "Crate", "x": 200, "y": 120, "sprite": PICTURE}
BELL = {"id": "bell", "name": "Bell", "x": 60, "y": 160, "sprite": PICTURE, "behaviours": ["EventLogger"]}
BARREL = {"id": "barrel", "name": "Barrel", "x": 240, "y": 60, "sprite": PICTURE}


def _scene(*entities: dict, **top: Any) -> dict:
    return {"name": "Yard", "schema_version": 1, "version": 1, "layers": [], "entities": list(entities), **top}


YARD = _scene(HERO, CRATE, BELL)


@pytest.fixture()
def game(tmp_path: Path) -> Iterator[tuple[Any, Path, list[str]]]:
    """A game running the Yard, with the live state a reload must keep: a subscription the scene tracks, a queued
    event, a game-state value, the player moved, the camera somewhere."""
    from engine.game import GameWindow

    path = tmp_path / "yard.json"
    path.write_text(json.dumps(YARD), encoding="utf-8")
    cfg = EngineConfig(width=320, height=200, title="F7 hot reload", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None)
    window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
    unsubscribed: list[str] = []
    try:
        window.scene_controller.load_scene(str(path))
        window.track_scene_subscription(lambda: unsubscribed.append("scene handler"))
        window._mesh_event_queue = [{"name": "door_opened"}]
        window.game_state_controller.set_var("coins", 7)
        player = window.scene_controller._find_player_sprite()
        player.center_x, player.center_y = 150.0, 140.0
        yield window, path, unsubscribed
    finally:
        dispose_game_window(window)


def _snapshot(window: Any) -> dict[str, Any]:
    """Everything a refused reload must leave exactly as it was (sprites and layers by identity)."""
    sc = window.scene_controller
    return {
        "sprites": [(id(s), (s.mesh_entity_data or {}).get("id"), s.center_x, s.center_y) for s in sc.all_sprites],
        "layers": {name: [id(s) for s in sprites] for name, sprites in sc.layers.items()},
        "scene": (sc.current_scene_path, sc.room_path, id(sc._loaded_scene_data), id(sc.scene_settings)),
        "scene_subscriptions": list(sc._scene_event_unsubscribes),
        "bus": (list(window.event_bus._wildcard_subscribers), {k: list(v) for k, v in window.event_bus._subscribers.items()}),
        "events": list(window._mesh_event_queue),
        "state": json.dumps(window.game_state_controller.export_state(), sort_keys=True, default=str),
        "camera": (window.get_camera_center(), window.camera_controller.zoom_state.current,
                   window.camera_controller.zoom_state.target),
        "lighting": id(getattr(window, "lighting", None)),
    }


def _subscriptions(window: Any) -> tuple[int, int, list[tuple[str, list[str]]]]:
    """How many event-bus subscribers (wildcard, by type) and each object's behaviours: a reload adds none."""
    bus = window.event_bus
    behaviours = sorted(((s.mesh_entity_data or {}).get("id"), [type(b).__name__ for b in s.mesh_behaviours_runtime])
                        for s in window.scene_controller.all_sprites)
    return len(bus._wildcard_subscribers), sum(len(v) for v in bus._subscribers.values()), behaviours


def _ids(window: Any) -> list[str]:
    return sorted((s.mesh_entity_data or {}).get("id") for s in window.scene_controller.all_sprites)


def _reload(window: Any, route: str) -> Any:
    """Reload as the person does: Ctrl+R (immediate), or the queued reload with the asset caches cleared."""
    if route == "immediate":
        return scene_ops.reload_scene_from_disk(window)
    window.request_scene_reload(clear_assets=True)
    return handle_pending_scene_load(window.scene_controller)


BROKEN = {
    "missing": ("scene_missing", lambda p: p.unlink()),
    "invalid_json": ("invalid_json", lambda p: p.write_text('{"name": "Yard", "entities": [', encoding="utf-8")),
    "schema": ("schema_invalid", lambda p: p.write_text(json.dumps(_scene({**CRATE, "width": 32})), encoding="utf-8")),
    "empty_fallback": ("scene_invalid",  # (passes the schema; the loader would load an empty scene in its place)
                       lambda p: p.write_text(json.dumps(_scene(HERO, settings={"world_width": "wide"})), encoding="utf-8")),
    "not_utf8": ("scene_unreadable", lambda p: p.write_bytes(b'\xff\xfe{"name": "Yard"}')),
    "a_folder": ("scene_unreadable", lambda p: (p.unlink(), p.mkdir())),
}


@pytest.mark.parametrize("route", ["immediate", "queued"])
@pytest.mark.parametrize("broken", list(BROKEN))
def test_a_scene_that_cant_be_loaded_is_refused_and_the_running_one_is_untouched(game, monkeypatch, broken: str,
                                                                                 route: str) -> None:
    window, path, unsubscribed = game
    cleared: list[str] = []
    monkeypatch.setattr(window.assets, "clear", lambda: cleared.append("textures"))
    monkeypatch.setattr(window.audio, "clear_cache", lambda: cleared.append("sounds"))
    before = _snapshot(window)
    reason, break_it = BROKEN[broken]
    break_it(path)

    outcome = _reload(window, route)

    assert outcome is (False if route == "immediate" else True)  # (queued: the request was handled, not raised)
    assert _snapshot(window) == before, "sprites, layers, subscriptions, events, state, camera: all as they were"
    assert _ids(window) == ["bell", "crate", "hero"] and not unsubscribed and not cleared
    result = window.scene_controller.last_reload_result
    assert (result["ok"], result["reason"], result["stage"], result["route"]) == (False, reason, "preflight", route)
    assert result["previous_scene_preserved"] is True and result["can_retry"] is True
    assert result["scene_path"] == str(path) and 1 <= len(result["errors"]) <= reload_check.MAX_ERRORS
    assert result["message"].startswith("Scene not reloaded: yard.json")
    assert "still running, unchanged" in result["message"]
    assert window.hot_reload_error_visible and window.hot_reload_error_message == result["message"]
    assert window.scene_controller._pending_scene_path is None and not window.scene_controller._clear_assets_on_next_load


@pytest.mark.parametrize("route", ["immediate", "queued"])
def test_the_corrected_scene_then_reloads_normally(game, route: str) -> None:
    window, path, unsubscribed = game
    path.write_text("{", encoding="utf-8")
    _reload(window, route)
    assert window.hot_reload_error_visible
    coins = window.game_state_controller.get_var("coins")
    zoom = window.camera_controller.zoom_state.current
    wildcard, typed, _behaviours = _subscriptions(window)

    path.write_text(json.dumps(_scene(HERO, BELL, BARREL)), encoding="utf-8")  # (fixed: the crate gone, a barrel)
    assert _reload(window, route) is True

    assert _ids(window) == ["barrel", "bell", "hero"], "no stale crate, the barrel there"
    result = window.scene_controller.last_reload_result
    assert (result["ok"], result["reason"], result["stage"], result["route"]) == (True, None, None, route)
    assert not window.hot_reload_error_visible and window.hot_reload_error_message == ""
    assert _subscriptions(window)[:2] == (wildcard, typed), "no event-bus subscription added"
    assert dict(_subscriptions(window)[2])["bell"] == ["EventLogger"], "the bell's behaviour once, not twice"
    assert unsubscribed == ["scene handler"], "the scene's tracked subscription released once"
    assert window.game_state_controller.get_var("coins") == coins
    assert window.camera_controller.zoom_state.current == zoom
    if route == "immediate":  # (Ctrl+R keeps the player where it was; a queued reload rebuilds it as authored)
        player = window.scene_controller._find_player_sprite()
        assert (player.center_x, player.center_y) == (150.0, 140.0)


@pytest.mark.parametrize("route", ["immediate", "queued"])
def test_reloading_again_and_again_keeps_one_of_everything(game, route: str) -> None:
    window, _path, _unsubscribed = game
    fresh = _subscriptions(window)
    loader, reads = window.scene_loader, []
    real = loader.load_scene
    loader.load_scene = lambda path, **kw: (reads.append(path), real(path, **kw))[1]
    for _ in range(3):
        assert _reload(window, route) is True
    assert len(reads) == 3, "each reload reads the scene once: it is built from the load that was checked"
    assert _ids(window) == ["bell", "crate", "hero"], "a reload came back with every object (it used to come back empty)"
    assert _subscriptions(window) == fresh, "one of every subscription and behaviour, as a fresh load has"
    assert sum(1 for _ in window.scene_controller.all_sprites) == 3


def test_an_open_studio_document_is_what_is_checked_not_the_file(game) -> None:
    window, path, _unsubscribed = game
    documents = window.scene_loader.documents
    documents[document_key(path)] = _scene(HERO, settings={"world_width": "wide"})  # (unsaved, and invalid)
    before = _snapshot(window)
    assert window.reload_scene() is False
    assert window.scene_controller.last_reload_result["reason"] == "scene_invalid"
    assert _snapshot(window) == before

    documents[document_key(path)] = _scene(HERO, BELL, BARREL)  # (unsaved, valid) while the file on disk is broken
    path.write_text("{", encoding="utf-8")
    assert window.reload_scene() is True
    assert _ids(window) == ["barrel", "bell", "hero"]


@pytest.mark.parametrize("route", ["immediate", "queued"])
def test_a_scene_that_fails_while_it_is_built_says_so_and_can_be_reloaded_again(game, monkeypatch, route: str) -> None:
    import engine.scene_lifecycle_controller as lifecycle

    window, _path, _unsubscribed = game
    real = lifecycle.configure_scene_lighting

    def lighting_fails(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("injected: the lighting couldn't be set up")

    monkeypatch.setattr(lifecycle, "configure_scene_lighting", lighting_fails)
    if route == "immediate":
        assert window.reload_scene() is False
    else:
        with pytest.raises(RuntimeError, match="injected"):  # (as before: a queued load that fails raises)
            _reload(window, route)
    result = window.scene_controller.last_reload_result
    assert (result["ok"], result["reason"], result["stage"]) == (False, "construction_failed", "construction")
    assert result["previous_scene_preserved"] is False and result["can_retry"] is True
    assert "while it was being built" in result["message"]
    monkeypatch.setattr(lifecycle, "configure_scene_lighting", real)
    assert window.reload_scene() is True and _ids(window) == ["bell", "crate", "hero"]


def test_an_ai_reads_the_same_result_in_the_editors_live_read(game) -> None:
    window, path, _unsubscribed = game
    path.write_text("{", encoding="utf-8")
    window.reload_scene()
    live = window.editor_controller.read_live_scene(compact=True)
    assert live["last_reload"] == window.scene_controller.last_reload_result
    assert live["last_reload"]["reason"] == "invalid_json" and live["last_reload"]["previous_scene_preserved"]


def test_an_ordinary_scene_change_is_not_a_reload(game, tmp_path: Path) -> None:
    window, _path, _unsubscribed = game
    other = tmp_path / "meadow.json"
    other.write_text(json.dumps(_scene(HERO, BARREL, name="Meadow")), encoding="utf-8")
    window.request_scene_change(str(other))
    assert handle_pending_scene_load(window.scene_controller) is True
    assert window.scene_controller.current_scene_path == str(other) and _ids(window) == ["barrel", "hero"]
    assert window.scene_controller.last_reload_result is None


def test_validation_errors_are_bounded() -> None:
    errors = [f"problem {i}" for i in range(25)]
    result = reload_check.result(ok=False, scene_path="s.json", route="immediate", reason="scene_invalid",
                                 stage="preflight", message="m", preserved=True, errors=errors)
    assert result["errors"] == errors[:reload_check.MAX_ERRORS] and result["errors_total"] == 25
