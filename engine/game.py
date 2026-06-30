"""Arcade window and runtime glue for the Mesh engine prototype.

This module contains the main GameWindow class which serves as the central
facade for the entire Mesh Engine. It orchestrates all subsystems and provides
the main game loop.

Architecture:
    GameWindow follows the Facade pattern, delegating responsibilities to
    specialized controllers while providing a unified interface:

    - **SceneController**: Entity management, layer rendering, scene loading
    - **CameraController**: Viewport, zoom, shake, camera areas
    - **InputController**: Keyboard/mouse/gamepad input handling
    - **UIController**: UI overlays, HUD, menus, dialogue
    - **EditorController**: In-game editor mode (dev only)
    - **ConsoleController**: Developer console commands
    - **LightManager**: Dynamic lighting and shadows
    - **AudioManager**: Music and sound effects

Game Loop:
    Each frame, GameWindow.on_update() and on_draw() are called:

    1. **on_update(dt)**:
        - Process input
        - Update behaviours (pre_update -> update -> late_update)
        - Update physics/collisions
        - Process pending scene changes
        - Tick animations, particles, day/night cycle
        - Deliver queued events

    2. **on_draw()**:
        - Clear screen
        - Draw background layers/parallax
        - Draw tilemap
        - Draw entities (sorted by depth)
        - Apply lighting
        - Draw UI overlays

Configuration:
    Engine settings are loaded from config.json::

        {
            "title": "My Game",
            "width": 1280,
            "height": 720,
            "fullscreen": false,
            "start_scene": "scenes/main.json",
            "lighting_enabled": true
        }

Example Usage::

    from engine.config import load_config
    from engine.game import GameWindow

    config = load_config("config.json")
    window = GameWindow(
        width=config.width,
        height=config.height,
        title=config.title,
        config=config
    )
    window.run()

See Also:
    - :class:`SceneController` for entity and scene management
    - :class:`CameraController` for viewport control
    - :mod:`engine.behaviours` for entity logic components
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable, Iterator, Sequence

import engine.optional_arcade

from .ai_debug_overlay import AIDebugOverlay
from .animation import AnimationFactory
from .assets import AssetManager
from .audio import AudioManager
from .behaviours import load_builtin_behaviours
from .camera_controller import CameraArea, CameraController
from .config import EngineConfig
from .console_controller import ConsoleController
from .constants import (
    DEBUG_STRICT_EXCEPTIONS,
    EVENT_COLLECTIBLE_PICKED,
    EVENT_DAMAGE_APPLIED,
    EVENT_LEVEL_UP,
)
from .cutscene_controller import CutsceneController
from .day_night import DayNightCycle
from .editor_controller import EditorModeController
from .events import MeshEvent, MeshEventBus
from .fx_presets import build_fx_preset_registry
from .game_parts.audio_coordinator import init_audio_coordinator as _init_audio_coordinator
from .game_parts.input_router import bind_input_router_methods as _bind_input_router_methods
from .game_parts.state_facade import bind_state_facade_methods as _bind_state_facade_methods
from .game_parts.ui_dispatcher import bind_ui_dispatcher_methods as _bind_ui_dispatcher_methods
from .game_parts.ui_dispatcher import init_ui_dispatcher as _init_ui_dispatcher
from .game_parts.update_loop import bind_update_loop_methods as _bind_update_loop_methods
from .game_runtime.undo import UndoFrame
from .game_state_controller import GameState, GameStateController
from .input import InputManager
from .input_controller import InputController
from .lighting import LightManager
from .logging_tools import get_logger
from .migrations import migrate_payload
from .monster.battle_mode import MonsterBattleMode
from .particles import ParticleManager
from .paths import pin_config, resolve_path
from .perf import PerfStats
from .quests import QuestManager
from .render_queue import SpriteRenderQueue
from .render_queue_arcade import ArcadeSpriteBatcher
from .save_manager import SaveManager
from .scene_controller import SceneController
from .scene_loader import SceneLoader
from .services import (
    InputService,
    PersistenceService,
    ReplayService,
    build_input_service,
    build_persistence_service,
    build_replay_service,
)
from .swallowed_exceptions import _log_swallow
from .tilemap import TilemapManager
from .ui import (
    DevBrowserOverlay,
    GameOverScreen,
    GoldenSliceDemoHUDStripOverlay,
    GoldenSliceVariantPickerOverlay,
    HelpOverlay,
    InspectorOverlay,
    PauseMenu,
    PlayerHUD,
    SettingsOverlay,
)
from .ui_controller import UIController
from .world_controller import WorldController

_BEHAVIOUR_META_EXPLICIT = "__explicit_behaviour_keys__"
_OPTIONAL_BEHAVIOUR_DEFAULTS: tuple[tuple[str, str], ...] = ()
_MISSING = object()
logger = get_logger(__name__)

class GameWindow(engine.optional_arcade.arcade.Window):
    """Main game window and central facade for the Mesh Engine.

    GameWindow inherits from Arcade's Window class and orchestrates all engine
    subsystems. It serves as the service container that controllers and systems
    reference to access other parts of the engine.

    Key Responsibilities:
        - Initialize and wire up all engine subsystems
        - Run the main game loop (update/draw cycle)
        - Dispatch input events to the appropriate handlers
        - Manage scene loading and transitions
        - Coordinate UI overlay rendering

    Subsystems (accessible as attributes):
        scene_controller: Entity and scene management
        camera_controller: Viewport, zoom, shake
        input_controller: Input handling and action dispatch
        ui_controller: UI overlays and HUD
        editor_controller: In-game editor (dev mode)
        console_controller: Developer console
        lighting: Dynamic lighting system
        audio: Music and sound effects
        events: Event bus for gameplay events
        game_state: Global game state (flags, counters)
        quest_manager: Quest progress tracking
        save_manager: Save/load functionality

    UI Overlays:
        player_hud: Health/stamina/inventory HUD
        pause_menu: In-game pause menu
        help_overlay: Controls help screen
        settings_overlay: Settings/options menu

    Example::

        # Access subsystems from a behaviour
        def update(self, dt):
            # Get player entity
            player = self.window.scene_controller.player

            # Emit a gameplay event
            self.window.events.emit("item_collected", item_id="key_1")

            # Check game state
            if self.window.game_state.get_flag("boss_defeated"):
                self.window.scene_controller.request_scene_change("credits.json")

            # Play sound effect
            self.window.audio.play_sound("coin_pickup")
    """

    player_hud: PlayerHUD
    game_over_screen: GameOverScreen
    pause_menu: PauseMenu
    help_overlay: HelpOverlay
    inspector_overlay: InspectorOverlay
    variant_picker_overlay: GoldenSliceVariantPickerOverlay
    golden_slice_demo_hud: GoldenSliceDemoHUDStripOverlay
    dev_browser_overlay: DevBrowserOverlay
    settings_overlay: SettingsOverlay
    input_service: InputService
    persistence_service: PersistenceService
    replay_service: ReplayService

    if TYPE_CHECKING:
        @property
        def all_sprites(self) -> Iterator[engine.optional_arcade.arcade.Sprite]: ...
        def add_camera_trauma(
            self,
            amount: float,
            *,
            decay: float | None = None,
            max_offset: float | None = None,
            frequency: float | None = None,
            seed: int | None = None,
        ) -> None: ...
        def _draw_debug_output(self, lines: list[str]) -> None: ...
        def _draw_debug_overlay(self) -> None: ...
        def _debug_print_events(self, events: list[MeshEvent]) -> None: ...
        def _draw_shadowcast_debug(self) -> None: ...
        def _consume_next_spawn_point(self) -> str | None: ...
        def _on_any_event(self, event: MeshEvent) -> None: ...
        def _on_any_event_boss_reward_clarity(self, event: MeshEvent) -> None: ...
        def _on_collectible_event(self, event: MeshEvent) -> None: ...
        def _on_damage_event(self, event: MeshEvent) -> None: ...
        def _on_entity_died(self, event: MeshEvent) -> None: ...
        def _on_level_up(self, event: MeshEvent) -> None: ...
        def _resolve_collisions_stage(self, delta_time: float) -> None: ...
        def _snapshot_current_authored_scene_payload(self) -> UndoFrame | None: ...
        def _toggle_paused_state(self) -> bool: ...
        def _undo_enabled(self) -> bool: ...
        def advance_dialogue(self, *, owner: str | None = None) -> bool: ...
        def build_scene_snapshot(self, compact: bool = False) -> dict[str, Any]: ...
        @property
        def camera(self) -> Any: ...
        def clear_ui_elements(self) -> None: ...
        def clear_hot_reload_error(self) -> None: ...
        def clear_scene_dirty(self) -> None: ...
        def clamp_camera_to_rect(
            self,
            target_x: float,
            target_y: float,
            rect: tuple[float, float, float, float],
            *,
            padding: float = 0.0,
        ) -> tuple[float, float]: ...
        def clamp_camera_to_world(
            self,
            target_x: float,
            target_y: float,
            *,
            padding: float = 0.0,
        ) -> tuple[float, float]: ...
        def close_dialogue(self, *, owner: str | None = None) -> None: ...
        def consume_events(self) -> list[MeshEvent]: ...
        def draw_debug_overlay(self) -> None: ...
        def dialogue_blocks_input(self) -> bool: ...
        def clear_input_locks(self) -> None: ...
        def emit_event(self, event: MeshEvent) -> None: ...
        def emit_signal(self, event_type: str, **payload: Any) -> None: ...
        def find_entity(self, identifier: str | int) -> engine.optional_arcade.arcade.Sprite | None: ...
        def find_sprite_by_name(self, name: str | None) -> engine.optional_arcade.arcade.Sprite | None: ...
        @property
        def game_state(self) -> GameState: ...
        def get_all_entities(self) -> list[engine.optional_arcade.arcade.Sprite]: ...
        def get_camera_area_for_point(self, x: float, y: float) -> CameraArea | None: ...
        def get_camera_center(self) -> tuple[float, float]: ...
        def get_chapter(self) -> int: ...
        def get_counter(self, name: str, default: float = 0.0) -> float: ...
        def get_flag(self, name: str, default: bool = False) -> bool: ...
        def get_main_quest(self) -> str | None: ...
        def get_next_spawn_point(self) -> str | None: ...
        def get_pressed_keys(self) -> set[int]: ...
        def get_playtime_seconds(self) -> float: ...
        def get_recent_scenes(self) -> list[str]: ...
        def get_sprites_in_layer(self, layer_name: str) -> engine.optional_arcade.arcade.SpriteList | None: ...
        def get_var(self, name: str, default: Any = None) -> Any: ...
        def hide_character_panel(self) -> None: ...
        def hide_inventory_overlay(self) -> None: ...
        def hide_quest_log(self) -> None: ...
        def inc_counter(self, name: str, amount: float = 1.0) -> float: ...
        def is_character_panel_visible(self) -> bool: ...
        def is_dialogue_active(self, *, owner: str | None = None) -> bool: ...
        def is_input_locked(self) -> bool: ...
        def is_inventory_overlay_visible(self) -> bool: ...
        def is_quest_log_visible(self) -> bool: ...
        def lock_player_input(self, *, owner: str | None = None) -> None: ...
        def load_scene(self, scene_path: str) -> dict[str, Any]: ...
        def mark_scene_dirty(self, reason: str) -> None: ...
        def move_entity_with_collision(
            self,
            sprite: engine.optional_arcade.arcade.Sprite,
            dx: float,
            dy: float,
            friction: float = 1.0,
        ) -> None: ...
        def on_collectible_picked(
            self,
            collectible: engine.optional_arcade.arcade.Sprite,
            collector: engine.optional_arcade.arcade.Sprite,
        ) -> None: ...
        def on_damage(
            self,
            source: engine.optional_arcade.arcade.Sprite,
            target: engine.optional_arcade.arcade.Sprite,
            amount: float,
        ) -> None: ...
        def on_key_press(self, key: int, modifiers: int) -> None: ...
        def on_key_release(self, key: int, modifiers: int) -> None: ...
        def on_mouse_drag(
            self,
            x: float,
            y: float,
            dx: float,
            dy: float,
            buttons: int,
            modifiers: int,
        ) -> None: ...
        def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None: ...
        def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None: ...
        def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> None: ...
        def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> None: ...
        def on_text(self, text: str) -> None: ...
        def on_text_motion(self, motion: int) -> None: ...
        def on_draw(self) -> None: ...
        def on_update(self, delta_time: float) -> None: ...
        def persist_scene_to_disk(self) -> Any: ...
        def player_input_blocked(self) -> bool: ...
        def push_undo_frame(self, reason: str) -> bool: ...
        def queue_scene_change(self, scene_path: str, *, spawn_id: str | None = None) -> None: ...
        def quest_log_blocks_input(self) -> bool: ...
        def register_ui_element(self, element: object) -> None: ...
        def record_recent_scene(self, scene_path: str) -> None: ...
        def redo(self) -> bool: ...
        def reload_current_scene(self) -> None: ...
        def reload_scene(self, new_path: str | None = None) -> bool: ...
        def reload_scene_from_disk(self) -> bool: ...
        def request_reload_current_scene(self, clear_assets: bool = False) -> None: ...
        def request_scene_change(self, scene_path: str) -> None: ...
        def request_scene_reload(self, clear_assets: bool = False) -> None: ...
        def save_scene_as(self, new_scene_path: str) -> Any: ...
        def screen_to_world(self, x: float, y: float) -> tuple[float, float]: ...
        def set_camera_zoom_target(self, zoom: float, *, speed: float | None = None) -> None: ...
        def set_chapter(self, chapter: int) -> None: ...
        def set_counter(self, name: str, value: float = 0.0) -> float: ...
        def set_flag(self, name: str, value: bool = True) -> None: ...
        def set_hot_reload_error(self, message: str, scene_path: str | None = None) -> None: ...
        def set_main_quest(self, quest_id: str | None) -> None: ...
        def set_next_spawn_point(self, spawn_id: str | None) -> None: ...
        def set_var(self, name: str, value: Any) -> None: ...
        def show_dialogue(self, entries: Sequence[dict[str, str]], *, owner: str) -> bool: ...
        def should_collide(
            self,
            sprite_a: engine.optional_arcade.arcade.Sprite,
            sprite_b: engine.optional_arcade.arcade.Sprite,
        ) -> bool: ...
        def start_camera_shake(
            self,
            *,
            duration: float,
            amplitude: float,
            frequency: float = 18.0,
            falloff: float = 1.0,
        ) -> None: ...
        def stop_camera_shake(self) -> None: ...
        def toggle_flag(self, name: str) -> bool: ...
        def toggle_character_panel(self) -> bool: ...
        def toggle_inventory_overlay(self) -> bool: ...
        def toggle_quest_log(self) -> bool: ...
        def track_scene_subscription(self, unsubscribe: Callable[[], None]) -> None: ...
        def undo(self) -> bool: ...
        def unlock_player_input(self, *, owner: str | None = None) -> None: ...
        def update_camera_follow(
            self,
            *,
            target_x: float,
            target_y: float,
            dt: float,
            lerp_factor: float | None = None,
            follow_strength: float | None = None,
            deadzone_px: float | None = None,
            deadzone_w: float | None = None,
            deadzone_h: float | None = None,
            max_speed: float | None = None,
            padding: float = 0.0,
            zoom: float | None = None,
            zoom_speed: float | None = None,
            min_zoom: float | None = None,
            max_zoom: float | None = None,
        ) -> None: ...
        def warp_to_scene(self, scene_path: str) -> None: ...

    def __init__(
        self,
        width: int,
        height: int,
        title: str,
        *,
        fullscreen: bool = False,
        vsync: bool = True,
        resizable: bool | None = None,
        config: EngineConfig | None = None,
        config_path: str = "config.json",
    ) -> None:
        """Initialize the game window and all engine subsystems.

        Args:
            width: Window width in pixels.
            height: Window height in pixels.
            title: Window title text.
            fullscreen: Start in fullscreen mode.
            vsync: Enable vertical sync.
            resizable: Allow the OS window to be resized. None uses config/default.
            config: Pre-loaded EngineConfig, or None to use defaults.
            config_path: Path to config.json for runtime reference.
        """
        resolved_resizable = (
            resizable
            if resizable is not None
            else (getattr(config, "resizable", True) if config is not None else True)
        )
        super().__init__(
            width=width,
            height=height,
            title=title,
            fullscreen=fullscreen,
            vsync=vsync,
            resizable=resolved_resizable,
        )
        set_min = getattr(self, "set_minimum_size", None)
        if callable(set_min):
            try:
                set_min(480, 270)
            except Exception as exc:  # noqa: BLE001  # REASON: resize safety floor is best-effort for platform/fallback compatibility
                _log_swallow("GAME-000", "engine/game.py set_minimum_size", once=True)
                logger.warning("[Mesh][GameWindow] WARNING: Failed to set minimum size: %r", exc)
        try:
            engine.optional_arcade.arcade.set_background_color(engine.optional_arcade.arcade.color.DARK_BLUE_GRAY)
        except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("GAME-001", "engine/game.py blanket swallow", once=True)
            logger.warning("[Mesh][GameWindow] WARNING: Failed to set background color: %r", exc)

        load_builtin_behaviours()

        self.config_path = config_path
        if config is None:
            config = EngineConfig(
                width=width,
                height=height,
                title=title,
                fullscreen=fullscreen,
                vsync=vsync,
                resizable=resolved_resizable,
            )
        self.engine_config = config
        self.engine_config.width = width
        self.engine_config.height = height
        self.engine_config.title = title
        self.engine_config.fullscreen = fullscreen
        self.engine_config.vsync = vsync
        self.engine_config.resizable = resolved_resizable
        pin_config(self.engine_config)

        # Text cache for overlays to avoid PerformanceWarning
        from engine.text_draw import TextCache
        self.text_cache = TextCache()

        self.world_controller = None
        world_file = getattr(self.engine_config, "world_file", None)
        if world_file:
            path = resolve_path(world_file)
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    raw = migrate_payload("world", raw)
                    self.world_controller = WorldController(raw)
                    logger.info(
                        "[Mesh][World] Loaded world '%s' from %s",
                        self.world_controller.id,
                        world_file,
                    )
                except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                    _log_swallow("GAME-002", "engine/game.py blanket swallow", once=True)
                    logger.error("[Mesh][World] Failed to load '%s': %s", world_file, exc)

        self.scene_loader = SceneLoader()
        self.fx_presets = build_fx_preset_registry()
        self.assets = AssetManager()
        self.animation_factory = AnimationFactory(self.assets)
        self.tilemap_manager = TilemapManager(self.assets)
        _init_audio_coordinator(self, audio_manager_cls=AudioManager)
        self.console_controller = ConsoleController(self)
        self.camera_controller = CameraController(self)
        self.scene_controller = SceneController(self)
        self.input_controller = InputController(self)
        self.ui_controller = UIController(self)
        self.event_bus = MeshEventBus()
        self._mesh_event_queue: list[MeshEvent] = []
        self._scene_event_unsubscribes: list[Callable[[], None]] = []
        self.game_state_controller = GameStateController(self)
        self.save_manager = SaveManager(self)
        self.quest_manager = QuestManager(self)
        # Single shared instance: the controller's lightweight-typed `quests`
        # slot now holds the canonical full manager (lightweight retired in a
        # later slice).
        setattr(self.game_state_controller, "quests", self.quest_manager)
        self.particle_manager = ParticleManager(self)
        self.editor_controller = EditorModeController(self)
        self.ai_debug_overlay = AIDebugOverlay()
        self.ai_debug_overlay_enabled = False

        # Debug-only scene authoring state (dirty tracking + guarded persist)
        self.scene_dirty: bool = False
        self.scene_dirty_reason: str = ""
        self.scene_dirty_counter: int = 0
        self.last_persist_path: str | None = None
        self.hot_reload_error_message: str = ""
        self.hot_reload_error_scene_path: str = ""
        self.hot_reload_error_visible: bool = False
        self.scene_persist_armed: bool = False
        self.entity_snap_to_tile: bool = False
        self.last_duplicate_count: int = 0
        self.last_duplicate_primary: str = ""
        self.last_duplicate_counter: int = 0
        self.entity_clipboard: dict[str, Any] | None = None
        self.last_transform_action: str = ""
        self.last_transform_count: int = 0
        self.last_transform_counter: int = 0
        self.last_props_action: str = ""
        self.last_props_changed: int = 0
        self.last_props_counter: int = 0
        self.last_config_action: str = ""
        self.last_config_changed: int = 0
        self.last_config_counter: int = 0
        self.tile_quick_slots: dict[int, int] = {}
        self.tile_recent: list[int] = []
        self.prefab_quick_slots: dict[int, str] = {}
        self.prefab_recent: list[str] = []
        self.recent_scenes: list[str] = []
        self.command_palette_enabled: bool = False
        self.command_palette_query: str = ""
        self.command_palette_index: int = 0
        self.command_palette_prompt_active: bool = False
        self.command_palette_prompt_text: str = ""
        self.command_palette_prompt_placeholder: str = ""
        self.command_palette_prompt_title: str = ""
        self.command_palette_prompt_command_id: str = ""
        self.command_palette_prompt_kind: str = "text"
        self.command_palette_prompt_query: str = ""
        self.command_palette_prompt_index: int = 0
        self.command_palette_prompt_steps: tuple[Any, ...] = ()
        self.command_palette_prompt_step_index: int = 0
        self.command_palette_prompt_values: dict[str, Any] = {}
        self.last_macro_args: dict[str, dict[str, Any]] = {}
        self.asset_hot_reload_watcher: Any | None = None
        self.undo_stack: list[UndoFrame] = []
        self.redo_stack: list[UndoFrame] = []
        self._undo_ts_counter: int = 0
        self._undo_suppress_count: int = 0
        self.cutscene_controller = CutsceneController(self)
        try:
            self.cutscene_controller.load_from_file("cutscenes.json")
        except FileNotFoundError:
            pass
        ambient = list(getattr(self.engine_config, "lighting_ambient_color", [10, 10, 10, 255]))
        ambient_alpha = getattr(self.engine_config, "ambient_darkness_alpha", None)
        if ambient_alpha is not None and len(ambient) >= 4:
            try:
                ambient[3] = int(ambient_alpha)
            except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("GAME-004", "engine/game.py pass-only blanket swallow")
                pass
        self.lighting = LightManager(
            self,
            enabled=getattr(self.engine_config, "lighting_enabled", True),
            ambient_color=tuple(ambient),
            max_static_lights=getattr(self.engine_config, "lighting_max_static_lights", 128),
            max_dynamic_lights=getattr(self.engine_config, "lighting_max_dynamic_lights", 64),
            shadows_mode=getattr(self.engine_config, "lighting_shadows_mode", "hard"),
            debug_shadows=getattr(self.engine_config, "lighting_debug_shadows", False),
        )
        ambient_tint = getattr(self.engine_config, "ambient_light_rgba", None)
        if ambient_tint is not None:
            self.lighting.set_ambient_tint(ambient_tint)
        if ambient_alpha is not None:
            self.lighting.set_ambient_darkness_alpha(ambient_alpha)
        self.day_night = DayNightCycle(
            self.lighting,
            enabled=self.engine_config.day_night_enabled,
            start_hour=float(self.engine_config.day_night_start_hour),
            cycle_length_seconds=float(self.engine_config.day_night_cycle_length_seconds),
        )

        _init_ui_dispatcher(self)

        self.paused: bool = False
        self.game_over: bool = False
        self.monster_battle_mode = MonsterBattleMode(self)
        self.monster_battle_mode_active: bool = False
        self.world_width: int | None = None
        self.world_height: int | None = None
        self.show_debug: bool = bool(self.engine_config.debug_on_start)
        self._debug_text = engine.optional_arcade.arcade.Text(
            text="",
            x=10,
            y=self.height - 10,
            color=engine.optional_arcade.arcade.color.WHITE,
            font_size=12,
            anchor_y="top",
        )
        self.render_batching_enabled = True
        self.render_culling_enabled = True
        self.tilemap_batching_enabled = True
        self.tilemap_chunk_size = 16
        self.render_queue = SpriteRenderQueue(ArcadeSpriteBatcher(self))
        self.perf_stats = PerfStats()

        # Post-processing pipeline (empty by default — add effects at runtime)
        from .post_processing import PostProcessPipeline
        self.post_process_pipeline = PostProcessPipeline()
        self.strict_mode: bool = DEBUG_STRICT_EXCEPTIONS
        self.input_service = build_input_service()
        self.persistence_service = build_persistence_service()
        self.replay_service = build_replay_service()
        from engine.asset_hot_reload_watcher import maybe_start_hot_reload_watcher  # noqa: PLC0415

        self.asset_hot_reload_watcher = maybe_start_hot_reload_watcher(self)
        watcher = self.asset_hot_reload_watcher
        configure_polling = getattr(watcher, "configure_polling", None) if watcher is not None else None
        if callable(configure_polling):
            configure_polling(
                (
                    "assets/shaders",
                    "assets/sprites",
                    "assets/textures",
                    "assets/audio",
                    "assets/sounds",
                    "packs",
                ),
                poll_interval_s=0.5,
            )

        # Plugin / mod system
        from .plugin_system import PluginManager
        self.plugin_manager = PluginManager()
        try:
            from .repo_root import find_repo_root
            _repo = find_repo_root()
            _mods_dir = (_repo / "mods") if _repo else None
            if _mods_dir and _mods_dir.is_dir():
                self.plugin_manager.load_all(self, _mods_dir)
                self.plugin_manager.enable_all()
        except Exception as _exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("GAME-004", "engine/game.py blanket swallow", once=True)
            logger.warning("[Mesh][Plugins] Plugin loading failed: %s", _exc)

        logger.info("[Mesh][GameWindow] Initialized %sx%s window", width, height)

        self.event_bus.subscribe("died", self._on_entity_died)
        self.event_bus.subscribe(EVENT_DAMAGE_APPLIED, self._on_damage_event)
        self.event_bus.subscribe(EVENT_COLLECTIBLE_PICKED, self._on_collectible_event)
        self.event_bus.subscribe(EVENT_LEVEL_UP, self._on_level_up)

        self.last_events: list[str] = []
        self.event_bus.subscribe_all(self._on_any_event)
        self.event_bus.subscribe_all(self._on_any_event_boss_reward_clarity)

    @property
    def input(self) -> InputManager:
        return self.input_controller.manager

    @property
    def mouse_x(self) -> float:
        return self.input_controller.mouse_x

    @property
    def mouse_y(self) -> float:
        return self.input_controller.mouse_y


    def run(self) -> None:
        """Start Arcade's main loop."""
        logger.info("[Mesh][GameWindow] Starting Arcade loop...")
        engine.optional_arcade.arcade.run()

    def start_monster_battle(self, **kwargs: Any) -> Any:
        """Start the runtime monster battle mode."""

        return self.monster_battle_mode.start_battle(**kwargs)

    def end_monster_battle(self, result: Any | None = None) -> Any:
        """End the runtime monster battle mode."""

        return self.monster_battle_mode.end_battle(result)

    def open_monster_party_view(self) -> Any:
        """Open the runtime monster party view."""

        from engine.monster.party_menu import open_monster_party_view  # noqa: PLC0415

        return open_monster_party_view(self)

    def start_debug_monster_battle(self) -> Any:
        """Start a fixture monster battle for MON-0f dogfooding."""

        from engine.monster.battle_model import MonsterInstance  # noqa: PLC0415
        from engine.monster.collection import load_battle_party_from_values  # noqa: PLC0415
        from engine.monster.data_load import load_monster_catalog  # noqa: PLC0415
        from engine.paths import resolve_monster_data_dir  # noqa: PLC0415

        mode = getattr(self, "monster_battle_mode", None)
        if mode is not None and getattr(mode, "active", False):
            return getattr(mode, "controller", None)

        catalog, validation = load_monster_catalog(resolve_monster_data_dir())
        if not validation.ok or catalog is None:
            self.console_log(f"[MonsterBattle] Catalog load failed: {'; '.join(validation.errors)}")
            return None
        try:
            player_species = catalog.species["sproutling"]
            opponent_species = catalog.species["shelltide"]
        except KeyError as exc:
            self.console_log(f"[MonsterBattle] Missing debug species: {exc}")
            return None
        fallback = MonsterInstance(player_species, level=8, known_moves=player_species.learnset)
        values: dict[str, Any] = {}
        controller = getattr(self, "game_state_controller", None)
        state = getattr(controller, "state", None)
        state_values = getattr(state, "values", None)
        if isinstance(state_values, dict):
            values = state_values
        party, party_instance_ids = load_battle_party_from_values(values, catalog.species, fallback=fallback)
        active = party[0]
        self.console_log("[MonsterBattle] Starting debug battle: Sproutling vs Shelltide")
        return self.start_monster_battle(
            player_monster=active,
            player_party=party,
            player_party_instance_ids=party_instance_ids,
            opponent_monster=MonsterInstance(opponent_species, level=6, known_moves=opponent_species.learnset),
            moves=catalog.moves,
            type_chart=catalog.type_chart,
            return_context={"source": "debug_key", "scene_path": getattr(self.scene_controller, "current_scene_path", "")},
        )

    def start_debug_trainer_monster_battle(self) -> Any:
        """Start a fixture trainer battle with a multi-monster opponent team."""

        from engine.monster.battle_model import MonsterInstance  # noqa: PLC0415
        from engine.monster.collection import load_battle_party_from_values  # noqa: PLC0415
        from engine.monster.data_load import load_monster_catalog  # noqa: PLC0415
        from engine.paths import resolve_monster_data_dir  # noqa: PLC0415

        mode = getattr(self, "monster_battle_mode", None)
        if mode is not None and getattr(mode, "active", False):
            return getattr(mode, "controller", None)

        catalog, validation = load_monster_catalog(resolve_monster_data_dir())
        if not validation.ok or catalog is None:
            self.console_log(f"[MonsterBattle] Catalog load failed: {'; '.join(validation.errors)}")
            return None
        try:
            player_species = catalog.species["sproutling"]
            lead_species = catalog.species["shelltide"]
            bench_species = catalog.species["sproutling"]
        except KeyError as exc:
            self.console_log(f"[MonsterBattle] Missing debug species: {exc}")
            return None
        fallback = MonsterInstance(player_species, level=8, known_moves=player_species.learnset)
        values: dict[str, Any] = {}
        controller = getattr(self, "game_state_controller", None)
        state = getattr(controller, "state", None)
        state_values = getattr(state, "values", None)
        if isinstance(state_values, dict):
            values = state_values
        party, party_instance_ids = load_battle_party_from_values(values, catalog.species, fallback=fallback)
        opponent_party = [
            MonsterInstance(lead_species, level=7, current_hp=28, known_moves=lead_species.learnset),
            MonsterInstance(bench_species, level=5, current_hp=22, known_moves=bench_species.learnset),
        ]
        active = party[0]
        self.console_log("[MonsterBattle] Starting debug trainer battle: 2-monster opponent team")
        return self.start_monster_battle(
            player_monster=active,
            player_party=party,
            player_party_instance_ids=party_instance_ids,
            opponent_monster=opponent_party[0],
            opponent_party=opponent_party,
            moves=catalog.moves,
            type_chart=catalog.type_chart,
            return_context={"source": "trainer_debug_key", "scene_path": getattr(self.scene_controller, "current_scene_path", "")},
        )

    def start_debug_companion_monster_battle(self) -> Any:
        """Start a companion battle where the monster acts autonomously."""

        from engine.monster.battle_model import MonsterInstance  # noqa: PLC0415
        from engine.monster.collection import (  # noqa: PLC0415
            add_caught_monster,
            ensure_monster_collection,
            load_battle_party_from_values,
            load_companion_mind_for_instance,
        )
        from engine.monster.companion_mind import CompanionMind, LearnedWeights, Temperament  # noqa: PLC0415
        from engine.monster.data_load import load_monster_catalog  # noqa: PLC0415
        from engine.paths import resolve_monster_data_dir  # noqa: PLC0415

        mode = getattr(self, "monster_battle_mode", None)
        if mode is not None and getattr(mode, "active", False):
            return getattr(mode, "controller", None)

        catalog, validation = load_monster_catalog(resolve_monster_data_dir())
        if not validation.ok or catalog is None:
            self.console_log(f"[MonsterBattle] Catalog load failed: {'; '.join(validation.errors)}")
            return None
        try:
            player_species = catalog.species["sproutling"]
            opponent_species = catalog.species["shelltide"]
        except KeyError as exc:
            self.console_log(f"[MonsterBattle] Missing debug species: {exc}")
            return None
        fallback = MonsterInstance(player_species, level=8, known_moves=player_species.learnset)
        values: dict[str, Any] = {}
        controller = getattr(self, "game_state_controller", None)
        state = getattr(controller, "state", None)
        state_values = getattr(state, "values", None)
        if isinstance(state_values, dict):
            values = state_values
        ensure_monster_collection(values)
        party, party_instance_ids = load_battle_party_from_values(values, catalog.species, fallback=fallback)
        if not party_instance_ids or party_instance_ids[0] is None:
            debug_monster = MonsterInstance(player_species, level=8, known_moves=player_species.learnset)
            stored = add_caught_monster(values, debug_monster)
            party = [debug_monster]
            party_instance_ids = [stored.instance_id]
        active = party[0]
        instance_id = str(party_instance_ids[0])
        mind = load_companion_mind_for_instance(values, instance_id)
        if mind is None:
            mind = CompanionMind(
                temperament=Temperament(aggression=65.0, fear=12.0),
                learned=LearnedWeights(),
                trust=60.0,
                bond=40.0,
            )
        self.console_log("[MonsterBattle] Starting debug companion battle")
        return self.start_monster_battle(
            player_monster=active,
            player_party=party,
            player_party_instance_ids=party_instance_ids,
            opponent_monster=MonsterInstance(opponent_species, level=6, current_hp=40, known_moves=opponent_species.learnset),
            moves=catalog.moves,
            type_chart=catalog.type_chart,
            companion_mode=True,
            companion_mind=mind,
            return_context={
                "source": "companion_debug_key",
                "scene_path": getattr(self.scene_controller, "current_scene_path", ""),
                "player_instance_id": instance_id,
            },
        )

    def debug_breed_first_party_pair(self) -> bool:
        """Debug-only: breed the first two party monsters into a hatching egg."""

        import random  # noqa: PLC0415

        from engine.monster.breeding import BreedingParent, breed_offspring  # noqa: PLC0415
        from engine.monster.collection import (  # noqa: PLC0415
            MONSTER_PARTY_KEY,
            ensure_monster_collection,
            load_companion_mind_for_instance,
        )
        from engine.monster.companion_mind import CompanionMind, LearnedWeights, Temperament  # noqa: PLC0415
        from engine.monster.data_load import load_monster_catalog  # noqa: PLC0415
        from engine.monster.egg_lifecycle import (  # noqa: PLC0415
            DEFAULT_EGG_HATCH_STEPS,
            create_breeding_egg,
            load_monster_instance_from_values,
        )
        from engine.paths import resolve_monster_data_dir  # noqa: PLC0415

        if not bool(getattr(self.engine_config, "debug_mode", False)):
            return False

        catalog, validation = load_monster_catalog(resolve_monster_data_dir())
        if not validation.ok or catalog is None:
            self.console_log(f"[Breeding] Catalog load failed: {'; '.join(validation.errors)}")
            return False

        values: dict[str, Any] = {}
        controller = getattr(self, "game_state_controller", None)
        state = getattr(controller, "state", None)
        state_values = getattr(state, "values", None)
        if isinstance(state_values, dict):
            values = state_values
        ensure_monster_collection(values)

        party_ids = [str(instance_id) for instance_id in values.get(MONSTER_PARTY_KEY, []) if str(instance_id).strip()]
        if len(party_ids) < 2:
            self.console_log("[Breeding] Need at least two party monsters to breed.")
            return False

        parent_a_id, parent_b_id = party_ids[0], party_ids[1]
        parent_a_monster = load_monster_instance_from_values(values, parent_a_id, species_by_id=catalog.species)
        parent_b_monster = load_monster_instance_from_values(values, parent_b_id, species_by_id=catalog.species)
        if parent_a_monster is None or parent_b_monster is None:
            self.console_log("[Breeding] Could not load parent monsters from party.")
            return False

        default_mind = CompanionMind(
            temperament=Temperament(aggression=65.0, fear=12.0),
            learned=LearnedWeights(),
            trust=60.0,
            bond=40.0,
        )
        parent_a_mind = load_companion_mind_for_instance(values, parent_a_id) or default_mind
        parent_b_mind = load_companion_mind_for_instance(values, parent_b_id) or default_mind

        offspring, mind = breed_offspring(
            BreedingParent(parent_a_monster, parent_a_mind),
            BreedingParent(parent_b_monster, parent_b_mind),
            random.Random(),
        )
        egg_id = create_breeding_egg(
            values,
            offspring=offspring,
            mind=mind,
            parent_a_instance_id=parent_a_id,
            parent_b_instance_id=parent_b_id,
            hatch_steps=DEFAULT_EGG_HATCH_STEPS,
        )
        self.console_log(
            f"[Breeding] Egg {egg_id} created ({offspring.species.id}); hatches in {DEFAULT_EGG_HATCH_STEPS} steps."
        )
        return True

    def _stop_asset_hot_reload_watcher(self) -> None:
        from engine.asset_hot_reload_watcher import stop_hot_reload_watcher  # noqa: PLC0415

        stop_hot_reload_watcher(self)

    def on_close(self) -> None:
        editor = getattr(self, "editor_controller", None)
        stop_live_bridge = getattr(editor, "stop_live_bridge", None) if editor is not None else None
        if callable(stop_live_bridge):
            stop_live_bridge()
        self._stop_asset_hot_reload_watcher()
        base_on_close = getattr(engine.optional_arcade.arcade.Window, "on_close", None)
        if callable(base_on_close):
            base_on_close(self)

    def close(self) -> None:
        editor = getattr(self, "editor_controller", None)
        stop_live_bridge = getattr(editor, "stop_live_bridge", None) if editor is not None else None
        if callable(stop_live_bridge):
            stop_live_bridge()
        self._stop_asset_hot_reload_watcher()
        base_close = getattr(engine.optional_arcade.arcade.Window, "close", None)
        if callable(base_close):
            base_close(self)

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        self.engine_config.width = int(width)
        self.engine_config.height = int(height)
        self.console_visible_line_count = max(4, min(12, height // 60 or 4))
        if self.camera_controller is not None:
            self.camera_controller.on_resize(int(width), int(height))
        if getattr(self, "ui_controller", None) is not None:
            resize = getattr(self.ui_controller, "on_resize", None)
            if callable(resize):
                resize(int(width), int(height))
        if getattr(self, "editor_controller", None) is not None:
            resize = getattr(self.editor_controller, "on_resize", None)
            if callable(resize):
                resize(int(width), int(height))
        self._debug_text.y = self.height - 10
        lighting = getattr(self, "lighting", None)
        if lighting is not None:
            lighting.resize(int(width), int(height))

    # ------------------------------------------------------------------
    # Console: delegated to ConsoleController
    # ------------------------------------------------------------------
    def console_log(self, message: str) -> None:
        self.console_controller.log(message)

    def _hot_reload_log(self, message: str) -> None:
        """Compat helper used by input/scene controllers when strict mode blocks hot reload."""
        self.console_log(f"[HotReload] {message}")


_bind_input_router_methods(GameWindow)
_bind_state_facade_methods(GameWindow)
_bind_update_loop_methods(GameWindow)
_bind_ui_dispatcher_methods(GameWindow)
