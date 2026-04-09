# ruff: noqa
# mypy: ignore-errors
"""Scene controller for managing entities, layers, and scene lifecycle.

The SceneController is the central hub for runtime scene management, handling:

- **Scene Loading**: Parse JSON scenes into sprite entities with behaviours
- **Layer Management**: Organize sprites into named layers (background/entities/foreground)
- **Entity Lifecycle**: Create, update, and destroy entities and their behaviours
- **Tilemap Integration**: Load and render tilemaps with collision detection
- **Scene Transitions**: Queue and execute scene changes with fade effects
- **HD-2D Rendering**: Support for depth sorting, shadows, parallax, and outlines
- **Pathfinding**: Build and cache navigation grids for AI movement

Architecture:
    The SceneController maintains the runtime representation of a scene,
    separate from the JSON source. It coordinates with:
    - :class:`SceneLoader` for parsing scene JSON
    - :class:`PrefabManager` for entity template resolution
    - :class:`TilemapManager` for tileset loading
    - :class:`LightManager` for dynamic lighting
    - :class:`SensorRuntime` for trigger zone detection

Scene JSON Format::

    {
        "name": "My Scene",
        "version": 1,
        "settings": {
            "world_width": 1600,
            "world_height": 900,
            "background_color": "dark_blue_gray",
            "render_sort_mode": "y_sort"
        },
        "layers": [
            {"name": "background"},
            {"name": "entities"},
            {"name": "foreground"}
        ],
        "entities": [
            {"name": "Player", "x": 100, "y": 200, "prefab": "p_player"},
            {"name": "NPC", "x": 300, "y": 200, "prefab": "p_npc_guard"}
        ],
        "tilemap": { ... }
    }

Key Methods:
    - :meth:`load_scene`: Load a scene from JSON path
    - :meth:`request_scene_change`: Queue transition to another scene
    - :meth:`get_entity_by_name`: Find an entity sprite by name
    - :meth:`spawn_entity`: Create a new entity at runtime

See Also:
    - :doc:`docs/scenes` for scene format documentation
    - :doc:`docs/mesh_scene_spec` for complete schema reference
"""

from __future__ import annotations

import copy
import hashlib
import logging
import math
import os
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Iterator, Sequence, cast
import engine.optional_arcade as optional_arcade

from .scene_index import SceneIndex
from .scene_runtime.index_build import build_scene_index_from_sprites
from .scene_runtime.spawn import apply_pending_spawn_point as _apply_pending_spawn_point_runtime
from .scene_runtime.spawn import find_spawn_marker as _find_spawn_marker_runtime
from .scene_runtime.spawn import get_spawn as _get_spawn_runtime
from .scene_runtime.transitions import perform_scene_change as _perform_scene_change_runtime
from .scene_runtime.transitions import queue_scene_change as _queue_scene_change_runtime
from .scene_runtime.transitions import reload_scene as _reload_scene_runtime
from .scene_runtime.transitions import request_scene_change as _request_scene_change_runtime
from .scene_runtime.transitions import request_scene_reload as _request_scene_reload_runtime
from .scene_runtime import scene_load_apply as _scene_load_apply_runtime
from . import scene_controller_selection as _selection_proxy
from . import scene_controller_scene_switch as _scene_switch
from . import scene_controller_save_load as _save_load_proxy
from .scene_lifecycle_controller import load_scene as _load_scene_runtime
from .scene_update_controller import SceneUpdateController
from .scene_entity_store_controller import SceneEntityStoreController
from .scene_runtime import authoring as _authoring_runtime
from .scene_runtime.persistence import (
    apply_scene_state as _apply_scene_state_runtime,
    build_scene_snapshot as _build_scene_snapshot_runtime,
    restore_camera_state as _restore_camera_state_runtime,
    restore_player_state as _restore_player_state_runtime,
    snapshot_camera_state as _snapshot_camera_state_runtime,
    snapshot_player_state as _snapshot_player_state_runtime,
)
from .scene_render_pipeline import (
    build_render_context,
    compute_draw_plan,
    execute_draw_plan,
    execute_background_plan,
    execute_scene_plan,
)
from .sensors_runtime import SensorRuntime
from .animation_state import (
    request_animation_state,
    tick_animation_state,
)

logger = logging.getLogger(__name__)
_LOG_ONCE: set[str] = set()
from .behaviours import (
    create_behaviour,
    get_behaviour_info,
)
from .behaviours.utils import (
    BEHAVIOUR_META_EXPLICIT,
    build_behaviour_config_map,
    ensure_behaviour_config_root,
    format_behaviour_config_summary,
    normalize_behaviour_entry,
    prepare_behaviour_configs,
    prune_optional_behaviour_defaults,
    strip_behaviour_metadata,
)
from .swallowed_exceptions import record_swallowed
from .constants import (
    EVENT_ANIMATION_EVENT,
    EVENT_COLLECTIBLE_PICKED,
    EVENT_DAMAGE_APPLIED,
)
from .encounter_sets import get_theme_manager
from .events import MeshEvent
from .elite_labeling import format_elite_label
from .encounter_cost import get_effective_encounter_cost, is_boss_payload, is_elite_payload, is_mini_boss_payload
from .prefabs import get_prefab_manager
from .paths import resolve_path
from .tilemap import TilemapDrawLayer, TilemapInstance, compute_parallax_camera_position
from .tilemap_batch import TilemapBatchState, TilemapBatchStats
from .tilemap_batch_arcade import TilemapBatcher
from .background_layers import BackgroundLayer, draw_background_layers, parse_background_layers
from .culling import Rect, is_sprite_visible, sprite_bounds
from .pathfinding import NavGrid
from .scene_navigation_controller import SceneNavigationController
from .scene_controller_parts.loading import (
    bind_loading_methods as _bind_loading_methods,
)
from .scene_controller_parts.transitions import (
    bind_transitions_methods as _bind_transitions_methods,
)
from .scene_controller_parts.runtime_hooks import (
    bind_runtime_hooks_methods as _bind_runtime_hooks_methods,
)
from .scene_controller_parts.persistence import (
    bind_persistence_methods as _bind_persistence_methods,
)
from .scene_controller_parts.quests_flags import (
    bind_quests_flags_methods as _bind_quests_flags_methods,
)
from .parallax_model import BackgroundPlane, parse_background_planes, sort_background_planes
from .render_queue import DrawSpriteCmd
from .render_sort_model import compute_sprite_render_sort_key
from .sprite_shadow_model import compute_sprite_multi_shadow
from .editor.sprite_outline_model import (
    OutlineSettings,
    DEFAULT_OUTLINE_SETTINGS,
    compute_sprite_outline_draw_calls,
    parse_outline_settings,
    should_draw_outline,
)
from .depth_tint_model import (
    DepthTintSettings,
    DEFAULT_DEPTH_TINT_SETTINGS,
    parse_depth_tint_settings,
    compute_sprite_tint,
    apply_tint_to_sprite_color,
)
from .ui import (
    AnimationStateOverlay,
    CharacterPanel,
    DevConsole,
    DialogueBox,
    EntityInspector,
    HealthBar,
    InventoryOverlay,
    QuestLog,
    ShopPanel,
    maybe_enqueue_boss_spawn_toast,
    maybe_enqueue_miniboss_spawn_toast,
    maybe_enqueue_controls_hint_toast,
    maybe_enqueue_preset_mode_toast,
    maybe_enqueue_shadowmask_enabled_toast,
)

if TYPE_CHECKING:
    from .game import GameWindow


class SceneController:
    """Manages scene loading, entities, layers, and runtime state.

    The SceneController is responsible for:
    - Loading scenes from JSON and building sprite entities
    - Managing named sprite layers (background, entities, foreground)
    - Updating entity behaviours each frame
    - Handling scene transitions and reloads
    - Providing entity lookup and iteration utilities
    - Rendering the scene with HD-2D effects

    Attributes:
        window: Reference to the main GameWindow.
        layers: Dict mapping layer names to SpriteLists.
        solid_sprites: SpriteList of collidable sprites.
        scene_settings: Current scene's settings dict.
        current_scene_path: Path to the currently loaded scene.
        tilemap_instance: Active tilemap (if scene has one).
        player: Reference to the player sprite (shortcut).

    Example:
        Get entities and transition scenes::

            # Find an entity
            npc = scene.get_entity_by_name(\"Guard\")

            # Iterate all entities
            for sprite in scene.all_sprites:
                print(sprite.name)

            # Change scenes
            scene.request_scene_change(\"scenes/dungeon.json\")

            # Spawn entity at runtime
            scene.spawn_entity({
                \"name\": \"Projectile\",
                \"x\": 100, \"y\": 200,
                \"prefab\": \"p_arrow\"
            })
    """

    if TYPE_CHECKING:
        @property
        def current_scene_data(self) -> Dict[str, Any] | None: ...

        def load_scene(self, scene_path: str) -> Dict[str, Any]: ...
        def request_scene_reload(self, clear_assets: bool = False) -> None: ...
        def get_nav_grid(self) -> NavGrid | None: ...
        def request_scene_change(self, scene_path: str) -> None: ...
        def queue_scene_change(self, scene_path: str, spawn_id: str | None = None) -> None: ...
        def _perform_scene_change(self, scene_path: str, spawn_id: str | None = None) -> None: ...
        def reload_scene(self, new_path: str | None = None) -> bool: ...
        def reload_current_scene(self) -> bool: ...
        def update(self, delta_time: float) -> None: ...
        def _snapshot_player_state(self) -> dict[str, Any] | None: ...
        def _restore_player_state(self, snapshot: dict[str, Any] | None) -> None: ...
        def _snapshot_camera_state(self) -> dict[str, Any] | None: ...
        def _restore_camera_state(self, snapshot: dict[str, Any] | None) -> None: ...
        def debug_config_set_game_state_set_toast(
            self,
            selected_ids: list[str],
            *,
            toast: str,
            toast_seconds: float | None,
        ) -> tuple[int, int, int]: ...
        def debug_config_set_game_state_add_require_flag(self, selected_ids: list[str], flag: str) -> tuple[int, int, int]: ...
        def debug_config_set_game_state_add_forbid_flag(self, selected_ids: list[str], flag: str) -> tuple[int, int, int]: ...
        def debug_config_set_game_state_set_flag_true(self, selected_ids: list[str], flag_key: str) -> tuple[int, int, int]: ...
        def debug_config_scene_transition_set_target_scene(self, selected_ids: list[str], target_scene: str) -> tuple[int, int, int]: ...
        def debug_config_scene_transition_set_spawn_id(self, selected_ids: list[str], spawn_id: str) -> tuple[int, int, int]: ...

    def __init__(self, window: GameWindow):
        """Initialize the scene controller.

        Args:
            window: The main game window to attach to.
        """
        self.window = window
        self.layers: Dict[str, optional_arcade.arcade.SpriteList] = {
            "background": optional_arcade.arcade.SpriteList(),
            "entities": optional_arcade.arcade.SpriteList(),
            "foreground": optional_arcade.arcade.SpriteList(),
        }
        self.solid_sprites: optional_arcade.arcade.SpriteList = optional_arcade.arcade.SpriteList()
        self.scene_settings: Dict[str, Any] = {}
        self.current_scene_path: str | None = None
        self._pending_scene_path: str | None = None
        self._pending_scene_change: dict[str, Any] | None = None
        self._clear_assets_on_next_load: bool = False
        self._suppress_spawn_toasts: bool = False
        self._loaded_scene_data: Dict[str, Any] = {}
        self._loaded_scene_source_data: Dict[str, Any] = {}
        self._scene_index: SceneIndex | None = None
        self._preserved_camera_state: Dict[str, Any] | None = None
        self._last_hot_reload_error_message: str = ""
        self._last_hot_reload_error_scene: str = ""

        # Tilemap state
        self.tilemap_instance: TilemapInstance | None = None
        self._tilemap_background_layers: list[optional_arcade.arcade.SpriteList] = []
        self._tilemap_foreground_layers: list[optional_arcade.arcade.SpriteList] = []
        self._tilemap_draw_layers: list[TilemapDrawLayer] = []
        self._tilemap_batch_state: TilemapBatchState | None = None
        self._tilemap_batcher: TilemapBatcher | None = None

        # Background/parallax layers
        self._background_layers: list[BackgroundLayer] = []
        self._background_planes: list[BackgroundPlane] = []
        self._background_plane_texture_cache: dict[str, Any] = {}

        # Pathfinding cache
        self.navigation = SceneNavigationController()
        self.updater = SceneUpdateController()
        self.entities = SceneEntityStoreController(self)
        self._render_culled_count: int = 0
        self._render_sort_mode: str = "y_sort"  # "y_sort" or "explicit_z"
        self.sensors_runtime = SensorRuntime()
        self._shadows_enabled: bool = True  # HD-2D sprite drop shadows
        self._shadows_contact_enabled: bool = True  # HD-2D contact shadows (double-layer)
        self._shadows_ao_enabled: bool = False  # HD-2D AO shadow ring (optional)
        self._depth_tint_settings: DepthTintSettings = DEFAULT_DEPTH_TINT_SETTINGS  # HD-2D depth tinting
        self._outline_settings: OutlineSettings = DEFAULT_OUTLINE_SETTINGS  # HD-2D faux sprite outlines

        self._scene_event_unsubscribes: list[Callable[[], None]] = []

        self._default_collision_rules: dict[tuple[str | None, str | None], bool] = {
            self._make_rule_pair("player", "terrain"): True,
            self._make_rule_pair("player", "pickup"): True,
            self._make_rule_pair("player", "hazard"): True,
            self._make_rule_pair("enemy", "terrain"): True,
        }
        self.collision_rules: dict[tuple[str | None, str | None], bool] = dict(
            self._default_collision_rules,
        )

        # Prefabs are now handled by PrefabManager
        get_prefab_manager().load()

    def _make_rule_pair(self, tag1: str | None, tag2: str | None) -> tuple[str | None, str | None]:
        t1 = str(tag1).strip().lower() if tag1 else None
        t2 = str(tag2).strip().lower() if tag2 else None
        if t1 is None and t2 is None:
            return (None, None)
        if t1 is None:
            return (None, t2)
        if t2 is None:
            return (None, t1)
        return (t1, t2) if t1 <= t2 else (t2, t1)

    def _apply_collision_rules_overrides(self, rules: dict[str, bool]) -> None:
        for key, value in rules.items():
            if not isinstance(key, str):
                continue
            parts = key.split(":")
            if len(parts) == 2:
                pair = self._make_rule_pair(parts[0], parts[1])
                self.collision_rules[pair] = bool(value)

    def should_collide(self, sprite_a: optional_arcade.arcade.Sprite, sprite_b: optional_arcade.arcade.Sprite) -> bool:
        tag_a = getattr(sprite_a, "mesh_tag", None)
        tag_b = getattr(sprite_b, "mesh_tag", None)
        pair = self._make_rule_pair(tag_a, tag_b)
        return self.collision_rules.get(pair, True)

    @property
    def all_sprites(self) -> Iterator[optional_arcade.arcade.Sprite]:
        """Iterate through every sprite across all layers."""
        for layer in self.layers.values():
            for sprite in layer:
                yield sprite

    def _apply_theme_runtime(self, scene_data: Dict[str, Any]) -> None:
        settings = scene_data.get("settings", {})
        theme_id = settings.get("region_theme")
        if not theme_id:
            return

        tm = get_theme_manager()
        theme = tm.get_theme(theme_id)
        if not theme:
            return

        # Resolve Encounter Set
        encounter_set_id = settings.get("encounter_set_id")
        if encounter_set_id:
            encounter_set = tm.get_encounter_set(encounter_set_id)
        else:
            encounter_set = tm.resolve_encounter_set_for_theme(theme_id)

        if not encounter_set:
            return

        # Apply Audio
        if "music" not in settings and encounter_set.ambient_audio_key:
            audio_map = {
                "forest_ambience": "assets/music/forest_ambience.mp3",
                "lava_rumble": "assets/music/lava_rumble.mp3",
                "void_hum": "assets/music/void_hum.mp3"
            }
            if encounter_set.ambient_audio_key in audio_map:
                settings["music"] = audio_map[encounter_set.ambient_audio_key]

        # Apply Lighting
        if "lights" not in scene_data and theme.lighting_hint:
            lighting_map = {
                "green_dim": [{"type": "ambient", "color": [50, 100, 50], "intensity": 0.4}],
                "red_glow": [{"type": "ambient", "color": [100, 50, 50], "intensity": 0.5}],
                "purple_dark": [{"type": "ambient", "color": [60, 20, 80], "intensity": 0.3}]
            }
            if theme.lighting_hint in lighting_map:
                scene_data["lights"] = lighting_map[theme.lighting_hint]

        # Apply Spawns
        if settings.get("use_theme_spawns") and encounter_set.enemy_prefab_ids:
            self._resolve_budgeted_spawns(scene_data, encounter_set, theme)











    def draw(self) -> None:
        render_queue = getattr(self.window, "render_queue", None)
        use_batching = False
        if render_queue is not None and getattr(self.window, "render_batching_enabled", False):
            enabled = getattr(render_queue, "is_enabled", None)
            use_batching = enabled() if callable(enabled) else True
        self._render_culled_count = 0
        base_camera_pos = self.window.get_camera_center()
        use_culling = bool(getattr(self.window, "render_culling_enabled", False)) and use_batching
        camera_rect = self._get_camera_rect(camera_pos=base_camera_pos) if use_culling else None

        # 1. Background Layers (Custom)
        if self._background_layers:
            try:
                camera_x, camera_y = base_camera_pos
                zoom = float(self.window.camera_controller.zoom_state.current)
                self.window.camera_controller.gui_camera.use()
                draw_background_layers(
                    self._background_layers,
                    camera_x=float(camera_x),
                    camera_y=float(camera_y),
                    viewport_w=float(self.window.width),
                    viewport_h=float(self.window.height),
                    zoom=zoom,
                )
            finally:
                self.window.camera.use()

        # Build Render Context & Plan
        all_sprites: list[Any] = []
        for layer in self._layer_draw_order():
            all_sprites.extend(layer)
        self._set_world_entities_counter(len(all_sprites))

        ctx = build_render_context(
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
        plan = compute_draw_plan(ctx)

        # 2. Background Planes (Parallax) - GUI Camera
        if hasattr(self.window.camera_controller, "gui_camera"):
             self.window.camera_controller.gui_camera.use()
             execute_background_plan(plan, self._get_background_plane_texture)
             self.window.camera.use()

        tile_layers = self._tilemap_draw_layers
        tile_stats = TilemapBatchStats()
        camera = getattr(self.window, "camera", None)

        if tile_layers:
            # 3a. Tile Layers Z < 0
            for tile_layer in tile_layers:
                if tile_layer.z < 0:
                     tile_stats.add(
                        self._draw_tilemap_layer(tile_layer, camera=camera, base_camera_pos=base_camera_pos)
                    )
        else:
             # 3b. Legacy BG Layers
             for layer in self._tilemap_background_layers:
                layer.draw()
        
        # 4. Scene (Shadows + Sprites)
        execute_scene_plan(
             plan, 
             render_queue=render_queue, 
             use_batching=use_batching, 
             camera_rect=camera_rect, 
             use_culling=use_culling
        )
        if use_batching and render_queue:
            render_queue.flush()
        
        if tile_layers:
            # 5a. Tile Layers Z >= 0
             for tile_layer in tile_layers:
                if tile_layer.z >= 0:
                     tile_stats.add(
                        self._draw_tilemap_layer(tile_layer, camera=camera, base_camera_pos=base_camera_pos)
                    )
        else:
             # 5b. Legacy FG Layers
             for layer in self._tilemap_foreground_layers:
                layer.draw()

        self._set_tilemap_perf_counters(tile_stats)
        self._set_render_cull_counter()

    def _get_background_plane_texture(self, asset_path: str) -> Any:
        """Get texture for a background plane, using cache.

        Headless-safe: returns None if texture loading unavailable.
        """
        # Check cache first
        if asset_path in self._background_plane_texture_cache:
            return self._background_plane_texture_cache[asset_path]

        texture = None

        # Try assets manager first
        assets = getattr(self.window, "assets", None)
        if assets is not None:
            try:
                texture = assets.get_texture(asset_path)
            except Exception as exc:  # noqa: BLE001  # REASON: assets-manager texture lookup failures should fall back to direct texture loading for that background plane
                record_swallowed("engine.scene_controller._get_background_plane_texture.assets_get_texture", exc)

        # Fallback to direct load
        if texture is None:
            try:
                from .paths import resolve_path
                load_texture = getattr(optional_arcade.arcade, "load_texture", None)
                if load_texture is not None:
                    resolved = resolve_path(asset_path)
                    if resolved.exists():
                        texture = load_texture(str(resolved))
            except Exception:
                logger.debug("Fallback texture load failed for %r", asset_path, exc_info=True)

        # Cache result (even if None to avoid repeated failures)
        self._background_plane_texture_cache[asset_path] = texture
        return texture

    def _draw_tilemap_layer(
        self,
        tile_layer: TilemapDrawLayer,
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

    def _get_camera_rect(self, *, camera_pos: tuple[float, float]) -> Rect:
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





    def _apply_entity_mutation(
        self,
        sprite: optional_arcade.arcade.Sprite,
        *,
        x: float | None = None,
        y: float | None = None,
        scale: float | None = None,
        tag: str | None = None,
    ) -> None:
        self.entities.enqueue_mutation(sprite, x=x, y=y, scale=scale, tag=tag)
        self.entities.apply_pending_ops(self, stage="immediate")

    def _apply_collision_poly(self, sprite: optional_arcade.arcade.Sprite, poly: Any) -> None:
        from engine.geometry_tools import sanitize_poly  # noqa: PLC0415

        points: list[tuple[float, float]] = []
        if isinstance(poly, list):
            points = sanitize_poly(poly)
        try:
            set_hit_box = getattr(sprite, "set_hit_box", None)
            if not callable(set_hit_box):
                return
            if points:
                if os.environ.get("MESH_POLY_DEBUG") == "1":
                    cx = sum(p[0] for p in points) / len(points)
                    cy = sum(p[1] for p in points) / len(points)
                    if abs(cx) > 1e-3 or abs(cy) > 1e-3:
                        logger.info(
                            "[Mesh][Poly] collision_poly centroid offset for %s: (%.3f, %.3f)",
                            getattr(sprite, "mesh_name", "<unnamed>"),
                            cx,
                            cy,
                        )
                # Points are entity-local (relative to entity position), which matches sprite-local hitbox space.
                set_hit_box(points)
            else:
                set_hit_box()
        except Exception:  # noqa: BLE001  # REASON: invalid collision polygon application should skip only that sprite hitbox update
            logger.debug("Failed to apply collision polygon on %s", getattr(sprite, 'mesh_name', '?'), exc_info=True); return

    def _build_behaviour_instantiation_lines(self, limit: int = 24) -> list[str]:
        lines: list[str] = []
        total_behaviours = 0
        for sprite in self._iter_layered_sprites():
            behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
            total_behaviours += len(behaviours)
            for behaviour in behaviours:
                if len(lines) >= limit:
                    continue
                label = behaviour.__class__.__name__
                config = getattr(behaviour, "config", {}) or {}
                summary = format_behaviour_config_summary(config)
                lines.append(f"{label}{summary} ✔")
        if total_behaviours > limit:
            lines.append(f"... (+{total_behaviours - limit} more behaviours)")
        return lines

    def _clear_scene_event_subscriptions(self) -> None:
        if not self._scene_event_unsubscribes:
            return
        for unsub in self._scene_event_unsubscribes:
            try:
                unsub()
            except Exception as exc:
                if "scene_unsub_failed" not in _LOG_ONCE:
                    logger.warning("Scene unsubscribe failed: %s", exc, exc_info=True)
                    _LOG_ONCE.add("scene_unsub_failed")
        self._scene_event_unsubscribes.clear()

    def track_scene_subscription(self, unsubscribe: Callable[[], None]) -> None:
        if callable(unsubscribe):
            self._scene_event_unsubscribes.append(unsubscribe)

    def _hot_reload_log(self, message: str) -> None:
        self.window.console_log(f"[HotReload] {message}")

    def _create_sprite(self, entity: Dict[str, Any]) -> optional_arcade.arcade.Sprite | None:
        """Turn an entity dictionary into an Arcade Sprite."""
        # Resolve Prefab (with optional variant) using the canonical resolver.
        if entity.get("prefab_id"):
            entity = get_prefab_manager().resolve(entity)

        if not self.window.scene_loader.validate_entity(entity):
            return None
        sprite_path = entity.get("sprite") or "assets/placeholder.png"
        try:
            texture = self.window.assets.get_texture(sprite_path)
            if texture is None:
                print(
                    f"[Mesh][Scene] WARNING: No texture available for '{sprite_path}', skipping entity",
                )
                return None

            sprite = optional_arcade.arcade.Sprite()
            sprite.texture = texture
            sprite.center_x = float(entity.get("x", 0))
            sprite.center_y = float(entity.get("y", 0))
            sprite.scale = float(entity.get("scale", 1.0))
            sprite.angle = float(entity.get("rotation", 0))

            entity_data = dict(entity)
            raw_behaviour_configs = prepare_behaviour_configs(
                entity_data.get("behaviours", []),
                include_metadata=True,
            )
            raw_behaviour_configs = [
                prune_optional_behaviour_defaults(entry)
                for entry in raw_behaviour_configs
            ]
            clean_behaviour_configs = [
                strip_behaviour_metadata(entry)
                for entry in raw_behaviour_configs
            ]
            entity_data["behaviours"] = clean_behaviour_configs
            behaviour_config_root = build_behaviour_config_map(
                entity_data,
                raw_behaviour_configs,
            )
            entity_data["behaviour_config"] = behaviour_config_root

            sprite_any = cast(Any, sprite)
            sprite_any.mesh_name = (
                entity_data.get("mesh_name")
                or entity_data.get("name")
                or entity_data.get("prefab_id")
            )
            sprite_any.mesh_entity_data = entity_data
            sprite_any.mesh_behaviours = [
                cfg.get("type") for cfg in clean_behaviour_configs
            ]
            sprite_any.mesh_behaviour_configs = clean_behaviour_configs
            sprite_any.mesh_behaviours_runtime = []
            sprite_any.mesh_tag = entity_data.get("tag")

            self._apply_collision_poly(sprite, entity_data.get("collision_poly"))
            self._attach_animator(sprite, entity_data)

            self._rebuild_behaviours_for_sprite(sprite)
            spawned_name = format_elite_label(
                str(entity_data.get("name") or entity.get("name") or "<unnamed>"),
                entity_data,
            )
            print(
                "[Mesh][Scene] [+] Spawned "
                f"'{spawned_name}' at ({sprite.center_x}, {sprite.center_y})",
            )
            if not bool(getattr(self, "_suppress_spawn_toasts", False)):
                maybe_enqueue_boss_spawn_toast(self.window, entity_data, self.current_scene_path, seconds=3.0)
                maybe_enqueue_miniboss_spawn_toast(self.window, entity_data, self.current_scene_path, seconds=3.0)
            return sprite
        except Exception as exc:
            if getattr(self.window, "strict_mode", False):
                raise
            if "scene_create_sprite" not in _LOG_ONCE:
                logger.error("Failed to create sprite: %s", exc, exc_info=True)
                _LOG_ONCE.add("scene_create_sprite")
            return None

    def _rebuild_behaviours_for_sprite(self, sprite: optional_arcade.arcade.Sprite) -> None:
        names = [
            str(name)
            for name in getattr(sprite, "mesh_behaviours", [])
            if isinstance(name, str) and name.strip()
        ]
        entity_data = self._ensure_entity_data_dict(sprite)
        config_root = ensure_behaviour_config_root(entity_data)

        runtime_instances: list[Any] = []
        for index, behaviour_name in enumerate(names):
            config_for_behaviour = dict(config_root.get(behaviour_name, {}) or {})
            behaviour = create_behaviour(
                behaviour_name,
                sprite,
                self.window,
                config=config_for_behaviour,
            )
            if behaviour is None:
                continue
            setattr(behaviour, "mesh_behaviour_type", behaviour_name)
            setattr(behaviour, "mesh_behaviour_index", index)
            current_config = getattr(behaviour, "config", None)
            if isinstance(current_config, dict):
                current_config.update(config_for_behaviour)
            else:
                setattr(behaviour, "config", dict(config_for_behaviour))
            runtime_instances.append(behaviour)

        cast(Any, sprite).mesh_behaviours_runtime = runtime_instances

    def _attach_animator(self, sprite: optional_arcade.arcade.Sprite, entity_data: dict[str, Any]) -> None:
        factory = getattr(self.window, "animation_factory", None)
        if factory is None:
            return
        try:
            animator = factory.build_for_entity(
                sprite,
                entity_data,
                debug=self.window.show_debug,
                event_sink=lambda payload, spr=sprite: self._handle_animation_event(spr, payload),
            )
        except Exception as exc:
            logger.error("Failed to build animator: %s", exc, exc_info=True)
            return
        if animator is not None:
            entity_data.setdefault("default_animation", animator.current_state)

    def _update_animation_stage(self, delta_time: float) -> None:
        for sprite in self._iter_layered_sprites():
            if getattr(sprite, "frozen", False):
                continue
            tick_animation_state(sprite, delta_time)
            animator = getattr(sprite, "mesh_animator", None)
            if animator is None:
                continue
            try:
                entity_data = getattr(sprite, "mesh_entity_data", None)
                desired_state = None
                if isinstance(entity_data, dict):
                    raw_state = entity_data.get("animation_state")
                    if isinstance(raw_state, str):
                        desired_state = raw_state
                if desired_state:
                    animator.set_state(desired_state)
                animator.update(delta_time)
            except Exception as exc:
                if getattr(self.window, "strict_mode", False):
                    raise
                if "animator_update" not in _LOG_ONCE:
                    logger.error("Animator update failed: %s", exc, exc_info=True)
                    _LOG_ONCE.add("animator_update")

    def _behaviour_config_copy(self, sprite: optional_arcade.arcade.Sprite) -> dict[str, dict[str, Any]]:
        entity_data = getattr(sprite, "mesh_entity_data", None)
        if not isinstance(entity_data, dict):
            return {}
        root = entity_data.get("behaviour_config")
        if not isinstance(root, dict):
            return {}
        snapshot: dict[str, dict[str, Any]] = {}
        for key, value in root.items():
            if isinstance(key, str) and isinstance(value, dict):
                snapshot[key] = dict(value)
        return snapshot

    def _get_behaviour_configs_for_sprite(self, sprite: optional_arcade.arcade.Sprite) -> list[dict[str, Any]]:
        raw_configs = getattr(sprite, "mesh_behaviour_configs", [])
        normalized: list[dict[str, Any]] = []
        if isinstance(raw_configs, list):
            for entry in raw_configs:
                normalized_entry = normalize_behaviour_entry(entry)
                if normalized_entry is not None:
                    normalized.append(normalized_entry)
        cast(Any, sprite).mesh_behaviour_configs = normalized
        return normalized

    def _ensure_entity_data_dict(self, sprite: optional_arcade.arcade.Sprite) -> dict[str, Any]:
        return self.entities.ensure_entity_data_dict(sprite)

    def _ensure_behaviour_config_root(self, entity_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Ensure entity_data has a valid behaviour_config dict and return it."""
        from .behaviours.utils import ensure_behaviour_config_root
        return ensure_behaviour_config_root(entity_data)

    def _ensure_layers(self, scene_layers: Iterable[Dict[str, Any]]) -> None:
        for layer in scene_layers:
            name = layer.get("name")
            if isinstance(name, str) and name not in self.layers:
                self.layers[name] = optional_arcade.arcade.SpriteList()

    def _clear_layers(self) -> None:
        for sprite_list in self.layers.values():
            sprite_list.clear()
        try:
            self.solid_sprites.clear()
        except RuntimeError:
            self.solid_sprites = optional_arcade.arcade.SpriteList()
        self._clear_tilemap_layers()
        self.window.clear_ui_elements()
        self._scene_index = None

    def _ensure_scene_index(self) -> SceneIndex:
        existing = self._scene_index
        if existing is not None:
            return existing
        # Defensive fallback for non-standard test setups.
        idx = build_scene_index_from_sprites(self.all_sprites)
        self._scene_index = idx
        return idx

    def _clear_tilemap_batching(self) -> None:
        batcher = self._tilemap_batcher
        if batcher is not None:
            try:
                batcher.clear()
            except Exception:
                logger.debug("Tilemap batcher clear failed", exc_info=True)
        self._tilemap_batcher = None
        self._tilemap_batch_state = None

    def _clear_tilemap_layers(self) -> None:
        self._clear_tilemap_batching()
        for sprite_list in self._tilemap_background_layers:
            sprite_list.clear()
        for sprite_list in self._tilemap_foreground_layers:
            sprite_list.clear()
        if self.tilemap_instance and self.tilemap_instance.collision_sprites:
            self.tilemap_instance.collision_sprites.clear()
        self._tilemap_background_layers = []
        self._tilemap_foreground_layers = []
        self._tilemap_draw_layers = []
        self._background_layers = []
        self.tilemap_instance = None
        self.navigation.invalidate()
        try:
            from engine.lighting.occluders import OCCLUDER_CACHE  # noqa: PLC0415

            OCCLUDER_CACHE.invalidate()
        except Exception:  # noqa: BLE001  # REASON: occluder cache invalidation failures should not block tilemap teardown
            logger.debug("Occluder cache invalidation failed", exc_info=True)

    def get_loaded_scene_payload(self) -> Dict[str, Any]:
        return _save_load_proxy.get_loaded_scene_payload(self, scene_load_apply_runtime=_scene_load_apply_runtime)

    def get_authored_scene_payload(self) -> Dict[str, Any]:
        """Return a copy of the scene payload before runtime-only mutations (e.g., themed spawn resolution)."""
        return _save_load_proxy.get_authored_scene_payload(self, scene_load_apply_runtime=_scene_load_apply_runtime, authoring_runtime=_authoring_runtime)

    def debug_apply_authored_scene_payload(self, authored_payload: Dict[str, Any]) -> bool:
        return _save_load_proxy.debug_apply_authored_scene_payload(self, authored_payload, scene_load_apply_runtime=_scene_load_apply_runtime, authoring_runtime=_authoring_runtime)

    # ------------------------------------------------------------------
    # Generic authoring-call proxy
    # ------------------------------------------------------------------

    _authoring_trace_enabled: bool = False
    _authoring_trace_data: dict[str, dict[str, Any]] = {}  # noqa: RUF012

    def _call_authoring(self, fn_name: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch to ``engine.scene_runtime.authoring.<fn_name>(self, *args, **kwargs)``."""
        fn = getattr(_authoring_runtime, fn_name)
        if not self._authoring_trace_enabled:
            return fn(self, *args, **kwargs)
        start = time.perf_counter()
        try:
            return fn(self, *args, **kwargs)
        except Exception as exc:
            entry = self._authoring_trace_data.get(fn_name)
            if entry is not None:
                entry["last_err"] = f"{type(exc).__name__}:{str(exc)[:120]}"
            else:
                self._authoring_trace_data[fn_name] = {
                    "count": 0,
                    "total_ms": 0,
                    "last_err": f"{type(exc).__name__}:{str(exc)[:120]}",
                }
            raise
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            entry = self._authoring_trace_data.get(fn_name)
            if entry is not None:
                entry["count"] += 1
                entry["total_ms"] += elapsed_ms
            else:
                self._authoring_trace_data[fn_name] = {
                    "count": 1,
                    "total_ms": elapsed_ms,
                    "last_err": None,
                }

    # ------------------------------------------------------------------
    # Authoring trace API (debug-only)
    # ------------------------------------------------------------------

    def enable_authoring_trace(self, enabled: bool) -> None:
        """Enable or disable per-function tracing for authoring proxy calls."""
        self._authoring_trace_enabled = bool(enabled)
        if enabled and not isinstance(self.__dict__.get("_authoring_trace_data"), dict):
            self._authoring_trace_data = {}

    def reset_authoring_trace(self) -> None:
        """Clear all accumulated trace data."""
        self._authoring_trace_data = {}

    def get_authoring_trace_snapshot(self, limit: int = 20) -> dict[str, Any]:
        """Return a snapshot of authoring proxy trace stats.

        The returned dict has *schema_version=1*, the *enabled* flag,
        *total_calls*, and a *functions* list sorted by *total_ms* desc
        then *name* asc, capped at *limit* entries.
        """
        data = self._authoring_trace_data
        total_calls = sum(e["count"] for e in data.values())
        items: list[dict[str, Any]] = []
        for name, entry in data.items():
            count = entry["count"]
            total_ms = entry["total_ms"]
            items.append({
                "name": name,
                "count": count,
                "total_ms": total_ms,
                "avg_ms": total_ms // count if count else 0,
                "last_err": entry["last_err"],
            })
        items.sort(key=lambda it: (-it["total_ms"], it["name"]))
        return {
            "schema_version": 1,
            "enabled": self._authoring_trace_enabled,
            "total_calls": total_calls,
            "functions": items[:limit],
        }

    def refresh_tilemap_layers(self) -> bool:
        """Debug-only: rebuild tilemap sprite layers from the current loaded scene payload."""
        scene_path = str(self.current_scene_path or "").strip()
        if not scene_path:
            return False
        scene = self._loaded_scene_data
        if not isinstance(scene, dict):
            return False
        tilemap = scene.get("tilemap")
        if not isinstance(tilemap, dict) or "tile_layers" not in tilemap:
            return False
        scene_file = resolve_path(scene_path)
        self._clear_tilemap_layers()
        self._load_tilemap_layers(scene, scene_file.parent)
        return True

    def debug_find_sprite_by_entity_id(self, entity_id: str) -> optional_arcade.arcade.Sprite | None:
        return self._call_authoring("debug_find_sprite_by_entity_id", entity_id)

    def _debug_iter_authoring_payloads(self) -> list[Dict[str, Any]]:
        return self._call_authoring("_debug_iter_authoring_payloads")

    def _debug_remove_sprite(self, sprite: optional_arcade.arcade.Sprite) -> None:
        self._call_authoring("_debug_remove_sprite", sprite)

    def debug_add_entity_payload(self, entity_payload: Dict[str, Any]) -> bool:
        return self._call_authoring("debug_add_entity_payload", entity_payload)

    def debug_remove_entity_by_id(self, entity_id: str) -> bool:
        return self._call_authoring("debug_remove_entity_by_id", entity_id)

    def debug_move_entity_by_id(self, entity_id: str, *, x: float, y: float) -> bool:
        return self._call_authoring("debug_move_entity_by_id", entity_id, x=x, y=y)

    def debug_duplicate_entities_by_ids(self, ids: list[str], *, dx: float, dy: float) -> dict[str, str]:
        return self._call_authoring("debug_duplicate_entities_by_ids", ids, dx=dx, dy=dy)

    def debug_copy_entities_by_ids(
        self,
        ids: list[str],
        *,
        primary_id: str | None = None,
    ) -> Dict[str, Any] | None:
        """
        Debug-only: copy selected authored entities into a clipboard payload (no mutation).

        - Operates on the authored scene payload.
        - Skips player entities silently.
        - Deterministic: entities sorted by orig_id.
        """
        return self._call_authoring("debug_copy_entities_by_ids", ids, primary_id=primary_id)

    def debug_paste_entities_from_clipboard(
        self,
        clipboard: Dict[str, Any],
        *,
        anchor_x: float,
        anchor_y: float,
        snap_to_tile: bool = False,
    ) -> tuple[list[str], str]:
        """
        Debug-only: paste entities from a clipboard payload into the authored scene payload.

        - Deterministic id scheme: <orig_id>__paste<k>, with k starting at 0.
        - Deterministic ordering: paste in sorted orig_id order.
        - Returns (pasted_ids_sorted, pasted_primary_id).
        """
        return self._call_authoring(
            "debug_paste_entities_from_clipboard", clipboard,
            anchor_x=anchor_x, anchor_y=anchor_y, snap_to_tile=snap_to_tile,
        )

    def debug_transform_entities_by_ids(
        self,
        ids: list[str],
        *,
        op: str,
        snap_to_tile: bool = False,
    ) -> int:
        """
        Debug-only: transform authored entities around the selection centroid.

        Supported ops:
        - "rotate_cw_90"
        - "flip_x"
        - "flip_y"

        Returns the number of entities transformed.
        """
        return self._call_authoring("debug_transform_entities_by_ids", ids, op=op, snap_to_tile=snap_to_tile)

    def debug_set_prefab_id(self, selected_ids: list[str], prefab_id: str) -> tuple[int, int]:
        return self._call_authoring("debug_set_prefab_id", selected_ids, prefab_id)

    def debug_add_behaviour(self, selected_ids: list[str], behaviour_name: str) -> tuple[int, int]:
        return self._call_authoring("debug_add_behaviour", selected_ids, behaviour_name)

    def debug_remove_behaviour(self, selected_ids: list[str], behaviour_name: str) -> tuple[int, int]:
        return self._call_authoring("debug_remove_behaviour", selected_ids, behaviour_name)

    def debug_set_name(self, primary_id: str, name: str) -> tuple[int, int]:
        return self._call_authoring("debug_set_name", primary_id, name)

    def debug_add_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int]:
        return self._call_authoring("debug_add_tag", selected_ids, tag)

    def debug_remove_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int]:
        return self._call_authoring("debug_remove_tag", selected_ids, tag)

    def debug_toggle_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int, int]:
        return self._call_authoring("debug_toggle_tag", selected_ids, tag)

    def debug_batch_rename(self, selected_ids: list[str], prefix: str = "", suffix: str = "") -> tuple[int, int]:
        return self._call_authoring("debug_batch_rename", selected_ids, prefix=prefix, suffix=suffix)

    def debug_set_names(self, entity_ids: list[str], base: str, start: int = 1, width: int = 3) -> dict:
        return self._call_authoring("debug_set_names", entity_ids, base, start=start, width=width)

    def debug_align_selection(
        self,
        entity_ids: list[str],
        axis: str,
        mode: str,
        reference: str = "primary",
        primary_id: str = "",
    ) -> dict:
        return _selection_proxy.debug_align_selection(self, entity_ids, axis, mode, reference=reference, primary_id=primary_id)

    def debug_distribute_selection(
        self,
        entity_ids: list[str],
        axis: str,
        mode: str = "gap",
        reference: str = "group",
        primary_id: str = "",
    ) -> dict:
        return _selection_proxy.debug_distribute_selection(self, entity_ids, axis, mode=mode, reference=reference, primary_id=primary_id)

    def debug_snap_to_grid(
        self,
        entity_ids: list[str],
        step: int,
        axes: str = "xy",
        mode: str = "nearest",
    ) -> dict:
        return _selection_proxy.debug_snap_to_grid(self, entity_ids, step, axes=axes, mode=mode)

    def debug_nudge_selection(
        self,
        entity_ids: list[str],
        dx: float,
        dy: float,
        count: int = 1,
        step: float | None = None,
    ) -> dict:
        return _selection_proxy.debug_nudge_selection(self, entity_ids, dx, dy, count=count, step=step)

    def debug_rotate_selection(
        self,
        entity_ids: list[str],
        deg: float,
        about: str = "self",
        primary_id: str = "",
    ) -> dict:
        return _selection_proxy.debug_rotate_selection(self, entity_ids, deg, about=about, primary_id=primary_id)

    def debug_mirror_selection(
        self,
        entity_ids: list[str],
        axis: str,
        about: str = "group",
        primary_id: str = "",
        include_rotation: bool = True,
    ) -> dict:
        return _selection_proxy.debug_mirror_selection(self, entity_ids, axis, about=about, primary_id=primary_id, include_rotation=include_rotation)

    def debug_group_selection(
        self,
        entity_ids: list[str],
        name_base: str = "Group",
        about: str = "group",
        primary_id: str = "",
    ) -> dict:
        return _selection_proxy.debug_group_selection(self, entity_ids, name_base=name_base, about=about, primary_id=primary_id)

    def debug_ungroup_selection(
        self,
        entity_ids: list[str],
        mode: str = "auto",
    ) -> dict:
        return _selection_proxy.debug_ungroup_selection(self, entity_ids, mode=mode)

    def debug_duplicate_to_grid(
        self,
        entity_ids: list[str],
        rows: int = 1,
        cols: int = 1,
        dx: float = 0.0,
        dy: float = 0.0,
        origin: str = "selection",
        include_original: bool = True,
        name_mode: str = "none",
    ) -> dict:
        return _selection_proxy.debug_duplicate_to_grid(self, entity_ids, rows=rows, cols=cols, dx=dx, dy=dy, origin=origin, include_original=include_original, name_mode=name_mode)

    def debug_duplicate_along_path(
        self,
        entity_ids: list[str],
        from_x: float = 0.0,
        from_y: float = 0.0,
        to_x: float = 0.0,
        to_y: float = 0.0,
        count: int = 2,
        include_original: bool = True,
        origin: str = "selection",
        name_mode: str = "none",
        orient: bool = False,
    ) -> dict:
        return _selection_proxy.debug_duplicate_along_path(self, entity_ids, from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y, count=count, include_original=include_original, origin=origin, name_mode=name_mode, orient=orient)

    def debug_scatter_selection(
        self,
        entity_ids: list[str],
        n: int = 1,
        shape: str = "circle",
        radius: float = 64.0,
        width: float = 128.0,
        height: float = 128.0,
        center: str = "group",
        seed: int = 0,
        jitter_rot_deg: float = 0.0,
        snap_step: int | None = None,
        include_original: bool = True,
        name_mode: str = "none",
    ) -> dict:
        return _selection_proxy.debug_scatter_selection(self, entity_ids, n=n, shape=shape, radius=radius, width=width, height=height, center=center, seed=seed, jitter_rot_deg=jitter_rot_deg, snap_step=snap_step, include_original=include_original, name_mode=name_mode)

    def debug_config_triggerzone_set_zone_id(self, selected_ids: list[str], zone_id: str) -> tuple[int, int, int]:
        """
        Debug-only: set behaviour_config.TriggerZone.zone_id for selected entities that have TriggerZone.

        Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
        """
        return self._call_authoring("debug_config_triggerzone_set_zone_id", selected_ids, zone_id)

    def debug_config_triggerzone_set_radius(self, selected_ids: list[str], trigger_radius: float) -> tuple[int, int, int]:
        """
        Debug-only: set behaviour_config.TriggerZone.trigger_radius for selected entities that have TriggerZone.

        Returns (changed_count, skipped_player_count, skipped_missing_behaviour_count).
        """
        return self._call_authoring("debug_config_triggerzone_set_radius", selected_ids, trigger_radius)







    def _debug_config_entity_has_behaviour(self, entity_payload: dict[str, Any], behaviour_name: str) -> bool:
        return self._call_authoring("_debug_config_entity_has_behaviour", entity_payload, behaviour_name)

    def _debug_config_mutate_for_behaviour(
        self,
        selected_ids: list[str],
        *,
        behaviour_name: str,
        mutate: "Callable[[dict[str, Any]], bool]",
    ) -> tuple[int, int, int]:
        return self._call_authoring(
            "_debug_config_mutate_for_behaviour",
            selected_ids,
            behaviour_name=behaviour_name,
            mutate=mutate,
        )

    def _debug_config_set_field_for_behaviour(
        self,
        selected_ids: list[str],
        *,
        behaviour_name: str,
        field_path: tuple[str, ...],
        value: Any,
    ) -> tuple[int, int, int]:
        return self._call_authoring(
            "_debug_config_set_field_for_behaviour",
            selected_ids,
            behaviour_name=behaviour_name,
            field_path=field_path,
            value=value,
        )

    def debug_build_macro_objective_zone_payload(
        self,
        *,
        center_x: float,
        center_y: float,
        zone_id: str,
        set_flag: str,
        radius: float,
        toast: str | None,
        require_flags: list[str] | None = None,
        forbid_flags: list[str] | None = None,
        toast_seconds: float | None = None,
    ) -> tuple[Dict[str, Any], int, int]:
        """
        Debug-only: build a new authored scene payload with a TriggerZone + SetGameStateOnEvent pair.

        Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
        """
        return self._call_authoring(
            "debug_build_macro_objective_zone_payload",
            center_x=center_x,
            center_y=center_y,
            zone_id=zone_id,
            set_flag=set_flag,
            radius=radius,
            toast=toast,
            require_flags=require_flags,
            forbid_flags=forbid_flags,
            toast_seconds=toast_seconds,
        )

    def debug_build_macro_door_transition_payload(
        self,
        *,
        center_x: float,
        center_y: float,
        target_scene: str,
        spawn_id: str,
        primary_id: str | None,
        require_flags: list[str] | None = None,
        forbid_flags: list[str] | None = None,
    ) -> tuple[Dict[str, Any], int, int]:
        """
        Debug-only: build a new authored scene payload that ensures a SceneTransition exists or is updated.

        Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
        """
        return self._call_authoring(
            "debug_build_macro_door_transition_payload",
            center_x=center_x,
            center_y=center_y,
            target_scene=target_scene,
            spawn_id=spawn_id,
            primary_id=primary_id,
            require_flags=require_flags,
            forbid_flags=forbid_flags,
        )

    def debug_build_macro_dialogue_choice_flag_payload(
        self,
        *,
        speaker_id: str,
        choice_id: str,
        choice_text: str,
        set_flag: str,
        toast: str | None,
    ) -> tuple[Dict[str, Any], int, int]:
        """
        Debug-only: build a new authored payload that ensures a Dialogue choice and a SetGameStateOnEvent hook exist.

        Returns (new_payload, created_count, updated_count). Does not mutate scene state by itself.
        """
        return self._call_authoring(
            "debug_build_macro_dialogue_choice_flag_payload",
            speaker_id=speaker_id,
            choice_id=choice_id,
            choice_text=choice_text,
            set_flag=set_flag,
            toast=toast,
        )

    def _debug_preview_diff(self, before_payload: Dict[str, Any], after_payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._call_authoring("_debug_preview_diff", before_payload, after_payload)

    def debug_preview_macro_objective_zone(
        self,
        *,
        center_x: float,
        center_y: float,
        zone_id: str,
        set_flag: str,
        radius: float,
        toast: str | None,
        require_flags: list[str] | None = None,
        forbid_flags: list[str] | None = None,
        toast_seconds: float | None = None,
    ) -> Dict[str, Any]:
        return self._call_authoring(
            "debug_preview_macro_objective_zone",
            center_x=center_x,
            center_y=center_y,
            zone_id=zone_id,
            set_flag=set_flag,
            radius=radius,
            toast=toast,
            require_flags=require_flags,
            forbid_flags=forbid_flags,
            toast_seconds=toast_seconds,
        )

    def debug_preview_macro_door_transition(
        self,
        *,
        center_x: float,
        center_y: float,
        target_scene: str,
        spawn_id: str,
        primary_id: str | None,
    ) -> Dict[str, Any]:
        return self._call_authoring(
            "debug_preview_macro_door_transition",
            center_x=center_x,
            center_y=center_y,
            target_scene=target_scene,
            spawn_id=spawn_id,
            primary_id=primary_id,
        )

    def debug_preview_macro_dialogue_choice_flag(
        self,
        *,
        speaker_id: str,
        choice_id: str,
        choice_text: str,
        set_flag: str,
        toast: str | None,
    ) -> Dict[str, Any]:
        return self._call_authoring(
            "debug_preview_macro_dialogue_choice_flag",
            speaker_id=speaker_id,
            choice_id=choice_id,
            choice_text=choice_text,
            set_flag=set_flag,
            toast=toast,
        )

    def _load_tilemap_layers(self, scene: Dict[str, Any], scene_dir: Path) -> None:
        _scene_load_apply_runtime.load_tilemap_layers(
            self,
            scene,
            scene_dir,
            logger=logger,
            log_once=_LOG_ONCE,
            load_tilemap_func=lambda *args, **kwargs: load_tilemap(*args, **kwargs),
        )

    def _init_tilemap_batching(self, instance: TilemapInstance) -> None:
        map_w, map_h = instance.map_size
        tile_w, tile_h = instance.tile_size
        if map_w <= 0 or map_h <= 0 or tile_w <= 0 or tile_h <= 0:
            self._clear_tilemap_batching()
            return
        chunk_size = int(getattr(self.window, "tilemap_chunk_size", 16) or 16)
        if chunk_size <= 0:
            chunk_size = 16
        state = TilemapBatchState(
            map_width=map_w,
            map_height=map_h,
            tile_width=tile_w,
            tile_height=tile_h,
            chunk_size_tiles=chunk_size,
        )
        for layer_id in instance.layer_data.keys():
            state.mark_layer_dirty(layer_id)
        self._tilemap_batch_state = state
        self._tilemap_batcher = TilemapBatcher(self.window, state)

    def _apply_tilemap_world_bounds(self, instance: TilemapInstance) -> None:
        if instance is None:
            return
        map_w, map_h = instance.map_size
        tile_w, tile_h = instance.tile_size
        if map_w <= 0 or map_h <= 0 or tile_w <= 0 or tile_h <= 0:
            return
        width_px = int(map_w * tile_w)
        height_px = int(map_h * tile_h)

        if self.window.world_width is None or self.window.world_width <= 0:
            self.window.world_width = width_px
        if self.window.world_height is None or self.window.world_height <= 0:
            self.window.world_height = height_px

        if self.window.camera_controller.bounds is None and width_px > 0 and height_px > 0:
            self.window.camera_controller.bounds = (0.0, 0.0, float(width_px), float(height_px))

    def _mark_tilemap_layer_dirty(self, layer_id: str) -> None:
        state = self._tilemap_batch_state
        if state is None:
            return
        try:
            state.mark_layer_dirty_all(str(layer_id))
        except Exception:
            logger.debug("mark_tilemap_layer_dirty failed for %r", layer_id, exc_info=True); return

    def invalidate_tilemap_batches(self) -> int:
        count = 0
        if self._tilemap_batcher is not None:
            try:
                count = int(self._tilemap_batcher.invalidate_batches())
            except Exception:
                logger.debug("invalidate_tilemap_batches failed", exc_info=True); count = 0
        state = self._tilemap_batch_state
        if state is not None and count == 0:
            layer_ids = list(state.layer_versions.keys())
            for layer_id in layer_ids:
                state.mark_layer_dirty_all(layer_id)
            count = len(layer_ids)
        return count

    def _mark_tilemap_tile_dirty(self, layer_id: str, col: int, row: int) -> None:
        state = self._tilemap_batch_state
        if state is None:
            return
        try:
            state.mark_tile_dirty(str(layer_id), int(col), int(row))
        except Exception:
            logger.debug("mark_tilemap_tile_dirty failed layer=%r", layer_id, exc_info=True); return

    def _layer_draw_order(self) -> Iterable[optional_arcade.arcade.SpriteList]:
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

    def _layer_update_order(self) -> list[str]:
        preferred = ["background", "entities", "foreground"]
        ordered: list[str] = []
        seen: set[str] = set()
        for name in preferred:
            if name in self.layers:
                ordered.append(name)
                seen.add(name)
        for name in self.layers.keys():
            if name not in seen:
                ordered.append(name)
        return ordered

    def _iter_layered_sprites(self) -> Iterable[optional_arcade.arcade.Sprite]:
        for layer_name in self._layer_update_order():
            layer = self.layers.get(layer_name)
            if layer is None:
                continue
            for sprite in layer:
                yield sprite

    def _deliver_events_to_behaviours(self, events: Sequence[MeshEvent]) -> None:
        for event in events:
            for sprite in self._iter_layered_sprites():
                behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
                if not behaviours:
                    continue
                for behaviour in behaviours:
                    on_event = getattr(behaviour, "on_event", None)
                    if not callable(on_event):
                        continue
                    try:
                        on_event(event)
                    except Exception as exc:  # noqa: BLE001  # REASON: non-strict behaviour event delivery failures should report and continue dispatching remaining behaviours
                        if getattr(self.window, "strict_mode", False):
                            raise
                        entity_name = getattr(sprite, "mesh_name", "<unnamed>")
                        print(
                            f"[Mesh][Events] ERROR delivering '{event.type}' to"
                            f" {behaviour} on {entity_name}: {exc}",
                        )

    def _pre_update_behaviour_stage(self, delta_time: float) -> None:
        for sprite in self._iter_layered_sprites():
            if getattr(sprite, "frozen", False):
                continue
            behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
            for behaviour in behaviours:
                pre = getattr(behaviour, "pre_update", None)
                if callable(pre):
                    pre(delta_time)

    def _update_behaviour_stage(self, delta_time: float) -> None:
        for sprite in self._iter_layered_sprites():
            if getattr(sprite, "frozen", False):
                continue
            for behaviour in getattr(sprite, "mesh_behaviours_runtime", []):
                behaviour.update(delta_time)

    def _update_movement_stage(self, delta_time: float) -> None:
        for layer_name in self._layer_update_order():
            layer = self.layers.get(layer_name)
            if layer is not None:
                for sprite in layer:
                    if not getattr(sprite, "frozen", False):
                        sprite.update()

    def _late_update_stage(self, delta_time: float) -> None:
        for sprite in self._iter_layered_sprites():
            if getattr(sprite, "frozen", False):
                continue
            behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
            for behaviour in behaviours:
                late = getattr(behaviour, "late_update", None)
                if callable(late):
                    late(delta_time)

    def _rebuild_ui_for_scene(self) -> None:
        self.window.clear_ui_elements()
        print("[Mesh][UI] Rebuilding UI for scene")

        from .ui import PERSISTENT_UI_ATTRS

        for attr_name in PERSISTENT_UI_ATTRS:
            element = getattr(self.window, attr_name, None)
            if element is not None:
                self.window.register_ui_element(element)

        self.window.register_ui_element(EntityInspector(self.window))
        self.window.register_ui_element(AnimationStateOverlay(self.window))
        self.window.register_ui_element(DevConsole(self.window))

        # Update UIController specific elements
        self.window.ui_controller.inventory_overlay = InventoryOverlay(self.window)
        self.window.register_ui_element(self.window.ui_controller.inventory_overlay)

        self.window.ui_controller.dialogue_box = DialogueBox(self.window)
        self.window.register_ui_element(self.window.ui_controller.dialogue_box)

        self.window.ui_controller.quest_log = QuestLog(self.window)
        self.window.register_ui_element(self.window.ui_controller.quest_log)

        self.window.ui_controller.shop_panel = ShopPanel(self.window)
        self.window.register_ui_element(self.window.ui_controller.shop_panel)

        self.window.ui_controller.character_panel = CharacterPanel(self.window)
        self.window.register_ui_element(self.window.ui_controller.character_panel)

        try:
            from .behaviours.health import Health
        except ImportError:
            return
        except Exception as exc:
            if "scene_import_health" not in _LOG_ONCE:
                logger.error("Unexpected error importing Health behaviour: %s", exc, exc_info=True)
                _LOG_ONCE.add("scene_import_health")
            return

        for sprite in self.all_sprites:
            behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
            if not behaviours:
                continue
            if any(isinstance(behaviour, Health) for behaviour in behaviours):
                print(
                    "[Mesh][UI] Registering HealthBar for",
                    getattr(sprite, "mesh_name", "<unnamed>"),
                )
                self.window.register_ui_element(HealthBar(self.window, sprite))

    def find_entity(self, identifier: str | int) -> optional_arcade.arcade.Sprite | None:
        """Find an entity by ID (index in all_sprites) or name."""
        return self.entities.find_entity(self, identifier)

    def get_all_entities(self) -> list[optional_arcade.arcade.Sprite]:
        """Return a stable list of all entities."""
        return self.entities.iter_entities(self)

    def find_sprite_by_name(self, name: str | None) -> optional_arcade.arcade.Sprite | None:
        """Return the first sprite whose mesh_name matches the provided value."""
        return self.entities.find_sprite_by_name(self, name)

    def _find_player_sprite(self) -> optional_arcade.arcade.Sprite | None:
        return self.entities.find_primary_player_sprite(self)

    def _find_spawn_marker(self, spawn_id: str) -> optional_arcade.arcade.Sprite | None:
        return _find_spawn_marker_runtime(self.all_sprites, spawn_id)

    def get_spawn(self, spawn_id: str | None) -> dict[str, Any] | None:
        return _get_spawn_runtime(self._loaded_scene_data, spawn_id)

    def apply_spawn(self, spawn_id: str | None) -> None:
        player = self._find_player_sprite()
        if player is None:
            return
        spawn = self.get_spawn(spawn_id)
        if spawn is None:
            return

        x = spawn.get("x")
        y = spawn.get("y")
        facing = spawn.get("facing")
        self._apply_entity_mutation(
            player,
            x=float(x) if x is not None else None,
            y=float(y) if y is not None else None,
        )
        if facing is not None:
            try:
                setattr(player, "facing", facing)
            except Exception as exc:
                if "scene_set_facing" not in _LOG_ONCE:
                    logger.warning("Failed to set player facing: %s", exc, exc_info=True)
                    _LOG_ONCE.add("scene_set_facing")
            entity_data = getattr(player, "mesh_entity_data", None)
            if isinstance(entity_data, dict):
                entity_data["facing"] = facing

    def _apply_pending_spawn_point(self) -> None:
        _apply_pending_spawn_point_runtime(self)

    def _apply_scene_settings(self, settings: Dict[str, Any]) -> None:
        _save_load_proxy.apply_scene_settings(self, settings, scene_load_apply_runtime=_scene_load_apply_runtime)

    def _apply_scene_state(self, state_block: Any) -> None:
        _save_load_proxy.apply_scene_state(self, state_block, scene_load_apply_runtime=_scene_load_apply_runtime, apply_scene_state_runtime=_apply_scene_state_runtime)

    def _configure_camera_from_scene(self, settings: Dict[str, Any]) -> None:
        self.window.camera_controller.configure_from_scene(settings)

    def get_sprites_in_layer(self, layer_name: str) -> optional_arcade.arcade.SpriteList | None:
        return self.layers.get(layer_name)

    def set_tile(self, layer_name: str, col: int, row: int, gid: int) -> tuple[int, int] | None:
        """Set a tile in the loaded tilemap; returns (old, new) or None on failure."""
        if not self.tilemap_instance:
            return None
        data = self.tilemap_instance.layer_data.get(layer_name)
        if data is None:
            return None
        width, height = self.tilemap_instance.layer_dimensions or (0, 0)
        if width <= 0 or height <= 0:
            return None
        if not (0 <= col < width and 0 <= row < height):
            return None
        index = row * width + col
        old_gid = int(data[index] if index < len(data) else 0)
        if gid == old_gid:
            return None
        if index >= len(data):
            return None
        data[index] = int(gid)
        sprites = self.tilemap_instance.layer_lookup.get(layer_name)
        tile_w, tile_h = self.tilemap_instance.tile_size
        offset = self.tilemap_instance.layer_offsets.get(layer_name, (0.0, 0.0))
        map_pixel_height = height * tile_h
        center_x = (col + 0.5) * tile_w + offset[0]
        center_y = map_pixel_height - ((row + 0.5) * tile_h) + offset[1]
        if sprites:
            # Remove existing sprite at this location
            for sprite in list(sprites):
                if abs(sprite.center_x - center_x) < 0.1 and abs(sprite.center_y - center_y) < 0.1:
                    sprites.remove(sprite)
        if gid != 0 and sprites is not None:
            tileset = None
            for ts in self.tilemap_instance.tilesets:
                if ts.contains(gid):
                    tileset = ts
                    break
            if tileset:
                local_id = gid - tileset.first_gid
                tilemap_manager = cast(Any, self.window.tilemap_manager)
                texture = tilemap_manager._get_tile_texture(tileset, local_id)
                if texture:
                    sprite = optional_arcade.arcade.Sprite()
                    sprite.texture = texture
                    sprite.center_x = center_x
                    sprite.center_y = center_y
                    sprite.scale = 1.0
                    sprites.append(sprite)
        self._mark_tilemap_tile_dirty(layer_name, col, row)
        return (old_gid, gid)

    def build_scene_snapshot(self, compact: bool = False) -> Dict[str, Any]:
        """Build a JSON-serializable snapshot of the current scene state."""
        return _save_load_proxy.build_scene_snapshot(self, compact=compact, build_scene_snapshot_runtime=_build_scene_snapshot_runtime)

    def move_entity_with_collision(
        self,
        sprite: optional_arcade.arcade.Sprite,
        dx: float,
        dy: float,
        friction: float = 1.0,
    ) -> None:
        # Simple AABB collision resolution

        # X-axis
        sprite.center_x += dx
        hit_list = optional_arcade.arcade.check_for_collision_with_list(sprite, self.solid_sprites)
        if hit_list:
            if dx > 0:
                # Moving right: snap to left of wall
                min_left = min(wall.left for wall in hit_list)
                sprite.right = min_left
            elif dx < 0:
                # Moving left: snap to right of wall
                max_right = max(wall.right for wall in hit_list)
                sprite.left = max_right

        # Y-axis
        sprite.center_y += dy
        hit_list = optional_arcade.arcade.check_for_collision_with_list(sprite, self.solid_sprites)
        if hit_list:
            if dy > 0:
                # Moving up: snap to bottom of wall
                min_bottom = min(wall.bottom for wall in hit_list)
                sprite.top = min_bottom
            elif dy < 0:
                # Moving down: snap to top of wall
                max_top = max(wall.top for wall in hit_list)
                sprite.bottom = max_top

    def _handle_animation_event(self, sprite: optional_arcade.arcade.Sprite, payload: Dict[str, Any]) -> None:
        data = dict(payload or {})
        data.setdefault("entity", getattr(sprite, "mesh_name", "<unnamed>"))
        data.setdefault("state", data.get("state"))
        data.setdefault("event", data.get("event"))
        data.setdefault("frame", data.get("frame"))
        data.setdefault("loop", data.get("loop", 0))
        data.setdefault("tag", getattr(sprite, "mesh_tag", None))
        motion = self._apply_animation_root_motion(sprite, data)
        data["position"] = (float(sprite.center_x), float(sprite.center_y))
        if motion is not None:
            dx, dy = motion
            data.setdefault("root_motion", {"dx": dx, "dy": dy})
        self.window.emit_signal(EVENT_ANIMATION_EVENT, **data)
        if self.window.show_debug:
            print(
                "[Mesh][Animation] EVENT",
                f"{data['entity']}::{data.get('state', '<unknown>')} -> {data.get('event', '<none>')}",
                f"(frame {data.get('frame')}, loop {data.get('loop')})",
            )

    def _apply_animation_root_motion(
        self,
        sprite: optional_arcade.arcade.Sprite,
        event_data: Dict[str, Any],
    ) -> tuple[float, float] | None:
        config = self._resolve_root_motion_config(sprite)
        if config is None:
            return None
        labels = config.get("labels")
        if labels and event_data.get("event") not in labels:
            return None

        dx, dy = self._extract_root_motion_vector(event_data)
        if dx == 0.0 and dy == 0.0:
            return None

        scale = config.get("scale", 1.0) * self._coerce_float(event_data.get("move_scale", 1.0), 1.0)
        dx *= scale
        dy *= scale

        space = str(event_data.get("space") or config.get("space", "local")).lower()
        if space not in {"local", "world"}:
            space = config.get("space", "local")

        if space == "local":
            angle = math.radians(float(getattr(sprite, "angle", 0.0)))
            world_dx = dx * math.cos(angle) - dy * math.sin(angle)
            world_dy = dx * math.sin(angle) + dy * math.cos(angle)
            dx, dy = world_dx, world_dy

        use_collision = bool(event_data.get("move_collision", config.get("collision", True)))
        if use_collision:
            self.move_entity_with_collision(sprite, dx, dy, 1.0)
        else:
            sprite.center_x += dx
            sprite.center_y += dy

        entity_data = self._ensure_entity_data_dict(sprite)
        entity_data["x"] = float(sprite.center_x)
        entity_data["y"] = float(sprite.center_y)
        return (dx, dy)

    def _resolve_root_motion_config(self, sprite: optional_arcade.arcade.Sprite) -> dict[str, Any] | None:
        cache = getattr(sprite, "_mesh_root_motion_config", None)
        if isinstance(cache, dict):
            return cache

        entity_data = getattr(sprite, "mesh_entity_data", None)
        if not isinstance(entity_data, dict):
            return None

        raw = entity_data.get("animation_root_motion")
        config = self._normalize_root_motion_config(raw)
        if config is not None:
            setattr(sprite, "_mesh_root_motion_config", config)
        return config

    def _normalize_root_motion_config(self, raw: Any) -> dict[str, Any] | None:
        if raw is None:
            return None
        enabled = True
        settings: dict[str, Any]
        if isinstance(raw, bool):
            enabled = raw
            settings = {}
        elif isinstance(raw, (int, float)):
            enabled = raw != 0
            settings = {"scale": float(raw)}
        elif isinstance(raw, dict):
            settings = dict(raw)
            enabled = bool(settings.pop("enabled", True))
        else:
            return None

        if not enabled:
            return None

        labels = settings.get("labels")
        label_set: set[str] | None = None
        if isinstance(labels, str):
            cleaned = labels.strip()
            label_set = {cleaned} if cleaned else None
        elif isinstance(labels, (list, tuple, set)):
            cleaned = {str(value).strip() for value in labels if isinstance(value, (str, int, float))}
            label_set = {entry for entry in cleaned if entry}
            if not label_set:
                label_set = None

        return {
            "scale": float(settings.get("scale", 1.0)),
            "space": str(settings.get("space", "local")).lower(),
            "collision": bool(settings.get("collision", True)),
            "labels": label_set,
        }

    def _extract_root_motion_vector(self, event_data: Dict[str, Any]) -> tuple[float, float]:
        move = event_data.get("move")
        dx, dy = self._coerce_motion_vector(move)
        if dx == 0.0 and dy == 0.0:
            displacement = event_data.get("displacement") or event_data.get("translate")
            dx, dy = self._coerce_motion_vector(displacement)
        if dx == 0.0 and dy == 0.0:
            dx = self._coerce_float(event_data.get("dx"), 0.0)
            dy = self._coerce_float(event_data.get("dy"), 0.0)
        return (dx, dy)

    def on_collectible_picked(self, collectible: optional_arcade.arcade.Sprite, collector: optional_arcade.arcade.Sprite) -> None:
        payload = {
            "collectible_name": getattr(collectible, "mesh_name", "<unnamed>"),
            "collector": getattr(collector, "mesh_name", "<unnamed>"),
            "position": (float(collectible.center_x), float(collectible.center_y)),
        }
        self.window.emit_signal(EVENT_COLLECTIBLE_PICKED, **payload)
        self.window.console_log(
            f"Collected {payload['collectible_name']} by {payload['collector']}",
        )

    def on_damage(self, source: optional_arcade.arcade.Sprite, target: optional_arcade.arcade.Sprite, amount: float) -> None:
        payload = {
            "source": getattr(source, "mesh_name", "<unnamed>"),
            "target": getattr(target, "mesh_name", "<unnamed>"),
            "amount": float(amount),
        }
        request_animation_state(source, "attack", priority=20.0, ttl=0.25)
        request_animation_state(target, "hit", priority=40.0, ttl=0.45)
        self.window.emit_signal(EVENT_DAMAGE_APPLIED, **payload)
        self.window.console_log(
            f"{payload['source']} dealt {payload['amount']:.1f} damage to {payload['target']}",
        )

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _coerce_optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _coerce_motion_vector(self, value: Any) -> tuple[float, float]:
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return (self._coerce_float(value[0]), self._coerce_float(value[1]))
        if isinstance(value, dict):
            return (
                self._coerce_float(value.get("x", 0.0)),
                self._coerce_float(value.get("y", 0.0)),
            )
        return (0.0, 0.0)

    def add_sprite_to_layer(self, sprite: optional_arcade.arcade.Sprite, layer_name: str = "entities") -> None:
        """Add a sprite to a specific layer at runtime."""
        if layer_name not in self.layers:
            self.layers[layer_name] = optional_arcade.arcade.SpriteList()
        self.layers[layer_name].append(sprite)

        # If it has behaviours, initialize them
        self._rebuild_behaviours_for_sprite(sprite)

    def _resolve_legacy_spawns(self, scene_data: Dict[str, Any], encounter_set: Any, theme: Any) -> None:
        settings = scene_data.get("settings", {})
        seed_val = 0
        if self.current_scene_path:
            seed_val = sum(ord(c) for c in self.current_scene_path)
        rng = random.Random(seed_val)

        variant_id = encounter_set.variant_id or theme.default_variant_id

        for entity in scene_data.get("entities", []):
            if entity.get("prefab_id") == "theme_enemy_placeholder":
                chosen = rng.choice(encounter_set.enemy_prefab_ids)
                if isinstance(chosen, dict):
                    pid = chosen.get("prefab_id")
                    if isinstance(pid, str) and pid.strip():
                        entity["prefab_id"] = pid.strip()
                    else:
                        continue
                    if "variant_id" not in entity:
                        v = chosen.get("variant_id")
                        if isinstance(v, str) and v.strip():
                            entity["variant_id"] = v.strip()
                else:
                    entity["prefab_id"] = chosen
                if encounter_set.drop_table_id and "drop_table_id" not in entity:
                    entity["drop_table_id"] = encounter_set.drop_table_id

                if variant_id and "variant_id" not in entity:
                    entity["variant_id"] = variant_id

    def _resolve_budgeted_spawns(self, scene_data: Dict[str, Any], encounter_set: Any, theme: Any) -> None:
        settings = scene_data.get("settings", {})

        preset_id_raw = settings.get("encounter_preset_id")
        preset_id = preset_id_raw.strip() if isinstance(preset_id_raw, str) and preset_id_raw.strip() else None
        if preset_id is None:
            difficulty_raw = settings.get("encounter_budget_profile")
            preset_id = difficulty_raw.strip() if isinstance(difficulty_raw, str) and difficulty_raw.strip() else None

        preset: dict | None = None
        if preset_id:
            try:
                preset = get_theme_manager().get_encounter_preset(preset_id)
            except Exception:
                logger.debug("Encounter preset lookup failed for %r", preset_id, exc_info=True); preset = None

        base_budget = settings.get("encounter_budget")
        if base_budget is None and preset is not None and preset.get("encounter_budget") is not None:
            base_budget = preset.get("encounter_budget")

        # If no global budget and no group budgets, use legacy
        group_budgets = settings.get("encounter_group_budgets", {})
        if base_budget is None and not group_budgets:
            self._resolve_legacy_spawns(scene_data, encounter_set, theme)
            return

        profile = settings.get("encounter_budget_profile")
        multiplier = 1.0
        if profile and hasattr(self.window, "engine_config") and self.window.engine_config.encounter_budget_profiles:
             multiplier = self.window.engine_config.encounter_budget_profiles.get(profile, 1.0)

        # Global Rules
        global_elite_cap = settings.get("elite_cap")
        if global_elite_cap is None and preset is not None and preset.get("elite_cap") is not None:
            global_elite_cap = preset.get("elite_cap")

        allow_elites_raw = settings.get("allow_elites")
        preset_allow_elites = preset.get("allow_elites") if preset is not None else None
        if allow_elites_raw is not None:
            global_allow_elites = bool(allow_elites_raw)
        elif preset_allow_elites is not None:
            global_allow_elites = bool(preset_allow_elites)
        else:
            global_allow_elites = True

        global_mini_boss_cap = settings.get("mini_boss_cap")
        if global_mini_boss_cap is None and preset is not None and preset.get("mini_boss_cap") is not None:
            global_mini_boss_cap = preset.get("mini_boss_cap")

        global_allow_mini_bosses = settings.get("allow_mini_bosses")
        if global_allow_mini_bosses is None and preset is not None and preset.get("allow_mini_bosses") is not None:
            global_allow_mini_bosses = preset.get("allow_mini_bosses")

        boss_reserve_raw = settings.get("boss_budget_reserve")
        if boss_reserve_raw is None and preset is not None and preset.get("boss_budget_reserve") is not None:
            boss_reserve_raw = preset.get("boss_budget_reserve")
        boss_reserve = float(boss_reserve_raw or 0.0)

        # Group Rules
        group_elite_caps = settings.get("encounter_group_elite_caps", {})
        group_allow_elites = settings.get("encounter_group_allow_elites", {})

        seed_val = settings.get("encounter_seed")
        if seed_val is None and self.current_scene_path:
             seed_val = int(hashlib.sha256(self.current_scene_path.encode('utf-8')).hexdigest(), 16)

        rng = random.Random(seed_val)

        entities = scene_data.get("entities", [])

        # Bucket placeholders by group
        placeholders_by_group: Dict[str, list[int]] = {}
        for idx, entity in enumerate(entities):
            if entity.get("prefab_id") == "theme_enemy_placeholder":
                group = entity.get("encounter_group", "default")
                if group not in placeholders_by_group:
                    placeholders_by_group[group] = []
                placeholders_by_group[group].append(idx)

        if not placeholders_by_group:
            return

        # Shuffle placeholders within each group for determinism
        # We sort keys to ensure deterministic iteration order of groups
        sorted_groups = sorted(placeholders_by_group.keys())
        for group in sorted_groups:
            rng.shuffle(placeholders_by_group[group])

        # Calculate effective budgets per group
        effective_budgets: Dict[str, float] = {}
        for group in sorted_groups:
            # Fallback to global budget if group budget missing
            g_budget = group_budgets.get(group)
            if g_budget is None:
                g_budget = base_budget if base_budget is not None else 0.0

            effective_budgets[group] = float(g_budget) * multiplier

        # Apply Boss Reserve
        if boss_reserve > 0:
            target_group = "boss_guard" if "boss_guard" in placeholders_by_group else "default"
            if target_group in effective_budgets:
                effective_budgets[target_group] -= boss_reserve

        # Resolve Candidates (Master List)
        # Scene-level override applies only to themed spawn resolution (theme_enemy_placeholder).
        # - New key: theme_spawn_variant_id
        # - Legacy key (deprecated): variant_id
        scene_spawn_variant_id = settings.get("theme_spawn_variant_id")
        if scene_spawn_variant_id is None:
            scene_spawn_variant_id = settings.get("variant_id")
        global_variant_id = scene_spawn_variant_id or encounter_set.variant_id or theme.default_variant_id
        pm = get_prefab_manager()

        master_candidates = []
        for entry in encounter_set.enemy_prefab_ids:
            candidate_variant_id = None
            if isinstance(entry, dict):
                pid_raw = entry.get("prefab_id")
                if not isinstance(pid_raw, str) or not pid_raw.strip():
                    continue
                pid = pid_raw.strip()
                v_raw = entry.get("variant_id")
                if isinstance(v_raw, str) and v_raw.strip():
                    candidate_variant_id = v_raw.strip()
            else:
                pid = entry
                if not isinstance(pid, str) or not pid.strip():
                    continue
                pid = pid.strip()

            variant_id = candidate_variant_id or global_variant_id
            if variant_id:
                data = pm.resolve_with_variant(pid, variant_id)
            else:
                data = pm.get_prefab(pid)

            if data:
                cost = float(get_effective_encounter_cost(data, default=1.0))
                is_boss = is_boss_payload(data)
                is_mini_boss = is_mini_boss_payload(data) and not is_boss
                is_elite = is_elite_payload(data) and not is_boss and not is_mini_boss
                master_candidates.append({
                    "pid": pid,
                    "variant_id": candidate_variant_id,
                    "cost": cost,
                    "is_boss": is_boss,
                    "is_mini_boss": is_mini_boss,
                    "is_elite": is_elite
                })

        if not master_candidates:
            return

        master_candidates.sort(key=lambda x: x["cost"])

        indices_to_remove = []

        # Process each group
        for group in sorted_groups:
            indices = placeholders_by_group[group]
            budget = effective_budgets[group]

            # Determine rules
            cap = group_elite_caps.get(group, global_elite_cap)
            allow = group_allow_elites.get(group, global_allow_elites)

            allow_mb = global_allow_mini_bosses if global_allow_mini_bosses is not None else allow
            mb_cap = global_mini_boss_cap if global_mini_boss_cap is not None else cap

            # Heuristic: Boss Guard safety
            if group == "boss_guard" and profile != "hard":
                # Check if explicitly overridden in group_allow_elites
                if group not in group_allow_elites:
                    allow = False
                    if global_allow_mini_bosses is None:
                        allow_mb = False

            # Filter candidates for this group
            group_candidates = [
                c
                for c in master_candidates
                if not ((c["is_elite"] and not allow) or (c["is_mini_boss"] and not allow_mb))
            ]

            if not group_candidates:
                # No valid candidates for this group (e.g. all elites and allow=False)
                indices_to_remove.extend(indices)
                continue

            spawned_count = 0
            elite_count = 0
            mini_boss_count = 0

            for idx in indices:
                affordable = []
                for c in group_candidates:
                    if c["cost"] > budget:
                        continue
                    if c["is_elite"] and cap is not None and elite_count >= cap:
                        continue
                    if c["is_mini_boss"] and mb_cap is not None:
                        if global_mini_boss_cap is None:
                            if elite_count >= mb_cap:
                                continue
                        else:
                            if mini_boss_count >= mb_cap:
                                continue
                    affordable.append(c)

                if not affordable:
                    if spawned_count == 0:
                        # Force at least one spawn if possible
                        # Prefer non-elites if capped
                        valid_fallback = []
                        for c in group_candidates:
                            if c["is_elite"] and cap is not None and elite_count >= cap:
                                continue
                            if c["is_mini_boss"] and mb_cap is not None:
                                if global_mini_boss_cap is None:
                                    if elite_count >= mb_cap:
                                        continue
                                else:
                                    if mini_boss_count >= mb_cap:
                                        continue
                            valid_fallback.append(c)
                        if valid_fallback:
                            chosen = valid_fallback[0]
                        else:
                            # If we must pick an elite even if capped (because it's the only option), so be it?
                            # Or just pick the cheapest candidate?
                            # Original logic: chosen = candidates[0] (cheapest)
                            chosen = group_candidates[0]
                    else:
                        indices_to_remove.append(idx)
                        continue
                else:
                    chosen = rng.choice(affordable)

                pid = chosen["pid"]
                cost = chosen["cost"]
                is_elite = chosen["is_elite"]
                is_mini_boss = chosen["is_mini_boss"]
                chosen_variant_id = chosen.get("variant_id")

                entity = entities[idx]
                entity["prefab_id"] = pid
                if encounter_set.drop_table_id and "drop_table_id" not in entity:
                    entity["drop_table_id"] = encounter_set.drop_table_id
                if "variant_id" not in entity:
                    if isinstance(chosen_variant_id, str) and chosen_variant_id.strip():
                        entity["variant_id"] = chosen_variant_id.strip()
                    elif global_variant_id:
                        entity["variant_id"] = global_variant_id

                budget -= cost
                spawned_count += 1
                if is_elite:
                    elite_count += 1
                elif is_mini_boss:
                    if global_mini_boss_cap is None:
                        elite_count += 1
                    else:
                        mini_boss_count += 1

        for idx in sorted(indices_to_remove, reverse=True):
            del entities[idx]

_bind_loading_methods(SceneController)
_bind_transitions_methods(SceneController)
_bind_runtime_hooks_methods(SceneController)
_bind_persistence_methods(SceneController)
_bind_quests_flags_methods(SceneController)
