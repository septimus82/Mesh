from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


class _SpySpriteList(list):
    def __init__(self, name: str, events: list[str], items: list[Any] | None = None) -> None:
        super().__init__(items or [])
        self._name = name
        self._events = events
        self.draw_calls = 0

    def __iter__(self):
        self._events.append(f"iter:{self._name}")
        return super().__iter__()

    def draw(self, **_kwargs: Any) -> None:
        self.draw_calls += 1
        self._events.append(f"draw:{self._name}")


class _SpyCamera:
    def __init__(self, events: list[str], label: str, *, fail_on_use: bool = False) -> None:
        self._events = events
        self._label = label
        self._fail_on_use = fail_on_use
        self.position = (0.0, 0.0)

    def use(self) -> None:
        self._events.append(f"camera:{self._label}")
        if self._fail_on_use:
            raise RuntimeError(f"camera {self._label} failed")


def _make_controller(events: list[str] | None = None) -> Any:
    from engine.scene_controller import SceneController

    log = events if events is not None else []
    controller = object.__new__(SceneController)
    controller.layers = {
        "background": _SpySpriteList("background", log),
        "entities": _SpySpriteList("entities", log),
        "foreground": _SpySpriteList("foreground", log),
    }
    controller._tilemap_background_layers = []
    controller._tilemap_foreground_layers = []
    controller._tilemap_draw_layers = []
    controller._tilemap_batch_state = None
    controller._tilemap_batcher = None
    controller.tilemap_instance = None
    controller._background_layers = []
    controller._background_planes = []
    controller._background_plane_texture_cache = {}
    controller._render_culled_count = 0
    controller._render_sort_mode = "y_sort"
    controller._shadows_enabled = True
    controller._shadows_contact_enabled = True
    controller._shadows_ao_enabled = False
    controller._depth_tint_settings = object()
    controller._outline_settings = object()
    controller.window = SimpleNamespace(
        width=200,
        height=100,
        show_debug=False,
        strict_mode=False,
        render_queue=None,
        render_batching_enabled=False,
        render_culling_enabled=False,
        tilemap_batching_enabled=False,
        get_camera_center=lambda: (100.0, 50.0),
        camera=_SpyCamera(log, "world"),
        camera_controller=SimpleNamespace(
            zoom_state=SimpleNamespace(current=1.0),
            gui_camera=_SpyCamera(log, "gui"),
            bounds=None,
            configure_from_scene=lambda _settings: None,
        ),
        perf_stats=SimpleNamespace(set_counter=lambda *_args, **_kwargs: None),
        assets=SimpleNamespace(get_texture=lambda _path: None),
    )
    return controller


def test_draw_orders_background_plan_negative_tiles_scene_then_positive_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core
    from engine.tilemap_batch import TilemapBatchStats

    events: list[str] = []
    controller = _make_controller(events)
    controller.layers["background"] = _SpySpriteList("background", events, [SimpleNamespace(name="bg")])
    controller.layers["entities"] = _SpySpriteList("entities", events, [SimpleNamespace(name="entity")])
    controller.layers["foreground"] = _SpySpriteList("foreground", events, [SimpleNamespace(name="fg")])

    controller._tilemap_draw_layers = [
        SimpleNamespace(id="bg_tiles", z=-1, parallax=1.0, sprites=_SpySpriteList("bg_tiles", events)),
        SimpleNamespace(id="fg_tiles", z=1, parallax=1.0, sprites=_SpySpriteList("fg_tiles", events)),
    ]

    monkeypatch.setattr(core, "build_render_context", lambda **_kwargs: events.append("build_context") or "ctx")
    monkeypatch.setattr(core, "compute_draw_plan", lambda _ctx: events.append("compute_plan") or "plan")
    monkeypatch.setattr(core, "execute_background_plan", lambda _plan, _texture_getter, **_kw: events.append("background_plan"))
    monkeypatch.setattr(core, "execute_scene_plan", lambda _plan, **_kwargs: events.append("scene_plan"))
    monkeypatch.setattr(controller, "_set_world_entities_counter", lambda count: events.append(f"world_count:{count}"))
    monkeypatch.setattr(controller, "_set_tilemap_perf_counters", lambda _stats: events.append("tile_counters"))
    monkeypatch.setattr(controller, "_set_render_cull_counter", lambda: events.append("render_counters"))
    monkeypatch.setattr(
        controller,
        "_draw_tilemap_layer",
        lambda tile_layer, **_kwargs: events.append(f"tile:{tile_layer.id}") or TilemapBatchStats(),
    )

    controller.draw()

    assert events == [
        "iter:background",
        "iter:entities",
        "iter:foreground",
        "world_count:3",
        "build_context",
        "compute_plan",
        "camera:gui",
        "background_plan",
        "camera:world",
        "tile:bg_tiles",
        "scene_plan",
        "tile:fg_tiles",
        "tile_counters",
        "render_counters",
    ]


def test_layer_draw_order_keeps_standard_layers_first_then_preserves_extras() -> None:
    controller = _make_controller([])
    effects = _SpySpriteList("effects", [])
    ui = _SpySpriteList("ui", [])
    background = _SpySpriteList("background", [])
    entities = _SpySpriteList("entities", [])
    foreground = _SpySpriteList("foreground", [])
    controller.layers = {
        "effects": effects,
        "foreground": foreground,
        "ui": ui,
        "entities": entities,
        "background": background,
    }

    assert list(controller._layer_draw_order()) == [background, entities, foreground, effects, ui]


def test_get_camera_rect_returns_stable_bounds() -> None:
    controller = _make_controller([])
    controller.window.width = 200
    controller.window.height = 100
    controller.window.camera_controller.zoom_state.current = 2.0

    rect = controller._get_camera_rect(camera_pos=(50.0, 25.0))

    assert rect == (0.0, 0.0, 100.0, 50.0)
    left, bottom, right, top = rect
    assert left < right
    assert bottom < top


def test_draw_tilemap_layer_handles_empty_layer_without_camera() -> None:
    controller = _make_controller([])
    sprites = _SpySpriteList("tile_layer", [])
    tile_layer = SimpleNamespace(id="ground", parallax=1.0, sprites=sprites)

    stats = controller._draw_tilemap_layer(tile_layer, camera=None, base_camera_pos=(0.0, 0.0))

    assert sprites.draw_calls == 1
    assert stats.sprites_drawn == 0
    assert stats.chunks_drawn == 1
    assert stats.draw_calls == 1


def test_draw_tilemap_layer_uses_batcher_when_available() -> None:
    controller = _make_controller([])
    events: list[str] = []
    controller.window.width = 200
    controller.window.height = 100
    controller.window.tilemap_batching_enabled = True
    controller.window.camera_controller.zoom_state.current = 2.0
    controller.window.camera = _SpyCamera(events, "world")
    sprites = _SpySpriteList("tile_layer", events)
    tile_layer = SimpleNamespace(id="ground", parallax=1.0, sprites=sprites)
    controller.tilemap_instance = SimpleNamespace(
        map_size=(10, 10),
        tile_size=(16, 16),
        layer_data={"ground": [0]},
        layer_offsets={"ground": (3.0, 4.0)},
    )
    batch_calls: list[dict[str, Any]] = []
    sentinel_stats = SimpleNamespace(sprites_drawn=7, chunks_drawn=2, draw_calls=1)
    controller._tilemap_batcher = SimpleNamespace(
        available=True,
        draw_layer=lambda **kwargs: batch_calls.append(kwargs) or sentinel_stats,
    )

    stats = controller._draw_tilemap_layer(
        tile_layer,
        camera=controller.window.camera,
        base_camera_pos=(100.0, 50.0),
    )

    assert stats is sentinel_stats
    assert controller.window.camera.position == (100.0, 50.0)
    assert events == ["camera:world"]
    assert sprites.draw_calls == 0
    assert batch_calls == [
        {
            "layer_id": "ground",
            "sprites": sprites,
            "rect": (50.0, 25.0, 150.0, 75.0),
            "offset": (3.0, 4.0),
        }
    ]


def test_get_background_plane_texture_falls_back_to_direct_load_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core

    class _ResolvedPath:
        def exists(self) -> bool:
            return True

        def __str__(self) -> str:
            return "resolved/bg.png"

    controller = _make_controller([])
    asset_calls: list[str] = []
    controller.window.assets = SimpleNamespace(
        get_texture=lambda path: asset_calls.append(path) or (_ for _ in ()).throw(RuntimeError("missing")),
    )
    sentinel_texture = object()

    monkeypatch.setattr(
        core.optional_arcade.arcade,
        "load_texture",
        lambda path: sentinel_texture if path.endswith("bg.png") else None,
    )
    monkeypatch.setattr(
        "engine.paths.resolve_path",
        lambda _path: _ResolvedPath(),
    )

    texture_a = controller._get_background_plane_texture("assets/bg.png")
    texture_b = controller._get_background_plane_texture("assets/bg.png")

    assert texture_a is sentinel_texture
    assert texture_b is sentinel_texture
    assert asset_calls == ["assets/bg.png"]


def test_draw_smoke_without_entities_or_tilemap(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core

    controller = _make_controller([])
    controller.layers = {
        "background": _SpySpriteList("background", []),
        "entities": _SpySpriteList("entities", []),
        "foreground": _SpySpriteList("foreground", []),
    }

    monkeypatch.setattr(core, "build_render_context", lambda **_kwargs: "ctx")
    monkeypatch.setattr(core, "compute_draw_plan", lambda _ctx: "plan")
    monkeypatch.setattr(core, "execute_background_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(core, "execute_scene_plan", lambda *_args, **_kwargs: None)

    controller.draw()
