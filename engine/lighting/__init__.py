"""Dynamic lighting system wrapping Arcade's experimental lights API.

Provides a game-ready lighting solution with:

- **Static Lights**: Scene-defined lights loaded from JSON
- **Dynamic Lights**: Attached to moving entities (torches, projectiles)
- **Light Flicker**: Procedural noise-based flickering effects
- **Light Cookies**: Textured light patterns (spotlights, windows)
- **Light Shafts**: Volumetric god-ray effects
- **Shadow Modes**: None, hard shadows, or direct shadows
- **Ambient Darkness**: Global darkness overlay with color tinting

Architecture:
    The LightManager wraps Arcade's LightLayer, providing a higher-level API
    for game-specific lighting needs. It handles graceful fallback when
    Arcade's lighting module is unavailable.

Light Types:
    - **Point lights**: Circular falloff from center point
    - **Ambient**: Global scene illumination
    - **Dynamic**: Lights that move with entities

Configuration (scene JSON)::

    {
        "settings": {
            "lighting_enabled": true,
            "lighting_ambient_color": [20, 20, 40, 255],
            "lighting_shadows_mode": "hard"
        },
        "lights": [
            {
                "type": "point",
                "x": 400, "y": 300,
                "radius": 200,
                "color": [255, 200, 100, 255],
                "flicker": {"enabled": true, "amount": 0.2}
            }
        ]
    }

Example Usage::

    # Add a dynamic light attached to an entity
    handle = light_manager.add_dynamic_light(
        owner=torch_sprite,
        radius=150,
        color=(255, 180, 80, 255),
        offset_y=20,
        flicker_enabled=True,
        flicker_amount=0.15
    )

    # Later, remove it
    light_manager.remove_dynamic_light(handle)

See Also:
    - :class:`DynamicLightHandle` for light attachment configuration
    - :mod:`engine.lighting.flicker` for flicker noise generation
    - :mod:`engine.lighting.occluders` for shadow casting geometry
"""

from __future__ import annotations

import math
import os
import importlib.util
import importlib
import zlib
from contextlib import nullcontext
from typing import Any, Iterable, Optional, TYPE_CHECKING

import engine.optional_arcade
from engine.logging_tools import get_logger

from . import cookies as _cookies
from . import occluder_layer_builder as _occluder_layer_builder
from . import occluder_utils as _occluder_utils
from . import lighting_stats as _lighting_stats
from . import lighting_snapshot as _lighting_snapshot
from . import polygon_raycaster as _polygon_raycaster
from . import shadowcast_snapshot as _shadowcast_snapshot
from . import shadow_selection as _shadow_selection
from . import shafts as _shafts
from . import shadow_pipeline as _shadow_pipeline
from . import static_light_builder as _static_light_builder
from .flicker import FlickerNoise, apply_light_flicker
from .types import DynamicLightHandle, _FlickerLightState, _LayerContext

logger = get_logger(__name__)

if TYPE_CHECKING:
    try:
        from arcade.experimental.lights import Light as _Light
        from arcade.experimental.lights import LightLayer as _LightLayer
    except ImportError:
        try:
            from arcade.lights import Light as _Light
            from arcade.lights import LightLayer as _LightLayer
        except ImportError:
            try:
                from arcade.future.light import Light as _Light
                from arcade.future.light import LightLayer as _LightLayer
            except ImportError:
                _Light = Any
                _LightLayer = Any
else:
    _Light = None
    _LightLayer = None

_LIGHT_MODULE_CANDIDATES: tuple[str, ...] = (
    "arcade.experimental.lights",
    "arcade.lights",
    "arcade.future.light",
)

_SWALLOW_ONCE_TAGS: set[str] = set()


def _log_swallow(tag: str, where: str, purpose: str, *, once: bool = False) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    logger.debug("SWALLOW[%s] %s %s", tag, where, purpose, exc_info=True)


def _resolve_light_symbols(
    *,
    find_spec_func: Any = None,
    import_module_func: Any = None,
) -> tuple[Any | None, Any | None]:
    finder = find_spec_func or importlib.util.find_spec
    importer = import_module_func or importlib.import_module
    for mod_name in _LIGHT_MODULE_CANDIDATES:
        try:
            if finder(mod_name) is None:
                continue
            mod = importer(mod_name)
            light = getattr(mod, "Light", None)
            layer = getattr(mod, "LightLayer", None)
            if light is not None and layer is not None:
                return light, layer
        except (ImportError, AttributeError, OSError):  # noqa: BLE001  # REASON: import fallback
            _log_swallow(
                "LGIN-001",
                "engine.lighting.__init__._resolve_light_symbols",
                "import_light_module_candidate",
            )
            continue
    return None, None


if engine.optional_arcade.arcade is not None:
    _Light, _LightLayer = _resolve_light_symbols()


class LightManager:
    """Central manager for all scene lighting including static and dynamic lights.

    Wraps Arcade's LightLayer with game-specific features like flicker effects,
    shadow modes, ambient darkness, and dynamic light attachment. Falls back
    gracefully when Arcade's lighting module is unavailable.

    Features:
        - Static lights loaded from scene JSON
        - Dynamic lights attached to moving sprites
        - Procedural flicker effects with deterministic seeds
        - Light cookies (textured patterns)
        - Multiple shadow modes (none, hard, direct)
        - Ambient darkness with color tinting
        - Debug visualization for occluders and shadows

    Attributes:
        window: Reference to the main game window.
        available: True if Arcade lighting API is available.
        enabled: True if lighting is active (can be toggled).
        ambient_color: Base ambient light color (R, G, B, A).
        shadows_mode: Current shadow mode ("none", "hard", "direct").
        shadowmask_enabled: Enable shadow mask rendering.

    Configuration:
        Many settings can be overridden via environment variables:
        - ``MESH_SHADOWS_MODE``: Force shadow mode
        - ``MESH_SHADOWCAST_MASK``: Enable shadow mask ("1")
        - ``MESH_SHADOWCAST_DEBUG``: Enable debug overlay ("1")
        - ``MESH_LIGHTING_DEBUG_GEOMETRY``: Show occluder geometry ("1")

    Example::

        # Create manager (usually done by GameWindow)
        lighting = LightManager(
            window,
            enabled=True,
            ambient_color=(20, 20, 40, 255),
            shadows_mode="hard"
        )

        # Load static lights from scene
        lighting.load_lights_from_scene(scene_data)

        # Add dynamic torch light
        torch = lighting.add_dynamic_light(
            owner=player,
            radius=150,
            color=(255, 180, 80, 255),
            flicker_enabled=True
        )

        # Toggle features at runtime
        lighting.toggle_shadowmask()
        lighting.set_shadows_mode("none")
    """

    def __init__(
        self,
        window: Any,
        *,
        enabled: bool = True,
        ambient_color: tuple[int, int, int, int] = (10, 10, 10, 255),
        max_static_lights: int | None = None,
        max_dynamic_lights: int | None = None,
        shadows_mode: str = "none",
        debug_shadows: bool = False,
    ) -> None:
        """Initialize the light manager.

        Args:
            window: The main game window.
            enabled: Whether lighting is initially enabled.
            ambient_color: Base ambient light as (R, G, B, A).
            max_static_lights: Optional limit on static light count.
            max_dynamic_lights: Optional limit on dynamic light count.
            shadows_mode: Initial shadow mode ("none", "hard", "direct").
            debug_shadows: Enable shadow debug visualization.
        """
        self.window = window
        self.available: bool = bool(_Light is not None and _LightLayer is not None)
        self.enabled: bool = bool(enabled) and self.available
        self.ambient_color = (ambient_color[0], ambient_color[1], ambient_color[2], ambient_color[3])
        self._max_static_lights = None if max_static_lights is None or int(max_static_lights) <= 0 else int(max_static_lights)
        self._max_dynamic_lights = None if max_dynamic_lights is None or int(max_dynamic_lights) <= 0 else int(max_dynamic_lights)

        self._width = getattr(window, "width", 0)
        self._height = getattr(window, "height", 0)
        self._layer: Any = None
        self._static_configs: list[dict[str, Any]] = []
        self._static_occluders: list[dict[str, Any]] = []
        self._processed_occluders: list[dict[str, Any]] = []
        self._static_lights: list[Any] = []
        self._dynamic_handles: list[DynamicLightHandle] = []
        self._static_count: int = 0
        self._flicker_time: float = 0.0
        self._flicker_lights: list[_FlickerLightState] = []
        self.ambient_tint: tuple[int, int, int, int] = (255, 255, 255, 255)
        self.ambient_darkness_alpha: int | None = None
        self._cookie_textures: dict[str, Any] = {}
        self._cookie_missing: set[str] = set()
        self._cookie_blend_warned: bool = False

        # Runtime toggles (seeded from env)
        self.shadowmask_enabled: bool = os.environ.get("MESH_SHADOWCAST_MASK") == "1"
        self.shadowcast_debug_enabled: bool = os.environ.get("MESH_SHADOWCAST_DEBUG") == "1" or debug_shadows
        self.debug_geometry_enabled: bool = os.environ.get("MESH_LIGHTING_DEBUG_GEOMETRY") == "1"
        
        env_shadows = os.environ.get("MESH_SHADOWS_MODE")
        if env_shadows:
            self.shadows_mode = str(env_shadows).strip().lower()
        else:
            self.shadows_mode = str(shadows_mode).strip().lower()
            
        self._shadowmask_overridden: bool = False
        self._shadowcast_debug_overridden: bool = False
        self._debug_geometry_overridden: bool = False
        self._shadows_mode_overridden: bool = False

        if self.available:
            self._rebuild_layer()
        self._last_lighting_stats: dict[str, Any] = {}

    def toggle_shadowmask(self) -> bool:
        """Toggle shadow mask feature and rebuild light layer.

        Returns:
            New state of shadowmask_enabled after toggle.
        """
        self.shadowmask_enabled = not self.shadowmask_enabled
        self._shadowmask_overridden = True
        self._rebuild_layer()
        return self.shadowmask_enabled

    def toggle_shadowcast_debug(self) -> bool:
        """Toggle shadowcast debug overlay visualization.

        Returns:
            New state of shadowcast_debug_enabled after toggle.
        """
        self.shadowcast_debug_enabled = not self.shadowcast_debug_enabled
        self._shadowcast_debug_overridden = True
        # Debug overlay is drawn in snapshot or separate hook, usually doesn't require rebuild
        # but if it affects snapshot generation which might be used for rendering debug lines...
        # The snapshot method checks the flag.
        return self.shadowcast_debug_enabled

    def toggle_debug_geometry(self) -> bool:
        """Toggle occluder/shadow outline debug overlay.

        Returns:
            New state of debug_geometry_enabled after toggle.
        """
        self.debug_geometry_enabled = not self.debug_geometry_enabled
        self._debug_geometry_overridden = True
        return self.debug_geometry_enabled

    def set_shadows_mode(self, mode: str) -> str:
        """Set the shadow rendering mode.

        Args:
            mode: Shadow mode - one of:
                - "none": No shadows (fastest)
                - "hard": Hard-edged shadows from occluders
                - "direct": Direct shadow projection

        Returns:
            The newly set shadows mode.

        Raises:
            ValueError: If mode is not a valid option.
        """
        m = str(mode or "").strip().lower()
        if m not in {"none", "hard", "direct"}:
            raise ValueError(f"Invalid shadows_mode: {m}")
        self.shadows_mode = m
        self._shadows_mode_overridden = True
        return self.shadows_mode

    def _ambient_rgb(self) -> tuple[int, int, int]:
        rgba = self._ambient_rgba()
        return (rgba[0], rgba[1], rgba[2])

    def _ambient_rgba(self) -> tuple[int, int, int, int]:
        base = getattr(self, "ambient_color", (10, 10, 10, 255))
        tint = getattr(self, "ambient_tint", (255, 255, 255, 255))
        r = int(base[0]) * int(tint[0]) / 255.0
        g = int(base[1]) * int(tint[1]) / 255.0
        b = int(base[2]) * int(tint[2]) / 255.0
        alpha = int(base[3]) if len(base) > 3 else 255
        alpha_override = getattr(self, "ambient_darkness_alpha", None)
        if alpha_override is not None:
            try:
                alpha = int(alpha_override)
            except (TypeError, ValueError):  # noqa: BLE001  # REASON: alpha parse
                _log_swallow(
                    "LGIN-002",
                    "engine.lighting.__init__.LightManager._ambient_rgba",
                    "parse_ambient_darkness_alpha",
                )
                pass
        return (
            max(0, min(255, int(round(r)))),
            max(0, min(255, int(round(g)))),
            max(0, min(255, int(round(b)))),
            max(0, min(255, int(round(alpha)))),
        )

    def _draw_layer_safe(self) -> bool:
        """Best-effort LightLayer.draw call compatible across Arcade versions."""
        layer = self._layer
        if layer is None:
            return False
        draw = getattr(layer, "draw", None)
        if not callable(draw):
            return False
        rgb = self._ambient_rgb()
        # Try to draw without position (screen space composition)
        try:
            draw(ambient_color=rgb)
            return True
        except TypeError:
            pass
        try:
            draw(rgb)
            return True
        except TypeError:
            pass
        try:
            draw()
            return True
        except TypeError:
            pass
        return False

    def _log_counter_once(self, key: str, msg: str) -> None:
        """Log a message once per key, with a counter."""
        counters = getattr(self, "_mesh_logged_counters", None)
        if not isinstance(counters, dict):
            counters = {}
            setattr(self, "_mesh_logged_counters", counters)
        
        count = counters.get(key, 0)
        counters[key] = count + 1
        
        if count == 0:
            print(f"[Mesh][Lighting] WARNING {key}: {msg}")

    # ------------------------------------------------------------------ public API
    def begin(self):
        if not (self.enabled and self._layer):
            return nullcontext()
        layer = self._layer
        enter = getattr(layer, "__enter__", None)
        exit_ = getattr(layer, "__exit__", None)
        if callable(enter) and callable(exit_):
            return layer
        if callable(getattr(layer, "use", None)):
            return _LayerContext(layer)
        return nullcontext()

    def end(self) -> None:
        if not (self.enabled and self._layer):
            return
        if self.shadows_mode == "hard":
            try:
                self._end_hard_shadows_overlay()
            except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001  # REASON: shadow overlay
                _log_swallow(
                    "LGIN-003",
                    "engine.lighting.__init__.LightManager.end",
                    "end_hard_shadows_overlay",
                    once=True,
                )
                try:
                    self._draw_layer_safe()
                except Exception as exc2:  # pragma: no cover  # noqa: BLE001  # REASON: layer draw
                    _log_swallow(
                        "LGIN-004",
                        "engine.lighting.__init__.LightManager.end",
                        "draw_layer_safe_after_hard_shadow_failure",
                        once=True,
                    )
        elif self.shadows_mode == "direct":
            try:
                self._draw_layer_safe()
            except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001  # REASON: layer draw
                _log_swallow(
                    "LGIN-005",
                    "engine.lighting.__init__.LightManager.end",
                    "draw_layer_safe_direct_mode",
                    once=True,
                )
            try:
                self._draw_direct_shadows()
            except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001  # REASON: shadow draw
                _log_swallow(
                    "LGIN-006",
                    "engine.lighting.__init__.LightManager.end",
                    "draw_direct_shadows",
                    once=True,
                )
        else:
            try:
                self._draw_layer_safe()
            except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001  # REASON: layer draw
                _log_swallow(
                    "LGIN-007",
                    "engine.lighting.__init__.LightManager.end",
                    "draw_layer_safe_default_mode",
                    once=True,
                )
        try:
            cam = getattr(self.window, "camera", None)
            cam_pos = getattr(cam, "position", (0.0, 0.0)) if cam is not None else (0.0, 0.0)
            offset = (float(cam_pos[0]), float(cam_pos[1]))
        except (TypeError, ValueError, IndexError, KeyError):  # REASON: camera offset coercion fallback
            _log_swallow(
                "LGIN-008",
                "engine.lighting.__init__.LightManager.end",
                "compute_camera_offset",
                once=True,
            )
            offset = (0.0, 0.0)
        try:
            self._apply_light_cookies(target_fbo=None, offset=offset)
        except Exception:  # pragma: no cover - defensive  # noqa: BLE001  # REASON: cookie apply
            _log_swallow(
                "LGIN-009",
                "engine.lighting.__init__.LightManager.end",
                "apply_light_cookies",
                once=True,
            )
            pass
        try:
            self._apply_light_shafts(target_fbo=None, offset=offset)
        except Exception:  # pragma: no cover - defensive  # noqa: BLE001  # REASON: shafts apply
            _log_swallow(
                "LGIN-010",
                "engine.lighting.__init__.LightManager.end",
                "apply_light_shafts",
                once=True,
            )
            pass
        if self.debug_geometry_enabled and bool(getattr(self.window, "show_debug", False)):
            try:
                self._draw_debug_geometry()
            except Exception as exc:  # pragma: no cover - defensive  # noqa: BLE001  # REASON: debug draw
                _log_swallow(
                    "LGIN-011",
                    "engine.lighting.__init__.LightManager.end",
                    "draw_debug_geometry",
                    once=True,
                )

    def _end_hard_shadows_overlay(self) -> bool:
        return _shadow_pipeline.end_hard_shadows_overlay(self)

    def _draw_pending_shadow_fallback(self) -> None:
        _shadow_pipeline.draw_pending_shadow_fallback(self)

    def _draw_direct_shadows(self) -> None:
        _shadow_pipeline.draw_direct_shadows(self)

    def _end_hard_shadows_composite(self) -> bool:
        return _shadow_pipeline.end_hard_shadows_composite(self)

    def _draw_hard_shadow_fallback(
        self,
        *,
        draw: Any,
        offset: tuple[float, float],
        viewport: Any,
        polys: list[list[tuple[float, float]]],
        stats: dict[str, Any],
    ) -> bool:
        return _shadow_pipeline.draw_hard_shadow_fallback(
            self,
            draw=draw,
            offset=offset,
            viewport=viewport,
            polys=polys,
            stats=stats,
        )

    def _select_shadow_light_params(self) -> tuple[float, float, float] | None:
        return _shadow_selection.select_shadow_light_params(self)

    def _extract_light_pos_radius(self, light: Any) -> tuple[float, float, float] | None:
        return _shadow_selection.extract_light_pos_radius(light)

    def _select_shadow_light(self) -> tuple[str, tuple[float, float], float, Any] | None:
        return _shadow_selection.select_shadow_light(self)

    def _draw_hard_shadows(self) -> None:
        from .shadows import Viewport, build_shadow_polygons, cull_occluders_for_light, render_shadow_mask  # noqa: PLC0415
        rects = _occluder_utils.build_rect_occluders(self._static_occluders)

        selected = self._select_shadow_light_params()
        if selected is None:
            return
        lx, ly, radius = selected
        if radius <= 0:
            return

        culled = cull_occluders_for_light(lx, ly, radius, rects)
        polys = build_shadow_polygons((lx, ly), radius, culled)
        viewport = Viewport(x=0.0, y=0.0, width=float(getattr(self.window, "width", 0) or 0), height=float(getattr(self.window, "height", 0) or 0))
        render_shadow_mask(self.window, polys, viewport)

    def _draw_debug_geometry(self) -> None:
        from .debug import draw_occluder_rects, draw_shadow_polygons  # noqa: PLC0415
        from .shadows import build_shadow_polygons  # noqa: PLC0415
        rects = _occluder_utils.build_rect_occluders(self._static_occluders)
        draw_occluder_rects(self.window, rects)

        selected = self._select_shadow_light_params()
        if selected is None:
            return
        lx, ly, radius = selected
        try:
            light_pos = (float(lx), float(ly))
            light_radius = float(radius)
            polys = build_shadow_polygons(light_pos, light_radius, rects)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):  # REASON: debug geometry shape/coercion fallback
            _log_swallow(
                "LGIN-012",
                "engine.lighting.__init__.LightManager._draw_debug_geometry",
                "build_shadow_polygons",
                once=True,
            )
            polys = []
        draw_shadow_polygons(self.window, polys)

    def configure_scene_lights(self, lights_config: Optional[Iterable[dict[str, Any]]]) -> None:
        """Apply static lights from scene JSON."""
        self._static_configs = list(lights_config or [])
        if not self.available:
            return
        self._rebuild_layer()

    def configure_scene_occluders(self, occluders_config: Optional[Iterable[dict[str, Any]]]) -> None:
        """Apply static occluders from scene JSON."""
        self._static_occluders = list(occluders_config or [])
        if not self.available:
            return
        self._rebuild_layer()

    def get_lighting_snapshot(self) -> dict[str, Any]:
        """Return a deterministic snapshot of the current lighting configuration."""
        return _lighting_snapshot.build_lighting_snapshot(self)

    def _cast_ray(self, origin: tuple[float, float], angle: float, max_radius: float) -> dict[str, Any]:
        return _polygon_raycaster.cast_ray(self, origin, angle, max_radius)

    def set_ambient_rgb(self, r: int, g: int, b: int, a: int | None = None) -> None:
        """Set ambient color (keeping alpha if not provided)."""
        alpha = self.ambient_color[3] if a is None else int(a)
        self.ambient_color = (int(r), int(g), int(b), alpha)

    def register_dynamic_light(
        self,
        *,
        owner: Any,
        radius: float,
        color: Any = (255, 255, 255, 255),
        color_rgba: tuple[int, int, int, int] | None = None,
        mode: str = "soft",
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        flicker_enabled: bool = False,
        flicker_seed: int | None = None,
        flicker_speed: float = 1.0,
        flicker_amount: float = 0.0,
        flicker_radius_px: float | None = None,
        flicker_intensity: float | None = None,
        cookie_id: str | None = None,
        cookie_scale: float = 1.0,
        cookie_rotation_deg: float = 0.0,
        cookie_offset_px: tuple[float, float] | None = None,
        shafts_enabled: bool = False,
        shafts_length_px: float = 220.0,
        shafts_width_px: float = 140.0,
        shafts_rotation_deg: float = 0.0,
        shafts_alpha: float = 0.35,
        shafts_noise_speed: float = 0.08,
        shafts_noise_amount: float = 0.15,
    ) -> Optional[DynamicLightHandle]:
        if self._max_dynamic_lights is not None and len(self._dynamic_handles) >= self._max_dynamic_lights:
            return None
        if not (self.enabled and _Light and _LightLayer):
            return None
        if color_rgba is not None:
            resolved_color = self._normalize_color(color_rgba)
        else:
            resolved_color = self._normalize_color(color)
        base_radius = float(radius)
        base_color = resolved_color
        light = self._create_light(
            getattr(owner, "center_x", 0.0) + offset_x,
            getattr(owner, "center_y", 0.0) + offset_y,
            base_radius,
            base_color,
            mode,
        )
        if light is None:
            return None
        try:
            flicker_speed = float(flicker_speed)
        except (TypeError, ValueError):  # noqa: BLE001  # REASON: speed parse
            _log_swallow(
                "LGIN-013",
                "engine.lighting.__init__.LightManager.register_dynamic_light",
                "parse_flicker_speed",
            )
            flicker_speed = 1.0
        try:
            flicker_amount = float(flicker_amount)
        except (TypeError, ValueError):  # noqa: BLE001  # REASON: amount parse
            _log_swallow(
                "LGIN-014",
                "engine.lighting.__init__.LightManager.register_dynamic_light",
                "parse_flicker_amount",
            )
            flicker_amount = 0.0
        seed_used = None
        if flicker_enabled:
            if flicker_seed is None:
                seed_used = self._derive_flicker_seed(owner, len(self._flicker_lights))
            else:
                try:
                    seed_used = int(flicker_seed)
                except (TypeError, ValueError):  # noqa: BLE001  # REASON: seed parse
                    _log_swallow(
                        "LGIN-015",
                        "engine.lighting.__init__.LightManager.register_dynamic_light",
                        "parse_flicker_seed",
                    )
                    seed_used = 0
        handle = DynamicLightHandle(
            owner=owner,
            light=light,
            offset_x=offset_x,
            offset_y=offset_y,
            base_radius=base_radius,
            base_color=base_color,
            color_rgba=color_rgba,
            flicker_enabled=bool(flicker_enabled),
            flicker_seed=seed_used,
            flicker_speed=flicker_speed,
            flicker_amount=flicker_amount,
            flicker_radius_px=flicker_radius_px,
            flicker_intensity=flicker_intensity,
            cookie_id=str(cookie_id).strip() if isinstance(cookie_id, str) and cookie_id.strip() else None,
            cookie_scale=float(cookie_scale),
            cookie_rotation_deg=float(cookie_rotation_deg),
            cookie_offset_px=self._normalize_cookie_offset(cookie_offset_px),
            shafts_enabled=bool(shafts_enabled),
            shafts_length_px=float(shafts_length_px),
            shafts_width_px=float(shafts_width_px),
            shafts_rotation_deg=float(shafts_rotation_deg),
            shafts_alpha=float(shafts_alpha),
            shafts_noise_speed=float(shafts_noise_speed),
            shafts_noise_amount=float(shafts_noise_amount),
        )
        self._dynamic_handles.append(handle)
        self._add_light(light)
        if handle.flicker_enabled:
            seed = 0 if handle.flicker_seed is None else int(handle.flicker_seed)
            radius_px = handle.flicker_radius_px
            if radius_px is not None:
                try:
                    radius_px = float(radius_px)
                except (TypeError, ValueError):  # noqa: BLE001  # REASON: radius parse
                    _log_swallow(
                        "LGIN-016",
                        "engine.lighting.__init__.LightManager.register_dynamic_light",
                        "parse_flicker_radius_px",
                    )
                    radius_px = None
            intensity = handle.flicker_intensity
            if intensity is not None:
                try:
                    intensity = float(intensity)
                except (TypeError, ValueError):  # noqa: BLE001  # REASON: intensity parse
                    _log_swallow(
                        "LGIN-017",
                        "engine.lighting.__init__.LightManager.register_dynamic_light",
                        "parse_flicker_intensity",
                    )
                    intensity = None
            state = _FlickerLightState(
                light=light,
                base_radius=base_radius,
                base_color=base_color,
                noise=FlickerNoise(seed),
                speed=float(handle.flicker_speed),
                amount=float(handle.flicker_amount),
                radius_px=radius_px,
                intensity=intensity,
            )
            self._flicker_lights.append(state)
            flicker_radius, flicker_color = apply_light_flicker(
                base_radius=state.base_radius,
                base_color=state.base_color,
                noise=state.noise,
                time_s=self._flicker_time,
                speed=state.speed,
                amount=state.amount,
                radius_px=state.radius_px,
                intensity=state.intensity,
            )
            if hasattr(light, "radius"):
                light.radius = flicker_radius
            if hasattr(light, "color"):
                light.color = flicker_color
        return handle

    def update(self, dt: float) -> None:  # noqa: ARG002
        if not (self.enabled and self._layer):
            return
        dt = max(0.0, float(dt))
        self._flicker_time += dt
        for handle in list(self._dynamic_handles):
            owner = handle.owner
            if owner is None:
                continue
            x = getattr(owner, "center_x", None)
            y = getattr(owner, "center_y", None)
            if x is None or y is None:
                continue
            lx = float(x) + handle.offset_x
            ly = float(y) + handle.offset_y
            if hasattr(handle.light, "position"):
                handle.light.position = (lx, ly)
            else:
                if hasattr(handle.light, "x"):
                    handle.light.x = lx
                if hasattr(handle.light, "y"):
                    handle.light.y = ly

        if self._flicker_lights:
            for entry in self._flicker_lights:
                radius, color = apply_light_flicker(
                    base_radius=entry.base_radius,
                    base_color=entry.base_color,
                    noise=entry.noise,
                    time_s=self._flicker_time,
                    speed=entry.speed,
                    amount=entry.amount,
                    radius_px=entry.radius_px,
                    intensity=entry.intensity,
                )
                if hasattr(entry.light, "radius"):
                    entry.light.radius = radius
                if hasattr(entry.light, "color"):
                    entry.light.color = color

    def resize(self, width: int, height: int) -> None:
        self._width = int(width)
        self._height = int(height)
        if not self.available:
            return
        self._rebuild_layer()

    # ------------------------------------------------------------------ internals
    def _create_layer(self) -> Any:
        if _LightLayer is None:
            return None
        layer = _LightLayer(self._width, self._height)
        setter = getattr(layer, "set_background_color", None)
        if callable(setter):
            try:
                setter(engine.optional_arcade.arcade.color.BLACK)
            except Exception as exc:  # noqa: BLE001  # REASON: bgcolor set
                _log_swallow(
                    "LGIN-018",
                    "engine.lighting.__init__.LightManager._create_layer",
                    "set_background_color",
                    once=True,
                )
        return layer

    def _create_light(self, x: float, y: float, radius: float, color: Any, mode: str) -> Any:
        if _Light is None:
            return None
        if isinstance(color, str):
            raw = color.strip()
            if raw.startswith("#"):
                hex_ = raw[1:]
                if len(hex_) in {6, 8}:
                    try:
                        r = int(hex_[0:2], 16)
                        g = int(hex_[2:4], 16)
                        b = int(hex_[4:6], 16)
                        if len(hex_) == 8:
                            a = int(hex_[6:8], 16)
                            color = (r, g, b, a)
                        else:
                            color = (r, g, b)
                    except ValueError:  # REASON: hex color parse
                        _log_swallow(
                            "LGIN-019",
                            "engine.lighting.__init__.LightManager._create_light",
                            "parse_hex_color",
                            once=True,
                        )
            else:
                named = getattr(getattr(engine.optional_arcade.arcade, "color", None), raw.upper(), None)
                if named is not None:
                    color = named
        try:
            light_x = float(x)
            light_y = float(y)
            light_radius = float(radius)
        except (TypeError, ValueError):  # REASON: light construct numeric coercion fallback
            _log_swallow(
                "LGIN-019",
                "engine.lighting.__init__.LightManager._create_light",
                "construct_light",
                once=True,
            )
            return None
        try:
            return _Light(light_x, light_y, light_radius, color, mode=str(mode))
        except (AttributeError, OSError, TypeError, ValueError):  # REASON: light construct backend/shape fallback
            _log_swallow(
                "LGIN-019",
                "engine.lighting.__init__.LightManager._create_light",
                "construct_light",
                once=True,
            )
            return None

    def _normalize_color(self, color: Any) -> tuple[int, int, int, int]:
        if isinstance(color, str):
            raw = color.strip()
            if raw.startswith("#"):
                hex_ = raw[1:]
                if len(hex_) in {6, 8}:
                    try:
                        r = int(hex_[0:2], 16)
                        g = int(hex_[2:4], 16)
                        b = int(hex_[4:6], 16)
                        a = int(hex_[6:8], 16) if len(hex_) == 8 else 255
                        return (r, g, b, a)
                    except ValueError:  # REASON: hex color parse
                        _log_swallow(
                            "LGIN-020",
                            "engine.lighting.__init__.LightManager._normalize_color",
                            "normalize_hex_color",
                        )
            named = getattr(getattr(engine.optional_arcade.arcade, "color", None), raw.upper(), None)
            if named is not None:
                color = named
        if isinstance(color, (list, tuple)):
            if len(color) >= 3:
                try:
                    r = int(color[0])
                    g = int(color[1])
                    b = int(color[2])
                    a = int(color[3]) if len(color) >= 4 else 255
                    return (
                        max(0, min(255, r)),
                        max(0, min(255, g)),
                        max(0, min(255, b)),
                        max(0, min(255, a)),
                    )
                except (TypeError, ValueError, IndexError):  # noqa: BLE001  # REASON: color parse
                    _log_swallow(
                        "LGIN-020",
                        "engine.lighting.__init__.LightManager._normalize_color",
                        "normalize_sequence_color",
                    )
                    pass
        return (255, 255, 255, 255)

    def _resolve_light_color(self, cfg: dict[str, Any]) -> tuple[int, int, int, int]:
        if not isinstance(cfg, dict):
            return (255, 255, 255, 255)
        if "color_rgba" in cfg:
            return self._normalize_color(cfg.get("color_rgba"))
        return self._normalize_color(cfg.get("color", (255, 255, 255, 255)))

    def set_ambient_tint(self, color: Any) -> None:
        self.ambient_tint = self._normalize_color(color)

    def set_ambient_darkness_alpha(self, alpha: int) -> None:
        try:
            self.ambient_darkness_alpha = int(alpha)
        except (TypeError, ValueError):  # noqa: BLE001  # REASON: alpha parse
            _log_swallow(
                "LGIN-021",
                "engine.lighting.__init__.LightManager.set_ambient_darkness_alpha",
                "parse_ambient_darkness_alpha",
            )
            self.ambient_darkness_alpha = None

    def _add_light(self, light: Any) -> None:
        if not self._layer:
            return
        for attr in ("add_light", "add"):
            adder = getattr(self._layer, attr, None)
            if callable(adder):
                try:
                    adder(light)
                    return
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    _log_swallow(
                        "LGIN-022",
                        "engine.lighting.__init__.LightManager._add_light",
                        "invoke_single_light_adder",
                        once=True,
                    )
                    continue
        bulk = getattr(self._layer, "add_lights", None)
        if callable(bulk):
            try:
                bulk([light])
            except Exception as exc:  # noqa: BLE001  # REASON: bulk add
                _log_swallow(
                    "LGIN-023",
                    "engine.lighting.__init__.LightManager._add_light",
                    "invoke_add_lights_bulk",
                    once=True,
                )

    def _add_occluder(self, occluder: Any) -> None:
        if not self._layer:
            return
        # Try common methods for adding walls/occluders
        for attr in ("add_wall", "add_occluder"):
            adder = getattr(self._layer, attr, None)
            if callable(adder):
                try:
                    adder(occluder)
                    return
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    _log_swallow(
                        "LGIN-024",
                        "engine.lighting.__init__.LightManager._add_occluder",
                        "invoke_single_occluder_adder",
                        once=True,
                    )
                    continue
        # Fallback: check for bulk add
        bulk = getattr(self._layer, "add_walls", None)
        if callable(bulk):
            try:
                bulk([occluder])
            except Exception as exc:  # noqa: BLE001  # REASON: bulk add
                _log_swallow(
                    "LGIN-025",
                    "engine.lighting.__init__.LightManager._add_occluder",
                    "invoke_add_walls_bulk",
                    once=True,
                )

    def _add_polygon_light(self, points: list[tuple[float, float]], light_config: dict[str, Any]) -> bool:
        if not self._layer:
            return False
        # Try methods for adding polygon lights
        for attr in ("add_light_polygon", "add_polygon_light", "add_hole_polygon"):
            adder = getattr(self._layer, attr, None)
            if callable(adder):
                try:
                    adder(points, **light_config)
                    return True
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    _log_swallow(
                        "LGIN-026",
                        "engine.lighting.__init__.LightManager._add_polygon_light",
                        "invoke_polygon_light_adder",
                        once=True,
                    )
                    continue
        return False

    def _is_valid_polygon(self, points: list[tuple[float, float]]) -> bool:
        return _polygon_raycaster.is_valid_polygon(points)

    def _round_points(self, points: list[tuple[float, float]], ndigits: int = 3) -> list[tuple[float, float]]:
        return _polygon_raycaster.round_points(points, ndigits=ndigits)

    def _rebuild_layer(self) -> None:
        if not self.available:
            return
        try:
            self._layer = self._create_layer()
        except Exception:  # noqa: BLE001  # REASON: layer create
            _log_swallow(
                "LGIN-027",
                "engine.lighting.__init__.LightManager._rebuild_layer",
                "create_layer",
                once=True,
            )
            # Likely no active window (e.g., during headless tests); disable gracefully.
            self._layer = None
            self.enabled = False
            self.available = False
            return
        
        _occluder_layer_builder.rebuild_occluder_layer(self)
        _static_light_builder.rebuild_static_and_dynamic_lights(self)

    def _normalize_cookie_offset(self, value: Any) -> tuple[float, float]:
        return _cookies.normalize_cookie_offset(value)

    def _collect_cookie_draw_specs(self, offset: tuple[float, float]) -> list[dict[str, Any]]:
        return _cookies.collect_cookie_draw_specs(self, offset)

    def _collect_shafts_draw_specs(self, offset: tuple[float, float]) -> list[dict[str, Any]]:
        return _shafts.collect_shafts_draw_specs(self, offset)

    def _apply_light_shafts(self, *, target_fbo: Any, offset: tuple[float, float]) -> int:
        return _shafts.apply_light_shafts(self, target_fbo=target_fbo, offset=offset)

    def _load_cookie_texture(self, cookie_id: str) -> Any:
        return _cookies.load_cookie_texture(self, cookie_id)

    def _apply_light_cookies(self, *, target_fbo: Any, offset: tuple[float, float]) -> int:
        return _cookies.apply_light_cookies(self, target_fbo=target_fbo, offset=offset)

    @staticmethod
    def _derive_flicker_seed(owner: Any, fallback: int) -> int:
        if owner is None:
            return int(fallback)
        for attr in ("entity_id", "prefab_id", "name", "id"):
            value = getattr(owner, attr, None)
            if value is None or value == "":
                continue
            text = str(value)
            return int(zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF)
        return int(fallback)

    def _get_light_polygon_points(self, light_config: dict[str, Any]) -> list[tuple[float, float]]:
        return _polygon_raycaster.get_light_polygon_points(self, light_config)

    def get_stats(self) -> dict[str, Any]:
        """Return a snapshot of lighting statistics and limits."""
        return {
            "available": self.available,
            "enabled": self.enabled,
            "static_count": self._static_count,
            "dynamic_count": len(self._dynamic_handles),
            "max_static": self._max_static_lights,
            "max_dynamic": self._max_dynamic_lights,
        }

    def get_lighting_stats(self) -> dict[str, Any]:
        return _lighting_stats.build_lighting_stats(self)

    def set_max_static_lights(self, value: int | None) -> None:
        if value is None or int(value) <= 0:
            self._max_static_lights = None
        else:
            self._max_static_lights = int(value)

    def set_max_dynamic_lights(self, value: int | None) -> None:
        if value is None or int(value) <= 0:
            self._max_dynamic_lights = None
        else:
            self._max_dynamic_lights = int(value)


# Re-exports from submodules for clean public API
# Config module - dataclasses and parsing
from .lighting_config import (
    LightConfig,
    OccluderConfig,
    LightingSceneConfig,
    normalize_color,
    parse_light_config,
    parse_occluder_config,
    parse_scene_config,
    DEFAULT_AMBIENT_COLOR,
    DEFAULT_MAX_STATIC_LIGHTS,
    DEFAULT_MAX_DYNAMIC_LIGHTS,
)

# Cache module - invalidation and state tracking
from .lighting_cache import (
    LightingCacheState,
    CacheInvalidationResult,
    check_cache_invalidation,
    update_cache_state,
    mark_lights_dirty,
    mark_shadows_dirty,
    mark_all_dirty,
)

# Geometry module - shadow hull computation
from .lighting_geometry import (
    LightGeometry,
    SceneGeometry,
    compute_hulls_digest,
    compute_light_geometry,
    compute_scene_geometry,
)

# Plan module - headless lighting model
from .lighting_plan import (
    LightPlanEntry,
    OccluderPlanEntry,
    LightingPlan,
    build_lighting_plan,
    build_lighting_plan_from_dicts,
)

# Render module - draw helpers
from .lighting_render import (
    RenderStats,
    prepare_light_layer,
    draw_layer_safe,
    clear_layer,
    compute_render_plan,
)

# Shadow geometry (already exists)
from .shadow_geometry import (
    Point,
    Polygon,
    ShadowParams,
    ShadowGeometryResult,
    compute_shadow_hulls,
    compute_shadow_geometry,
    normalize_polygon,
    validate_polygon,
)

# Shadow geometry adapter
from .shadow_geometry_adapter import (
    rect_to_polygon,
    rects_to_polygons,
    occluder_config_to_polygon,
    occluder_configs_to_polygons,
    compute_shadow_hulls_from_rects,
    compute_shadow_hulls_from_configs,
    compute_shadow_geometry_from_configs,
)

__all__ = [
    # Main class
    "LightManager",
    "DynamicLightHandle",
    # Config
    "LightConfig",
    "OccluderConfig",
    "LightingSceneConfig",
    "normalize_color",
    "parse_light_config",
    "parse_occluder_config",
    "parse_scene_config",
    "DEFAULT_AMBIENT_COLOR",
    "DEFAULT_MAX_STATIC_LIGHTS",
    "DEFAULT_MAX_DYNAMIC_LIGHTS",
    # Cache
    "LightingCacheState",
    "CacheInvalidationResult",
    "check_cache_invalidation",
    "update_cache_state",
    "mark_lights_dirty",
    "mark_shadows_dirty",
    "mark_all_dirty",
    # Geometry
    "LightGeometry",
    "SceneGeometry",
    "compute_hulls_digest",
    "compute_light_geometry",
    "compute_scene_geometry",
    # Plan
    "LightPlanEntry",
    "OccluderPlanEntry",
    "LightingPlan",
    "build_lighting_plan",
    "build_lighting_plan_from_dicts",
    # Render
    "RenderStats",
    "prepare_light_layer",
    "draw_layer_safe",
    "clear_layer",
    "compute_render_plan",
    # Shadow geometry
    "Point",
    "Polygon",
    "ShadowParams",
    "ShadowGeometryResult",
    "compute_shadow_hulls",
    "compute_shadow_geometry",
    "normalize_polygon",
    "validate_polygon",
    # Shadow adapter
    "rect_to_polygon",
    "rects_to_polygons",
    "occluder_config_to_polygon",
    "occluder_configs_to_polygons",
    "compute_shadow_hulls_from_rects",
    "compute_shadow_hulls_from_configs",
    "compute_shadow_geometry_from_configs",
]
