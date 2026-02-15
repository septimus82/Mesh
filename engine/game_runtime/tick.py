from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from engine.swallowed_exceptions import record_swallowed
from engine.logging_tools import get_logger
from engine.ui import maybe_auto_open_quest_log, maybe_enqueue_demo_interior_hint, maybe_enqueue_quest_progress_toast


if TYPE_CHECKING:
    from engine.events import MeshEvent
    from engine.game import GameWindow


logger = get_logger(__name__)


# Module-level ghosting cache state
_ghosting_cache: dict[str, Any] = {
    "previous_state": None,
    "snapshots": [],
    "sprites_by_id": {},
}


def _apply_editor_sprite_ghosting(window: "GameWindow") -> tuple[list, dict]:
    """Apply editor sprite ghosting if alt-drag duplicate is active.

    Uses caching to avoid redundant sprite mutations when state hasn't changed.

    Returns:
        Tuple of (snapshots, sprites_by_id) for restore, or ([], {}) if inactive.
    """
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        _ghosting_cache["previous_state"] = None
        return [], {}

    # Get ghost settings from editor controller
    ghost_enabled = getattr(editor, "get_ghost_originals_enabled", lambda: True)()
    if not ghost_enabled:
        _ghosting_cache["previous_state"] = None
        return [], {}

    alt_dup_active = getattr(editor, "_alt_dup_active", False)
    if not alt_dup_active:
        _ghosting_cache["previous_state"] = None
        return [], {}

    original_ids = getattr(editor, "_alt_dup_original_selection", None)
    if not original_ids:
        _ghosting_cache["previous_state"] = None
        return [], {}

    # Get settings
    ghost_alpha = getattr(editor, "get_ghost_originals_alpha", lambda: 90)()
    ghost_dim_scale = getattr(editor, "get_ghost_originals_dim_scale", lambda: 0.65)()

    try:
        from engine.editor.editor_sprite_ghosting import (
            apply_ghosting_to_sprites,
            build_sprite_lookup_for_ghosting,
            make_ghosting_cache_key,
            should_reapply_ghosting,
        )

        # Check if we need to reapply ghosting
        current_state = make_ghosting_cache_key(
            ghost_ids=original_ids,
            alpha=ghost_alpha,
            dim_scale=ghost_dim_scale,
            enabled=ghost_enabled,
            alt_dup_active=alt_dup_active,
        )
        previous_state = _ghosting_cache.get("previous_state")

        if not should_reapply_ghosting(current_state, previous_state):
            # Cache hit - return cached snapshots and sprites
            return _ghosting_cache["snapshots"], _ghosting_cache["sprites_by_id"]

        # Cache miss - need to reapply ghosting
        sprites_by_id = build_sprite_lookup_for_ghosting(editor, original_ids)
        if not sprites_by_id:
            _ghosting_cache["previous_state"] = None
            return [], {}

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=original_ids,
            ghost_alpha=ghost_alpha,
            ghost_color_scale=ghost_dim_scale,
        )

        # Update cache
        _ghosting_cache["previous_state"] = current_state
        _ghosting_cache["snapshots"] = snapshots
        _ghosting_cache["sprites_by_id"] = sprites_by_id

        return snapshots, sprites_by_id
    except Exception as exc:  # noqa: BLE001
        # Ghosting is visual polish only, but we still count swallow sites.
        record_swallowed("engine.game_runtime.tick._apply_editor_sprite_ghosting", exc)
        _ghosting_cache["previous_state"] = None
        return [], {}


def _restore_editor_sprite_ghosting(snapshots: list, sprites_by_id: dict) -> None:
    """Restore sprites after ghosting."""
    if not snapshots:
        return

    try:
        from engine.editor.editor_sprite_ghosting import restore_ghosted_sprites
        restore_ghosted_sprites(snapshots, sprites_by_id)
    except Exception as exc:  # noqa: BLE001
        record_swallowed("engine.game_runtime.tick._restore_editor_sprite_ghosting", exc)


def on_draw(window: "GameWindow") -> None:
    # --- Post-processing: capture world rendering into offscreen FBO ---
    pp = getattr(window, "post_process_pipeline", None)
    if pp is not None:
        pp.begin(window)

    window.clear()
    window.camera.use()
    render_queue = getattr(window, "render_queue", None)
    if render_queue is not None:
        render_queue.begin_frame()

    # Apply editor sprite ghosting (for alt-drag duplicate)
    ghost_snapshots, ghost_sprites = _apply_editor_sprite_ghosting(window)

    try:
        lighting = getattr(window, "lighting", None)
        if lighting is not None and lighting.enabled:
            with lighting.begin():
                window.scene_controller.draw()
                window.particle_manager.draw()
                window.editor_controller.draw_world()
            # LightLayer draws/composites in screen space; ensure we are on the GUI camera
            # before calling lighting.end() so the lighting output isn't transformed by the
            # world camera projection.
            window.camera_controller.gui_camera.use()
            lighting.end()
        else:
            window.scene_controller.draw()
            window.particle_manager.draw()
            window.editor_controller.draw_world()
    finally:
        # Always restore ghosted sprites even if an exception occurs
        _restore_editor_sprite_ghosting(ghost_snapshots, ghost_sprites)

    fog_overlay = getattr(window, "fog_overlay", None)
    if fog_overlay is not None:
        window.camera.use()
        fog_overlay.draw_world()
        window.camera_controller.gui_camera.use()

    if render_queue is not None:
        render_queue.finalize(getattr(window, "perf_stats", None))

    # --- Post-processing: apply effect chain and blit to screen ---
    if pp is not None:
        pp.end(window)

    # Switch to GUI camera for UI elements
    window.camera_controller.gui_camera.use()

    if window.show_debug:
        window._draw_debug_overlay()
    window.ui_controller.draw()
    window.editor_controller.draw_overlay()

    if window.ai_debug_overlay_enabled:
        window.ai_debug_overlay.draw(window)

    # Draw debug overlay last
    if window.engine_config.debug_mode:
        window.draw_debug_overlay()

    # Draw shadowcast debug overlay
    if os.environ.get("MESH_SHADOWCAST_DEBUG") == "1":
        window._draw_shadowcast_debug()


def on_update(window: "GameWindow", delta_time: float) -> None:
    # Always update input to ensure we catch menu actions
    window.input_controller.update(delta_time)
    audio = getattr(window, "audio", None)
    if audio is not None:
        try:
            audio.update(delta_time)
        except Exception as exc:  # noqa: BLE001
            if not getattr(window, "_mesh_audio_update_error_logged", False):
                logger.warning("[Mesh][Audio] WARNING: update failed: %r", exc)
                setattr(window, "_mesh_audio_update_error_logged", True)

    if window.game_over:
        # Check for restart (SPACE or Attack)
        if window.input.was_action_pressed("attack") or window.input.is_key_down(optional_arcade.arcade.key.SPACE):
            window.game_over = False
            window.game_over_screen.visible = False
            window.paused = False
            window.request_scene_reload()
        return

    if window.paused:
        window.ui_controller.update(delta_time)
        return

    if getattr(window, "cutscene_controller", None) is not None:
        window.cutscene_controller.update(delta_time)

    window.scene_controller.update(delta_time)
    window.particle_manager.update()
    lighting = getattr(window, "lighting", None)
    if lighting is not None:
        lighting.update(delta_time)
    window.ui_controller.update(delta_time)
    if hasattr(window, "day_night") and not window.paused and not window.game_over:
        try:
            window.day_night.update(delta_time)
            # Persist time-of-day into game state
            window.game_state_controller.set_var("time_of_day_hours", window.day_night.hour)
            if lighting is not None and getattr(window.day_night, "enabled", False):
                r, g, b = window.day_night.compute_ambient_rgb()
                lighting.set_ambient_rgb(r, g, b)
        except Exception as exc:  # noqa: BLE001
            if not getattr(window, "_mesh_day_night_error_logged", False):
                logger.warning("[Mesh][DayNight] WARNING: update failed: %r", exc)
                setattr(window, "_mesh_day_night_error_logged", True)
    gs_controller = getattr(window, "game_state_controller", None)
    if gs_controller is not None:
        gs_controller.update(delta_time)

    events = window.consume_events()
    if events and window.game_state_controller:
        for event in events:
            try:
                window.game_state_controller.handle_event(event)
            except Exception as exc:  # noqa: BLE001
                logger.error("[Mesh][Game] ERROR handling '%s': %s", event.type, exc)
    window._debug_print_events(events)
    if events:
        window.scene_controller._deliver_events_to_behaviours(events)

    maybe_auto_open_quest_log(window, getattr(window, "quest_manager", None))
    maybe_enqueue_quest_progress_toast(window, getattr(window, "quest_manager", None))
    maybe_enqueue_demo_interior_hint(window, dt=delta_time)
