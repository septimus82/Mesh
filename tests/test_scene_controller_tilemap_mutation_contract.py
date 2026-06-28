from __future__ import annotations

import builtins
from types import SimpleNamespace
from typing import Any

import pytest

from engine.tilemap_batch import TilemapBatchState

pytestmark = [pytest.mark.fast]


class _SpriteList(list):
    def clear(self) -> None:
        super().clear()


class _Tileset:
    first_gid = 1

    def contains(self, gid: int) -> bool:
        return gid == 7


def _make_controller() -> Any:
    from engine.scene_controller import SceneController

    controller = object.__new__(SceneController)
    controller._tilemap_batch_state = None
    controller._tilemap_batcher = None
    controller._tilemap_background_layers = []
    controller._tilemap_foreground_layers = []
    controller._tilemap_draw_layers = []
    controller._background_layers = ["bg"]
    controller.tilemap_instance = None
    controller.navigation = SimpleNamespace(invalidate=lambda: None)
    controller.window = SimpleNamespace(
        tilemap_chunk_size=8,
        world_width=None,
        world_height=None,
        camera_controller=SimpleNamespace(bounds=None),
        tilemap_manager=SimpleNamespace(_get_tile_texture=lambda _tileset, _local_id: "tex"),
    )
    return controller


def test_tilemap_state_methods_are_bound_from_part_module() -> None:
    from engine.scene_controller import SceneController

    for name in (
        "_load_tilemap_layers",
        "_init_tilemap_batching",
        "_apply_tilemap_world_bounds",
        "_mark_tilemap_layer_dirty",
        "invalidate_tilemap_batches",
        "_mark_tilemap_tile_dirty",
        "set_tile",
        "_clear_tilemap_batching",
        "_clear_tilemap_layers",
    ):
        method = getattr(SceneController, name, None)
        assert callable(method), f"SceneController.{name} missing or not callable"
        assert getattr(method, "__module__", None) == "engine.scene_controller_parts.tilemap_state"


def test_mark_tilemap_layer_dirty_marks_expected_layer_and_increments_version() -> None:
    controller = _make_controller()
    controller._tilemap_batch_state = TilemapBatchState(4, 4, 16, 16)

    controller._mark_tilemap_layer_dirty("ground")
    controller._mark_tilemap_layer_dirty("ground")

    state = controller._tilemap_batch_state
    assert state.layer_versions == {"ground": 2}
    assert state.dirty_all_layers == {"ground"}
    assert state.dirty_chunks == {}


def test_mark_tilemap_tile_dirty_records_expected_chunk_for_valid_input() -> None:
    controller = _make_controller()
    controller._tilemap_batch_state = TilemapBatchState(4, 4, 16, 16, chunk_size_tiles=2)

    controller._mark_tilemap_tile_dirty("ground", 3, 1)

    assert controller._tilemap_batch_state.dirty_chunks == {"ground": {(1, 0)}}


def test_invalidate_tilemap_batches_is_safe_when_batching_state_missing() -> None:
    controller = _make_controller()

    assert controller.invalidate_tilemap_batches() == 0


def test_invalidate_tilemap_batches_falls_back_to_marking_all_known_layers_dirty() -> None:
    controller = _make_controller()
    state = TilemapBatchState(4, 4, 16, 16)
    state.layer_versions = {"ground": 1, "decor": 3}
    controller._tilemap_batch_state = state
    controller._tilemap_batcher = SimpleNamespace(invalidate_batches=lambda: 0)

    count = controller.invalidate_tilemap_batches()

    assert count == 2
    assert state.dirty_all_layers == {"ground", "decor"}
    assert state.layer_versions == {"ground": 2, "decor": 4}


def test_set_tile_updates_target_layer_marks_dirty_and_leaves_other_layers_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_parts.tilemap_state as tilemap_state

    controller = _make_controller()
    target_sprites = [SimpleNamespace(center_x=24.0, center_y=24.0), SimpleNamespace(center_x=8.0, center_y=24.0)]
    controller.tilemap_instance = SimpleNamespace(
        layer_data={"ground": [0, 0, 0, 0], "decor": [5, 5, 5, 5]},
        layer_dimensions=(2, 2),
        tile_size=(16, 16),
        layer_offsets={"ground": (0.0, 0.0), "decor": (0.0, 0.0)},
        layer_lookup={"ground": target_sprites, "decor": []},
        tilesets=[_Tileset()],
    )
    dirty_calls: list[tuple[str, int, int]] = []
    controller._mark_tilemap_tile_dirty = lambda layer, col, row: dirty_calls.append((layer, col, row))
    monkeypatch.setattr(tilemap_state.optional_arcade.arcade, "Sprite", lambda: SimpleNamespace())

    result = controller.set_tile("ground", 1, 0, 7)

    assert result == (0, 7)
    assert controller.tilemap_instance.layer_data["ground"] == [0, 7, 0, 0]
    assert controller.tilemap_instance.layer_data["decor"] == [5, 5, 5, 5]
    assert dirty_calls == [("ground", 1, 0)]
    assert len(target_sprites) == 2
    assert target_sprites[0].center_x == 8.0
    new_sprite = target_sprites[1]
    assert getattr(new_sprite, "texture", None) == "tex"
    assert (new_sprite.center_x, new_sprite.center_y, new_sprite.scale) == (24.0, 24.0, 1.0)


def test_clear_tilemap_layers_clears_observable_state_and_tolerates_missing_occluder_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    cleared_bg = _SpriteList([1, 2])
    cleared_fg = _SpriteList([3])
    collision_sprites = _SpriteList([4])
    nav_calls: list[str] = []
    batcher_calls: list[str] = []
    controller.navigation = SimpleNamespace(invalidate=lambda: nav_calls.append("invalidate"))
    controller._tilemap_batcher = SimpleNamespace(clear=lambda: batcher_calls.append("clear"))
    controller._tilemap_batch_state = TilemapBatchState(2, 2, 16, 16)
    controller._tilemap_background_layers = [cleared_bg]
    controller._tilemap_foreground_layers = [cleared_fg]
    controller._tilemap_draw_layers = ["draw-layer"]
    controller._background_layers = ["background-layer"]
    controller.tilemap_instance = SimpleNamespace(collision_sprites=collision_sprites)

    original_import = builtins.__import__

    def _import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0) -> Any:
        if name == "engine.lighting.occluders":
            raise ImportError("missing in test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    controller._clear_tilemap_layers()

    assert batcher_calls == ["clear"]
    assert nav_calls == ["invalidate"]
    assert controller._tilemap_background_layers == []
    assert controller._tilemap_foreground_layers == []
    assert controller._tilemap_draw_layers == []
    assert controller._background_layers == ["background-layer"]
    assert controller.tilemap_instance is None
    assert controller._tilemap_batcher is None
    assert controller._tilemap_batch_state is None
    assert list(cleared_bg) == []
    assert list(cleared_fg) == []
    assert list(collision_sprites) == []


def test_init_tilemap_batching_initializes_state_and_marks_all_layers_dirty(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_parts.tilemap_state as tilemap_state

    controller = _make_controller()
    created: list[tuple[Any, Any]] = []
    batcher = object()
    monkeypatch.setattr(tilemap_state, "TilemapBatcher", lambda window, state: created.append((window, state)) or batcher)
    instance = SimpleNamespace(
        map_size=(4, 3),
        tile_size=(16, 8),
        layer_data={"ground": [0], "decor": [0]},
    )

    controller._init_tilemap_batching(instance)

    state = controller._tilemap_batch_state
    assert state is not None
    assert state.map_width == 4
    assert state.map_height == 3
    assert state.tile_width == 16
    assert state.tile_height == 8
    assert state.chunk_size_tiles == 8
    assert state.dirty_all_layers == {"ground", "decor"}
    assert state.layer_versions == {"ground": 1, "decor": 1}
    assert controller._tilemap_batcher is batcher
    assert created == [(controller.window, state)]


def test_init_tilemap_batching_with_empty_dimensions_clears_existing_batching() -> None:
    controller = _make_controller()
    calls: list[str] = []
    controller._clear_tilemap_batching = lambda: calls.append("clear")
    instance = SimpleNamespace(map_size=(0, 3), tile_size=(16, 8), layer_data={"ground": [0]})

    controller._init_tilemap_batching(instance)

    assert calls == ["clear"]


def test_apply_tilemap_world_bounds_sets_world_size_and_camera_bounds_when_empty() -> None:
    controller = _make_controller()
    instance = SimpleNamespace(map_size=(5, 4), tile_size=(16, 8))

    controller._apply_tilemap_world_bounds(instance)

    assert controller.window.world_width == 80
    assert controller.window.world_height == 32
    assert controller.window.camera_controller.bounds == (0.0, 0.0, 80.0, 32.0)
