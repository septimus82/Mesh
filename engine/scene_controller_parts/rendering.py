# mypy: ignore-errors
from __future__ import annotations

from typing import Any, Iterable

from engine.tilemap import compute_parallax_camera_position
from engine.tilemap_batch import TilemapBatchStats


def draw(self) -> None:
    import engine.scene_controller_core as scene_controller_module

    render_queue = getattr(self.window, "render_queue", None)
    use_batching = False
    if render_queue is not None and getattr(self.window, "render_batching_enabled", False):
        enabled = getattr(render_queue, "is_enabled", None)
        use_batching = enabled() if callable(enabled) else True
    self._render_culled_count = 0
    base_camera_pos = self.window.get_camera_center()
    use_culling = bool(getattr(self.window, "render_culling_enabled", False)) and use_batching
    camera_rect = self._get_camera_rect(camera_pos=base_camera_pos) if use_culling else None

    if self._background_layers:
        camera_x, camera_y = base_camera_pos
        zoom = float(self.window.camera_controller.zoom_state.current)
        try:
            self.window.camera_controller.gui_camera.use()
            scene_controller_module.draw_background_layers(
                self._background_layers,
                camera_x=float(camera_x),
                camera_y=float(camera_y),
                viewport_w=float(self.window.width),
                viewport_h=float(self.window.height),
                zoom=zoom,
                coordinate_space="projected",
            )
        finally:
            self.window.camera.use()

    all_sprites: list[Any] = []
    for layer in self._layer_draw_order():
        all_sprites.extend(layer)
    self._set_world_entities_counter(len(all_sprites))

    ctx = scene_controller_module.build_render_context(
        sprites=all_sprites,
        background_planes=self._background_planes,
        camera_pos=base_camera_pos,
        viewport_size=(float(self.window.width), float(self.window.height)),
        zoom=float(self.window.camera_controller.zoom_state.current),
        sort_mode=self._render_sort_mode,
        shadows_enabled=self._shadows_enabled,
        shadows_ao_enabled=self._shadows_ao_enabled,
        shadows_contact_enabled=self._shadows_contact_enabled,
        depth_tint_settings=self._depth_tint_settings,
        outline_settings=self._outline_settings,
        use_culling=use_culling,
        camera_rect=camera_rect,
    )
    plan = scene_controller_module.compute_draw_plan(ctx)

    if hasattr(self.window.camera_controller, "gui_camera"):
        self.window.camera_controller.gui_camera.use()
        scene_controller_module.execute_background_plan(
            plan, self._get_background_plane_texture,
            viewport_size=(self.window.width, self.window.height),
        )
        self.window.camera.use()

    tile_layers = self._tilemap_draw_layers
    tile_stats = TilemapBatchStats()
    camera = getattr(self.window, "camera", None)

    if tile_layers:
        for tile_layer in tile_layers:
            if tile_layer.z < 0:
                tile_stats.add(
                    self._draw_tilemap_layer(tile_layer, camera=camera, base_camera_pos=base_camera_pos)
                )
    else:
        for layer in self._tilemap_background_layers:
            layer.draw()

    scene_controller_module.execute_scene_plan(
        plan,
        render_queue=render_queue,
        use_batching=use_batching,
        camera_rect=camera_rect,
        use_culling=use_culling,
    )
    if use_batching and render_queue:
        render_queue.flush()

    if tile_layers:
        for tile_layer in tile_layers:
            if tile_layer.z >= 0:
                tile_stats.add(
                    self._draw_tilemap_layer(tile_layer, camera=camera, base_camera_pos=base_camera_pos)
                )
    else:
        for layer in self._tilemap_foreground_layers:
            layer.draw()

    self._set_tilemap_perf_counters(tile_stats)
    self._set_render_cull_counter()


def _get_background_plane_texture(self, asset_path: str) -> Any:
    import engine.scene_controller_core as scene_controller_module

    if asset_path in self._background_plane_texture_cache:
        return self._background_plane_texture_cache[asset_path]

    texture = None

    assets = getattr(self.window, "assets", None)
    if assets is not None:
        try:
            texture = assets.get_texture(asset_path)
        except Exception as exc:  # noqa: BLE001  # REASON: assets-manager texture lookup failures should fall back to direct texture loading for that background plane
            scene_controller_module.record_swallowed(
                "engine.scene_controller._get_background_plane_texture.assets_get_texture",
                exc,
            )

    if texture is None:
        try:
            import engine.paths as paths_module

            load_texture = getattr(scene_controller_module.optional_arcade.arcade, "load_texture", None)
            if load_texture is not None:
                resolved = paths_module.resolve_path(asset_path)
                if resolved.exists():
                    texture = load_texture(str(resolved))
        except Exception:
            scene_controller_module.logger.debug("Fallback texture load failed for %r", asset_path, exc_info=True)

    self._background_plane_texture_cache[asset_path] = texture
    return texture


def _draw_tilemap_layer(
    self,
    tile_layer: Any,
    *,
    camera: Any,
    base_camera_pos: tuple[float, float],
) -> TilemapBatchStats:
    stats = TilemapBatchStats()
    if camera is None:
        tile_layer.sprites.draw()
        stats.sprites_drawn = len(tile_layer.sprites)
        stats.chunks_drawn = 1
        stats.draw_calls = 1
        return stats
    parallax = float(tile_layer.parallax)
    camera_pos = compute_parallax_camera_position(base_camera_pos, parallax)
    try:
        setattr(camera, "position", camera_pos)
        use = getattr(camera, "use", None)
        if callable(use):
            use()
    except Exception:
        tile_layer.sprites.draw()
        stats.sprites_drawn = len(tile_layer.sprites)
        stats.chunks_drawn = 1
        stats.draw_calls = 1
        return stats

    instance = self.tilemap_instance
    batcher = self._tilemap_batcher
    if (
        instance is not None
        and batcher is not None
        and getattr(self.window, "tilemap_batching_enabled", False)
        and getattr(batcher, "available", True)
        and tile_layer.id in instance.layer_data
    ):
        zoom_state = getattr(self.window, "camera_controller", None)
        zoom = 1.0
        if zoom_state is not None:
            zoom = float(getattr(getattr(zoom_state, "zoom_state", None), "current", 1.0))
        if zoom <= 0.0:
            zoom = 1.0
        view_w = float(self.window.width) / zoom
        view_h = float(self.window.height) / zoom
        left = camera_pos[0] - view_w / 2.0
        right = camera_pos[0] + view_w / 2.0
        bottom = camera_pos[1] - view_h / 2.0
        top = camera_pos[1] + view_h / 2.0
        offset = instance.layer_offsets.get(tile_layer.id, (0.0, 0.0))
        return batcher.draw_layer(
            layer_id=tile_layer.id,
            sprites=tile_layer.sprites,
            rect=(left, bottom, right, top),
            offset=offset,
        )

    tile_layer.sprites.draw()
    stats.sprites_drawn = len(tile_layer.sprites)
    stats.chunks_drawn = 1
    stats.draw_calls = 1
    return stats


def _set_tilemap_perf_counters(self, stats: TilemapBatchStats) -> None:
    perf = getattr(self.window, "perf_stats", None)
    setter = getattr(perf, "set_counter", None) if perf is not None else None
    if not callable(setter):
        return
    setter("tile_chunks_drawn", stats.chunks_drawn)
    setter("tile_sprites_drawn", stats.sprites_drawn)
    setter("tile_draw_calls", stats.draw_calls)


def _set_world_entities_counter(self, entity_count: int) -> None:
    perf = getattr(self.window, "perf_stats", None)
    setter = getattr(perf, "set_counter", None) if perf is not None else None
    if not callable(setter):
        return
    setter("world.entities.count", int(entity_count))


def _set_render_cull_counter(self) -> None:
    perf = getattr(self.window, "perf_stats", None)
    setter = getattr(perf, "set_counter", None) if perf is not None else None
    if not callable(setter):
        return
    setter("render_sprites_culled", int(self._render_culled_count))


def _get_camera_rect(self, *, camera_pos: tuple[float, float]) -> Any:
    zoom_state = getattr(self.window, "camera_controller", None)
    zoom = 1.0
    if zoom_state is not None:
        zoom = float(getattr(getattr(zoom_state, "zoom_state", None), "current", 1.0))
    if zoom <= 0.0:
        zoom = 1.0
    view_w = float(self.window.width) / zoom
    view_h = float(self.window.height) / zoom
    left = float(camera_pos[0]) - view_w / 2.0
    right = float(camera_pos[0]) + view_w / 2.0
    bottom = float(camera_pos[1]) - view_h / 2.0
    top = float(camera_pos[1]) + view_h / 2.0
    return (left, bottom, right, top)


def _layer_draw_order(self) -> Iterable[Any]:
    ordered_names = ["background", "entities", "foreground"]
    already_yielded = set()
    for name in ordered_names:
        layer = self.layers.get(name)
        if layer is not None:
            already_yielded.add(name)
            yield layer
    for name, layer in self.layers.items():
        if name not in already_yielded:
            yield layer


def bind_rendering_methods(cls) -> None:
    cls.draw = draw
    cls._get_background_plane_texture = _get_background_plane_texture
    cls._draw_tilemap_layer = _draw_tilemap_layer
    cls._set_tilemap_perf_counters = _set_tilemap_perf_counters
    cls._set_world_entities_counter = _set_world_entities_counter
    cls._set_render_cull_counter = _set_render_cull_counter
    cls._get_camera_rect = _get_camera_rect
    cls._layer_draw_order = _layer_draw_order
