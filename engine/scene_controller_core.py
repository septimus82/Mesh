"""Runtime scene controller facade.

This module preserves the public SceneController surface while implementation
details are split across scene_controller_parts binder modules.
"""

from __future__ import annotations

import hashlib
import logging
import random
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Iterator

import engine.optional_arcade as optional_arcade

from . import scene_controller_save_load as _save_load_proxy
from .animation_state import request_animation_state, tick_animation_state
from .background_layers import BackgroundLayer, draw_background_layers
from .behaviours import create_behaviour
from .behaviours.utils import (
    build_behaviour_config_map,
    ensure_behaviour_config_root,
    format_behaviour_config_summary,
    normalize_behaviour_entry,
    prepare_behaviour_configs,
    prune_optional_behaviour_defaults,
    strip_behaviour_metadata,
)
from .constants import EVENT_COLLECTIBLE_PICKED, EVENT_DAMAGE_APPLIED
from .culling import Rect
from .depth_tint_model import DEFAULT_DEPTH_TINT_SETTINGS, DepthTintSettings
from .encounter_cost import (
    get_effective_encounter_cost,
    is_boss_payload,
    is_elite_payload,
    is_mini_boss_payload,
)
from .encounter_sets import get_theme_manager
from .editor.sprite_outline_model import DEFAULT_OUTLINE_SETTINGS, OutlineSettings
from .elite_labeling import format_elite_label
from .parallax_model import BackgroundPlane
from .pathfinding import NavGrid
from .paths import resolve_path
from .prefabs import get_prefab_manager
from .scene_controller_parts.animation_event_sink import (
    bind_animation_event_sink_methods as _bind_animation_event_sink_methods,
)
from .scene_controller_parts.animation_runtime import (
    bind_animation_runtime_methods as _bind_animation_runtime_methods,
)
from .scene_controller_parts.authoring import (
    bind_authoring_methods as _bind_authoring_methods,
)
from .scene_controller_parts.encounter_resolution import (
    bind_encounter_resolution_methods as _bind_encounter_resolution_methods,
)
from .scene_controller_parts.entity_factory import (
    bind_entity_factory_methods as _bind_entity_factory_methods,
)
from .scene_controller_parts.gameplay_runtime import (
    bind_gameplay_runtime_methods as _bind_gameplay_runtime_methods,
)
from .scene_controller_parts.loading import (
    bind_loading_methods as _bind_loading_methods,
)
from .scene_controller_parts.persistence import (
    bind_persistence_methods as _bind_persistence_methods,
)
from .scene_controller_parts.quests_flags import (
    bind_quests_flags_methods as _bind_quests_flags_methods,
)
from .scene_controller_parts.rendering import (
    bind_rendering_methods as _bind_rendering_methods,
)
from .scene_controller_parts.runtime_hooks import (
    bind_runtime_hooks_methods as _bind_runtime_hooks_methods,
)
from .scene_controller_parts.scene_facade import (
    bind_scene_facade_methods as _bind_scene_facade_methods,
)
from .scene_controller_parts.tilemap_state import (
    bind_tilemap_state_methods as _bind_tilemap_state_methods,
)
from .scene_controller_parts.transitions import (
    _perform_scene_change_runtime,
    _reload_scene_runtime,
    bind_transitions_methods as _bind_transitions_methods,
)
from .scene_controller_parts.ui_runtime import (
    bind_ui_runtime_methods as _bind_ui_runtime_methods,
)
from .scene_controller_selection import (
    bind_selection_methods as _bind_selection_methods,
)
from .scene_entity_store_controller import SceneEntityStoreController
from .scene_index import SceneIndex
from .scene_navigation_controller import SceneNavigationController
from .scene_render_pipeline import (
    build_render_context,
    compute_draw_plan,
    execute_background_plan,
    execute_scene_plan,
)
from .scene_runtime import authoring as _authoring_runtime
from .scene_runtime import scene_load_apply as _scene_load_apply_runtime
from .scene_runtime.index_build import build_scene_index_from_sprites
from .scene_runtime.persistence import (
    apply_scene_state as _apply_scene_state_runtime,
)
from .scene_runtime.persistence import (
    build_scene_snapshot as _build_scene_snapshot_runtime,
)
from .scene_runtime.spawn import apply_pending_spawn_point as _apply_pending_spawn_point_runtime
from .scene_runtime.spawn import find_spawn_marker as _find_spawn_marker_runtime
from .scene_runtime.spawn import get_spawn as _get_spawn_runtime
from .scene_update_controller import SceneUpdateController
from .sensors_runtime import SensorRuntime
from .swallowed_exceptions import record_swallowed
from .tilemap import TilemapDrawLayer, TilemapInstance, compute_parallax_camera_position
from .tilemap_batch import TilemapBatchState, TilemapBatchStats
from .tilemap_batch_arcade import TilemapBatcher
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
)

logger = logging.getLogger(__name__)
_LOG_ONCE: set[str] = set()

_EXTRACTION_SEAMS = (
    _perform_scene_change_runtime,
    _apply_pending_spawn_point_runtime,
    _apply_scene_state_runtime,
    _build_scene_snapshot_runtime,
    _find_spawn_marker_runtime,
    _get_spawn_runtime,
    _reload_scene_runtime,
    EVENT_COLLECTIBLE_PICKED,
    EVENT_DAMAGE_APPLIED,
    AnimationStateOverlay,
    BackgroundPlane,
    BackgroundLayer,
    CharacterPanel,
    DEFAULT_DEPTH_TINT_SETTINGS,
    DEFAULT_OUTLINE_SETTINGS,
    DepthTintSettings,
    DevConsole,
    DialogueBox,
    EntityInspector,
    HealthBar,
    InventoryOverlay,
    OutlineSettings,
    QuestLog,
    Rect,
    ShopPanel,
    TilemapBatchStats,
    build_behaviour_config_map,
    build_render_context,
    compute_draw_plan,
    compute_parallax_camera_position,
    create_behaviour,
    draw_background_layers,
    ensure_behaviour_config_root,
    execute_background_plan,
    execute_scene_plan,
    format_elite_label,
    get_effective_encounter_cost,
    get_prefab_manager,
    get_theme_manager,
    hashlib,
    is_boss_payload,
    is_elite_payload,
    is_mini_boss_payload,
    maybe_enqueue_boss_spawn_toast,
    maybe_enqueue_miniboss_spawn_toast,
    normalize_behaviour_entry,
    prepare_behaviour_configs,
    prune_optional_behaviour_defaults,
    random,
    record_swallowed,
    request_animation_state,
    resolve_path,
    strip_behaviour_metadata,
    tick_animation_state,
)

if TYPE_CHECKING:
    from .game import GameWindow


class SceneController:
    """Coordinates scene state and exposes the bound controller API."""

    if TYPE_CHECKING:
        @property
        def current_scene_data(self) -> Dict[str, Any] | None: ...

        def _clear_tilemap_layers(self) -> None: ...
        def _create_sprite(self, entity: Dict[str, Any]) -> optional_arcade.arcade.Sprite | None: ...
        def _debug_preview_diff(self, *args: Any, **kwargs: Any) -> Any: ...
        def _deliver_events_to_behaviours(self, *args: Any, **kwargs: Any) -> None: ...
        def _ensure_entity_data_dict(self, sprite: optional_arcade.arcade.Sprite) -> dict[str, Any]: ...
        def _find_player_sprite(self) -> optional_arcade.arcade.Sprite | None: ...
        def _iter_layered_sprites(self) -> Iterator[optional_arcade.arcade.Sprite]: ...
        def add_sprite_to_layer(self, sprite: optional_arcade.arcade.Sprite, layer_name: str = "entities") -> None: ...
        def apply_spawn(self, spawn_id: str | None) -> None: ...
        def build_scene_snapshot(self, compact: bool = False) -> Dict[str, Any]: ...
        def debug_build_macro_dialogue_choice_flag_payload(self, *args: Any, **kwargs: Any) -> Any: ...
        def debug_build_macro_door_transition_payload(self, *args: Any, **kwargs: Any) -> Any: ...
        def debug_build_macro_objective_zone_payload(self, *args: Any, **kwargs: Any) -> Any: ...
        def debug_preview_macro_dialogue_choice_flag(self, *args: Any, **kwargs: Any) -> Any: ...
        def debug_preview_macro_door_transition(self, *args: Any, **kwargs: Any) -> Any: ...
        def debug_preview_macro_objective_zone(self, *args: Any, **kwargs: Any) -> Any: ...
        def draw(self) -> None: ...
        def find_entity(self, identifier: str | int) -> optional_arcade.arcade.Sprite | None: ...
        def find_sprite_by_name(self, name: str | None) -> optional_arcade.arcade.Sprite | None: ...
        def get_all_entities(self) -> list[optional_arcade.arcade.Sprite]: ...
        def get_authoring_trace_snapshot(self, *args: Any, **kwargs: Any) -> Any: ...
        def get_sprites_in_layer(self, layer_name: str) -> optional_arcade.arcade.SpriteList | None: ...
        def load_scene(self, scene_path: str) -> Dict[str, Any]: ...
        def move_entity_with_collision(
            self,
            sprite: optional_arcade.arcade.Sprite,
            dx: float,
            dy: float,
            friction: float = 1.0,
        ) -> None: ...
        def on_collectible_picked(
            self,
            collectible: optional_arcade.arcade.Sprite,
            collector: optional_arcade.arcade.Sprite,
        ) -> None: ...
        def on_damage(
            self,
            source: optional_arcade.arcade.Sprite,
            target: optional_arcade.arcade.Sprite,
            amount: float,
        ) -> None: ...
        def set_tile(self, *args: Any, **kwargs: Any) -> Any: ...
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

_bind_loading_methods(SceneController)
_bind_transitions_methods(SceneController)
_bind_runtime_hooks_methods(SceneController)
_bind_animation_event_sink_methods(SceneController)
_bind_animation_runtime_methods(SceneController)
_bind_encounter_resolution_methods(SceneController)
_bind_tilemap_state_methods(SceneController)
_bind_persistence_methods(SceneController)
_bind_quests_flags_methods(SceneController)
_bind_selection_methods(SceneController)
_bind_scene_facade_methods(SceneController)
_bind_ui_runtime_methods(SceneController)
_bind_entity_factory_methods(SceneController)
_bind_gameplay_runtime_methods(SceneController)
_bind_rendering_methods(SceneController)
_bind_authoring_methods(SceneController, authoring_runtime=_authoring_runtime)
