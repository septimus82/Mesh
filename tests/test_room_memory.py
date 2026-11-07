"""Room memory: what was collected or defeated in a room stays gone, across room changes and saves.

Milestone 8, found in the real window (tooling/acceptance_persistence.py): a picked-up coin was back
after leaving the room and returning, and after loading a save made in that room; a loaded save's
object states (a dummy's HP) were applied to the room being left, not the saved one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.scene_runtime import room_memory

pytestmark = [pytest.mark.fast]


class _State:
    def __init__(self) -> None:
        self.vars: dict[str, Any] = {}

    def get_var(self, name: str, default: Any = None) -> Any:
        return self.vars.get(name, default)

    def set_var(self, name: str, value: Any) -> None:
        self.vars[name] = value


def _sprite(entity_id: str) -> SimpleNamespace:
    return SimpleNamespace(mesh_entity_data={"id": entity_id})


def _controller(tmp_path, room: str, spawned: set[str], alive: list[str]) -> SimpleNamespace:
    window = SimpleNamespace(game_state_controller=_State(), save_manager=SimpleNamespace(save_dir=tmp_path / "saves"))
    return SimpleNamespace(window=window, room_path=room, _room_spawned_ids=spawned,
                           all_sprites=[_sprite(i) for i in alive])


def test_objects_removed_during_play_are_remembered_per_room(tmp_path) -> None:
    controller = _controller(tmp_path, "packs\\rooms\\hall.json", {"coin", "npc", "chest"}, ["npc", "chest", "bullet"])
    room_memory.remember_removed(controller)
    assert room_memory.removed_ids(controller.window, "packs/rooms/hall.json") == {"coin"}
    assert room_memory.removed_ids(controller.window, "packs/rooms/yard.json") == set()


def test_what_was_remembered_stays_remembered(tmp_path) -> None:
    controller = _controller(tmp_path, "hall.json", {"coin", "npc"}, ["npc"])
    room_memory.remember_removed(controller)
    # Back in the room the coin no longer spawns; later the NPC is defeated too.
    controller._room_spawned_ids, controller.all_sprites = {"npc"}, []
    room_memory.remember_removed(controller)
    assert room_memory.removed_ids(controller.window, "hall.json") == {"coin", "npc"}


def test_nothing_is_recorded_without_a_room_or_spawn_list(tmp_path) -> None:
    controller = _controller(tmp_path, "", {"coin"}, [])
    room_memory.remember_removed(controller)
    assert controller.window.game_state_controller.vars == {}


def test_save_slots_are_told_apart_from_rooms(tmp_path) -> None:
    window = SimpleNamespace(save_manager=SimpleNamespace(save_dir=tmp_path / "saves"))
    assert room_memory.is_save_slot(window, str(tmp_path / "saves" / "quicksave.json"))
    assert not room_memory.is_save_slot(window, str(tmp_path / "packs" / "hall.json"))


def test_a_save_records_the_room_it_was_made_in_not_the_save_file(monkeypatch) -> None:
    from engine.save_runtime import payloads

    state = _State()
    controller = SimpleNamespace(
        current_scene_path="saves/quicksave.json", room_path="packs/rooms/hall.json", _room_spawned_ids=set(),
        all_sprites=[], build_scene_snapshot=lambda compact=False: {"name": "Hall", "entities": []})
    state.export_state = lambda: {"flags": {}}  # type: ignore[attr-defined]
    window = SimpleNamespace(scene_controller=controller, game_state_controller=state)
    monkeypatch.setattr(payloads, "serialize_entities", lambda _c: [])
    snapshot, _ = payloads.build_slot_payload(window, "quicksave", compact=False, timestamp="t")
    assert snapshot["meta"]["scene_path"] == "packs/rooms/hall.json"


def test_load_scene_leaves_out_remembered_objects_and_applies_a_loaded_saves_object_states(monkeypatch) -> None:
    """The two load-time halves, through the real load_scene with a stand-in controller."""
    from engine import scene_lifecycle_controller as lifecycle

    state = _State()
    state.set_var(room_memory.VAR, {"packs/rooms/hall.json": {"removed": ["coin"]}})
    scene = {"name": "Hall", "entities": [{"id": "coin", "name": "Coin"}, {"id": "npc", "name": "Npc"}]}
    created: list[str] = []
    applied: list[Any] = []

    class Entities:
        def enqueue_spawn(self, sprite, **_k) -> None: ...
        def apply_pending_ops(self, *_a, **_k) -> None: ...
        def invalidate(self, *_a) -> None: ...

    class Stop(Exception):
        pass

    def create(entity: dict[str, Any]) -> Any:
        created.append(entity["id"])
        return SimpleNamespace()

    controller = SimpleNamespace(
        window=SimpleNamespace(scene_loader=SimpleNamespace(load_scene=lambda _p: scene, last_saved_from=None),
                               game_state_controller=state, get_flag=lambda *_a, **_k: False,
                               save_manager=SimpleNamespace(save_dir="saves")),
        layers={"entities": []}, entities=Entities(), _create_sprite=create, all_sprites=[],
        _pending_saved_entities=[{"entity_id": "Npc", "x": 1.0, "y": 2.0}],
        sensors_runtime=SimpleNamespace(reset=lambda: None), _clear_scene_event_subscriptions=lambda: None,
        _apply_theme_runtime=lambda _s: None,
    )
    monkeypatch.setattr("engine.save_runtime.entity_state.apply_entities", lambda c, e: applied.append(e))

    def stop(*_a, **_k):
        raise Stop

    # Everything between reading the scene and spawning is unrelated set-up: let it no-op, stop after the restore.
    monkeypatch.setattr(lifecycle, "build_scene_index_from_sprites", stop)
    for name in ("parse_background_layers", "parse_foreground_layers", "parse_background_planes",
                 "parse_depth_tint_settings", "parse_outline_settings", "configure_scene_lighting"):
        monkeypatch.setattr(lifecycle, name, lambda *_a, **_k: [])
    for attr in ("_apply_scene_settings", "_apply_scene_state", "_configure_camera_from_scene",
                 "_apply_collision_rules_overrides", "_ensure_layers", "_clear_layers", "_load_tilemap_layers"):
        setattr(controller, attr, lambda *_a, **_k: None)
    controller._default_collision_rules = {}
    controller._background_plane_texture_cache = {}
    with pytest.raises(Stop):
        lifecycle.load_scene(controller, "packs/rooms/hall.json")
    assert created == ["npc"]
    assert controller._room_spawned_ids == {"npc"}
    assert applied == [[{"entity_id": "Npc", "x": 1.0, "y": 2.0}]]
    assert controller._pending_saved_entities is None
