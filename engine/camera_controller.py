"""Camera controller for Mesh Engine.

Provides smooth camera following, zoom control, screen shake, and camera areas
for dynamic viewport management during gameplay.

Key Features:
    - **Smooth Follow**: Lerp-based following with configurable strength
    - **Zoom Control**: Animated zoom with min/max bounds
    - **Screen Shake**: Both legacy (duration-based) and trauma-based systems
    - **Camera Areas**: Named regions with custom zoom/lerp overrides
    - **Bounds Clamping**: Keep camera within world boundaries
    - **Deadzone**: Prevent camera jitter for small movements

Architecture:
    The controller wraps Arcade's Camera2D and adds game-specific features.
    It maintains separate cameras for world rendering and GUI overlay.

Usage Example::

    # In game update loop
    camera = window.camera_controller

    # Follow player with smooth interpolation
    camera.update_camera_follow(
        target_x=player.center_x,
        target_y=player.center_y,
        dt=delta_time,
        lerp_factor=5.0,
        deadzone_px=20,
    )

    # Add screen shake on hit
    camera.shake_state.add_trauma(0.3)

    # Zoom in for dramatic moment
    camera.zoom_state.target = 1.5

See Also:
    - :class:`CameraArea` for defining custom camera zones
    - :class:`CameraShakeState` for shake configuration
    - Scene JSON ``settings.camera`` for per-scene camera config
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:

    from .game import GameWindow

logger = logging.getLogger(__name__)
_LOG_ONCE: set[str] = set()

_CAMERA_NEEDS_DIMENSIONS = False
ArcadeCamera: Any = None
if optional_arcade.arcade is not None:
    ArcadeCamera = getattr(optional_arcade.arcade, "Camera", None)
    if ArcadeCamera is not None:
        _CAMERA_NEEDS_DIMENSIONS = True
    else:
        camera_mod = getattr(optional_arcade.arcade, "camera", None)
        ArcadeCamera = getattr(camera_mod, "Camera2D", None) if camera_mod is not None else None

if ArcadeCamera is None:  # pragma: no cover - only used when optional_arcade.arcade is unavailable
    class ArcadeCamera:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN001
            raise RuntimeError("Arcade Camera API not available")

@dataclass(slots=True)
class CameraArea:
    """Defines a rectangular region with custom camera behavior.

    Camera areas allow different parts of a scene to have unique camera
    settings. When the follow target enters an area, the camera smoothly
    transitions to that area's zoom/lerp settings.

    Use cases:
        - Boss arenas with locked zoom
        - Scenic overlooks with wide zoom-out
        - Tight corridors with faster camera response
        - Cutscene triggers with specific framing

    Attributes:
        name: Unique identifier for debugging and transitions.
        x: Left edge of the area in world coordinates.
        y: Bottom edge of the area in world coordinates.
        width: Width of the area in pixels.
        height: Height of the area in pixels.
        zoom: Optional zoom override when inside this area.
        lerp_factor: Optional camera follow speed override.
        padding: Additional padding from area edges.
        priority: Higher priority areas take precedence when overlapping.

    Example (in scene JSON)::

        "settings": {
            "camera": {
                "areas": [
                    {
                        "name": "boss_arena",
                        "x": 800, "y": 0,
                        "width": 400, "height": 300,
                        "zoom": 0.8,
                        "priority": 10
                    }
                ]
            }
        }
    """
    name: str
    x: float
    y: float
    width: float
    height: float
    zoom: float | None = None
    lerp_factor: float | None = None
    padding: float = 0.0
    priority: int = 0

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Return area bounds as (left, bottom, right, top)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def contains(self, x: float, y: float) -> bool:
        """Check if a point is inside this area."""
        left, bottom, right, top = self.bounds
        return left <= x <= right and bottom <= y <= top


@dataclass(slots=True)
class CameraZoomState:
    """Manages animated zoom transitions for the camera.

    Zoom smoothly interpolates from ``current`` toward ``target`` each frame.
    Values are clamped between ``min_zoom`` and ``max_zoom``.

    Attributes:
        current: Current zoom level (1.0 = 100%, 2.0 = 200% magnification).
        target: Desired zoom level to animate toward.
        speed: Interpolation speed (higher = faster zoom transitions).
        min_zoom: Minimum allowed zoom (default 0.25 = 25%).
        max_zoom: Maximum allowed zoom (default 4.0 = 400%).

    Example::

        # Zoom in for dramatic effect
        zoom_state.target = 1.5

        # Zoom out for overview
        zoom_state.target = 0.5

        # Instant zoom (bypass animation)
        zoom_state.current = zoom_state.target = 2.0
    """
    current: float = 1.0
    target: float = 1.0
    speed: float = 5.0
    min_zoom: float = 0.25
    max_zoom: float = 4.0

    def clamp(self, value: float) -> float:
        """Clamp a zoom value to the allowed range."""
        return min(self.max_zoom, max(self.min_zoom, value))


@dataclass(slots=True)
class CameraShakeState:
    """Manages screen shake effects using both legacy and trauma systems.

    Two shake systems are available:

    **Legacy System** (duration-based):
        Set duration, amplitude, and frequency for a fixed-length shake.
        Uses sinusoidal oscillation with configurable falloff.

    **Trauma System** (recommended):
        Add "trauma" (0.0-1.0) which naturally decays over time.
        Shake intensity is trauma squared for natural feel.
        More flexible for stacking multiple damage sources.

    The trauma system is preferred for gameplay as it:
        - Stacks naturally (multiple hits add trauma)
        - Has smooth organic decay
        - Produces more cinematic results

    Attributes:
        timer: Current time into legacy shake.
        duration: Total legacy shake duration.
        amplitude: Legacy shake magnitude in pixels.
        frequency: Legacy shake oscillation speed.
        falloff: Legacy amplitude decay rate.
        offset_x, offset_y: Current frame's shake offset.
        trauma: Current trauma value (0.0-1.0).
        trauma_decay: How fast trauma decreases per second.
        trauma_max_offset: Maximum pixel offset at full trauma.
        trauma_frequency: Noise sampling frequency.

    Example::

        # Add trauma from taking damage
        shake.add_trauma(0.3)  # 30% trauma

        # Big hit adds more, naturally caps at 1.0
        shake.add_trauma(0.5)  # Now at 80% trauma

        # Configure trauma behavior
        shake.add_trauma(
            0.4,
            decay=2.0,        # Faster decay
            max_offset=20.0,  # Stronger shake
            seed=12345,       # Deterministic for replay
        )
    """

    timer: float = 0.0
    duration: float = 0.0
    amplitude: float = 0.0
    frequency: float = 0.0
    falloff: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    trauma: float = 0.0
    trauma_decay: float = 1.5
    trauma_max_offset: float = 12.0
    trauma_frequency: float = 24.0
    trauma_timer: float = 0.0
    trauma_angle: float = 0.0
    trauma_scale: float = 1.0
    rng: random.Random = field(default_factory=random.Random, repr=False)

    def reset(self) -> None:
        """Reset both legacy and trauma shake to idle state."""
        self.reset_legacy()
        self.reset_trauma()

    def reset_legacy(self) -> None:
        """Reset only legacy shake parameters."""
        self.timer = 0.0
        self.duration = 0.0
        self.amplitude = 0.0
        self.frequency = 0.0
        self.falloff = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

    def reset_trauma(self) -> None:
        """Reset only trauma shake parameters."""
        self.trauma = 0.0
        self.trauma_timer = 0.0
        self.trauma_angle = 0.0
        self.trauma_scale = 1.0

    def set_seed(self, seed: int | None) -> None:
        """Set RNG seed for deterministic shake (useful for replays)."""
        if seed is None:
            return
        self.rng.seed(int(seed))

    def add_trauma(
        self,
        amount: float,
        *,
        decay: float | None = None,
        max_offset: float | None = None,
        frequency: float | None = None,
        seed: int | None = None,
    ) -> None:
        """Add trauma to trigger/intensify screen shake.

        Trauma values stack additively but are capped at 1.0.
        Shake intensity scales with trauma squared for natural feel.

        Args:
            amount: Trauma to add (0.0-1.0 scale, but can exceed).
            decay: Override trauma decay rate (higher = faster settle).
            max_offset: Override maximum pixel offset at full trauma.
            frequency: Override noise sampling frequency.
            seed: Set RNG seed for deterministic behavior.
        """
        if decay is not None:
            self.trauma_decay = max(0.0, float(decay))
        if max_offset is not None:
            self.trauma_max_offset = max(0.0, float(max_offset))
        if frequency is not None:
            self.trauma_frequency = max(0.1, float(frequency))
        if seed is not None:
            self.set_seed(seed)
        self.trauma = min(1.0, max(0.0, self.trauma + float(amount)))


class CameraController:
    """Main camera controller managing viewport, follow, zoom, and shake.

    Wraps Arcade's camera system with game-specific features including
    smooth following, animated zoom, screen shake, camera areas, and
    world bounds clamping.

    Attributes:
        window: Reference to the main game window.
        camera: Arcade camera for world rendering.
        gui_camera: Separate camera for UI (unaffected by shake/zoom).
        zoom_state: Current zoom configuration and animation state.
        shake_state: Screen shake configuration and current offsets.
        areas: List of CameraArea zones with custom settings.
        active_area: Currently active camera area (or None for default).
        bounds: Optional (left, bottom, right, top) world bounds.

    Example::

        controller = CameraController(window)

        # Configure bounds from scene
        controller.bounds = (0, 0, 1600, 900)

        # Add camera areas
        controller.areas.append(CameraArea(
            name="boss_room",
            x=1200, y=0, width=400, height=300,
            zoom=0.75
        ))

        # In update loop
        controller.update_camera_follow(
            target_x=player.center_x,
            target_y=player.center_y,
            dt=delta_time
        )
    """

    def __init__(self, window: GameWindow) -> None:
        """Initialize the camera controller.

        Args:
            window: The main game window to attach cameras to.
        """
        self.window = window
        if _CAMERA_NEEDS_DIMENSIONS:
            self.camera = ArcadeCamera(window.width, window.height)
            self.gui_camera = ArcadeCamera(window.width, window.height)
        else:
            self.camera = ArcadeCamera(window=window)
            self.gui_camera = ArcadeCamera(window=window)
        self.zoom_state = CameraZoomState()
        self.shake_state = CameraShakeState()
        self.areas: list[CameraArea] = []
        self.active_area: CameraArea | None = None
        self.padding: float = 0.0
        self.default_lerp: float = 5.0
        self.default_deadzone: float = 0.0
        self.default_max_speed: float | None = None
        self.default_zoom: float = 1.0
        self.default_zoom_speed: float = 5.0
        self.default_padding: float = 0.0
        self.bounds: tuple[float, float, float, float] | None = None

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
    ) -> None:
        """Update camera position to follow a target with smooth interpolation.

        Call this each frame in the game update loop. The camera smoothly
        moves toward the target position, respecting bounds, deadzones,
        and camera area overrides.

        Args:
            target_x: Target X position to follow (usually player.center_x).
            target_y: Target Y position to follow (usually player.center_y).
            dt: Delta time in seconds since last frame.
            lerp_factor: Follow speed multiplier (higher = snappier).
            follow_strength: Alias for lerp_factor.
            deadzone_px: Symmetric deadzone radius (no movement if target
                within this distance of camera center).
            deadzone_w: Deadzone width (for asymmetric deadzones).
            deadzone_h: Deadzone height (for asymmetric deadzones).
            max_speed: Maximum camera movement speed in pixels/second.
            padding: Extra padding from world bounds.
            zoom: Target zoom level to animate toward.
            zoom_speed: Zoom interpolation speed.
            min_zoom: Override minimum zoom limit.
            max_zoom: Override maximum zoom limit.

        Note:
            If the target is inside a :class:`CameraArea`, that area's
            zoom and lerp_factor settings will override parameters.
        """
        camera = self.camera
        if camera is None:
            # print("[Mesh][Camera] WARNING: update_camera_follow called with no camera present")
            return

        target_x = float(target_x)
        target_y = float(target_y)
        if lerp_factor is not None:
            effective_lerp = float(lerp_factor)
        elif follow_strength is not None:
            effective_lerp = float(follow_strength)
        else:
            effective_lerp = float(self.default_lerp)
        area = self.get_camera_area_for_point(target_x, target_y)
        if area is not self.active_area:
            previous = self.active_area.name if self.active_area else "<default>"
            next_name = area.name if area else "<default>"
            print(f"[Mesh][Camera] area {previous} -> {next_name}")
            self.active_area = area

        if area and area.lerp_factor:
            effective_lerp = float(area.lerp_factor)

        effective_padding = max(0.0, padding, self.padding, self.default_padding)
        if area:
            effective_padding = max(effective_padding, area.padding)

        zoom_target = zoom
        if area and area.zoom is not None:
            zoom_target = area.zoom
        if zoom_target is None:
            zoom_target = self.default_zoom

        self._apply_zoom_target(
            zoom_target,
            speed=zoom_speed,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
        )

        self._update_camera_effects(dt)

        current_x, current_y = self.get_camera_center()
        zoom_value = max(1e-6, float(self.zoom_state.current))
        if deadzone_w is not None or deadzone_h is not None:
            dz_w = max(0.0, float(deadzone_w or 0.0))
            dz_h = max(0.0, float(deadzone_h or 0.0))
            half_w = dz_w * 0.5 / zoom_value
            half_h = dz_h * 0.5 / zoom_value
        else:
            effective_deadzone = max(0.0, deadzone_px if deadzone_px is not None else self.default_deadzone)
            half_w = effective_deadzone / zoom_value if effective_deadzone > 0.0 else 0.0
            half_h = half_w

        if half_w > 0.0:
            if target_x > current_x + half_w:
                target_x = target_x - half_w
            elif target_x < current_x - half_w:
                target_x = target_x + half_w
            else:
                target_x = current_x
        if half_h > 0.0:
            if target_y > current_y + half_h:
                target_y = target_y - half_h
            elif target_y < current_y - half_h:
                target_y = target_y + half_h
            else:
                target_y = current_y

        move_x = (target_x - current_x) * max(0.0, effective_lerp) * dt
        move_y = (target_y - current_y) * max(0.0, effective_lerp) * dt
        effective_max_speed = max_speed if max_speed is not None else self.default_max_speed
        if effective_max_speed is not None and effective_max_speed > 0.0:
            max_step = effective_max_speed * max(0.0, dt)
            dist = math.hypot(move_x, move_y)
            if dist > max_step and dist > 0.0:
                scale = max_step / dist
                move_x *= scale
                move_y *= scale

        new_x = current_x + move_x
        new_y = current_y + move_y

        if area:
            clamped_x, clamped_y = self.clamp_camera_to_rect(new_x, new_y, area.bounds, padding=effective_padding)
        else:
            clamped_x, clamped_y = self.clamp_camera_to_world(new_x, new_y, padding=effective_padding)

        final_x = clamped_x + self.shake_state.offset_x
        final_y = clamped_y + self.shake_state.offset_y

        move_to = getattr(camera, "move_to", None)
        if callable(move_to):
            move_to((final_x, final_y), 1.0)
        else:
            setattr(camera, "position", (final_x, final_y))

    def get_camera_area_for_point(self, x: float, y: float) -> CameraArea | None:
        for area in self.areas:
            if area.contains(x, y):
                return area
        return None

    def get_camera_center(self) -> tuple[float, float]:
        camera = self.camera
        if camera is None:
            return (self.window.width / 2.0, self.window.height / 2.0)

        position = getattr(camera, "position", None)
        if isinstance(position, (tuple, list)) and len(position) == 2:
            return (float(position[0]), float(position[1]))

        get_pos = getattr(camera, "get_position", None)
        if callable(get_pos):
            try:
                pos_value = get_pos()
                if isinstance(pos_value, (tuple, list)) and len(pos_value) == 2:
                    return (float(pos_value[0]), float(pos_value[1]))
            except Exception as exc:
                if "camera_get_position" not in _LOG_ONCE:
                    logger.warning("get_position() failed: %s", exc, exc_info=True)
                    _LOG_ONCE.add("camera_get_position")

        return (self.window.width / 2.0, self.window.height / 2.0)

    def clamp_camera_to_world(
        self,
        target_x: float,
        target_y: float,
        *,
        padding: float = 0.0,
    ) -> tuple[float, float]:
        if self.bounds is not None:
            return self.clamp_camera_to_rect(target_x, target_y, self.bounds, padding=padding)

        world_w = self.window.world_width
        world_h = self.window.world_height
        if world_w is None or world_h is None:
            return (target_x, target_y)

        half_w = self.window.width / 2.0
        half_h = self.window.height / 2.0
        padded_half_w = half_w + padding
        padded_half_h = half_h + padding

        min_x = padded_half_w
        max_x = max(padded_half_w, world_w - padded_half_w)
        min_y = padded_half_h
        max_y = max(padded_half_h, world_h - padded_half_h)

        clamped_x = min(max(target_x, min_x), max_x)
        clamped_y = min(max(target_y, min_y), max_y)
        return (clamped_x, clamped_y)

    def clamp_camera_to_rect(
        self,
        target_x: float,
        target_y: float,
        rect: tuple[float, float, float, float],
        *,
        padding: float = 0.0,
    ) -> tuple[float, float]:
        left, bottom, right, top = rect
        if right < left:
            left, right = right, left
        if top < bottom:
            bottom, top = top, bottom

        half_w = self.window.width / 2.0
        half_h = self.window.height / 2.0
        padded_half_w = half_w + padding
        padded_half_h = half_h + padding

        min_x = left + padded_half_w
        max_x = right - padded_half_w
        if min_x > max_x:
            center_x = (left + right) / 2.0
        else:
            center_x = min(max(target_x, min_x), max_x)

        min_y = bottom + padded_half_h
        max_y = top - padded_half_h
        if min_y > max_y:
            center_y = (bottom + top) / 2.0
        else:
            center_y = min(max(target_y, min_y), max_y)

        return (center_x, center_y)

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        camera = self.camera
        if camera is None:
            return (float(x), float(y))
        
        # Try new arcade 3.0 API first
        unproject = getattr(camera, "unproject", None)
        if callable(unproject):
            try:
                # unproject returns a 3 component tuple/vector
                world_pos = unproject((x, y))
                return float(world_pos[0]), float(world_pos[1])
            except Exception as exc:
                if "camera_unproject" not in _LOG_ONCE:
                    logger.warning("unproject() failed: %s", exc, exc_info=True)
                    _LOG_ONCE.add("camera_unproject")

        # Fallback to older screen_to_world if available
        transformer = getattr(camera, "screen_to_world", None)
        if callable(transformer):
            try:
                world_x, world_y = transformer(x, y)
                return float(world_x), float(world_y)
            except Exception as exc:
                if "camera_screen_to_world" not in _LOG_ONCE:
                    logger.warning("screen_to_world() failed: %s", exc, exc_info=True)
                    _LOG_ONCE.add("camera_screen_to_world")
        return (float(x), float(y))

    def set_zoom_target(self, zoom: float, *, speed: float | None = None) -> None:
        self._apply_zoom_target(zoom, speed=speed)

    @property
    def zoom(self) -> float:
        """Return the current zoom scalar (for debug overlays/UI)."""
        return float(getattr(self.zoom_state, "current", 1.0))

    def _apply_zoom_target(
        self,
        target: float,
        *,
        speed: float | None = None,
        min_zoom: float | None = None,
        max_zoom: float | None = None,
    ) -> None:
        if min_zoom is not None:
            self.zoom_state.min_zoom = float(min_zoom)
        if max_zoom is not None:
            self.zoom_state.max_zoom = float(max_zoom)

        self.zoom_state.target = self.zoom_state.clamp(float(target))
        if speed is not None:
            self.zoom_state.speed = float(speed)
        else:
            self.zoom_state.speed = self.default_zoom_speed

    def _update_camera_effects(self, dt: float) -> None:
        self._update_camera_zoom(dt)
        self._update_camera_shake(dt)

    def _update_camera_zoom(self, dt: float) -> None:
        state = self.zoom_state
        if state.speed <= 0 or dt <= 0:
            state.current = state.target
            self._set_camera_zoom_value(state.current)
            return

        delta = state.target - state.current
        if abs(delta) < 1e-4:
            state.current = state.target
            self._set_camera_zoom_value(state.current)
            return

        step = delta * min(1.0, state.speed * dt)
        state.current = state.clamp(state.current + step)
        self._set_camera_zoom_value(state.current)

    def _update_camera_shake(self, dt: float) -> None:
        state = self.shake_state
        legacy_x = 0.0
        legacy_y = 0.0
        if state.duration <= 0 or state.amplitude == 0:
            state.reset_legacy()
        else:
            state.timer += max(0.0, dt)
            if state.timer >= state.duration:
                state.reset_legacy()
            else:
                progress = state.timer / state.duration
                damping = max(0.0, 1.0 - progress) ** state.falloff
                angle = state.timer * state.frequency * 2.0 * math.pi
                legacy_x = math.sin(angle) * state.amplitude * damping
                legacy_y = math.cos(angle * 0.85) * state.amplitude * 0.75 * damping

        trauma_x = 0.0
        trauma_y = 0.0
        if state.trauma > 0.0:
            state.trauma = max(0.0, state.trauma - state.trauma_decay * max(0.0, dt))
            interval = 1.0 / max(0.1, state.trauma_frequency)
            state.trauma_timer += max(0.0, dt)
            if state.trauma_timer >= interval:
                state.trauma_timer = 0.0
                state.trauma_angle = state.rng.random() * math.tau
                state.trauma_scale = 0.5 + state.rng.random() * 0.5
            intensity = state.trauma * state.trauma
            magnitude = state.trauma_max_offset * intensity * state.trauma_scale
            trauma_x = math.cos(state.trauma_angle) * magnitude
            trauma_y = math.sin(state.trauma_angle) * magnitude

        state.offset_x = legacy_x + trauma_x
        state.offset_y = legacy_y + trauma_y

    def _set_camera_zoom_value(self, zoom_value: float) -> None:
        camera = self.camera
        if camera is None:
            return
        applied = False
        if hasattr(camera, "zoom"):
            try:
                camera.zoom = zoom_value
                applied = True
            except Exception:
                applied = False
        if not applied and hasattr(camera, "scale"):
            try:
                camera.scale = zoom_value
                applied = True
            except Exception:
                applied = False
        if not applied:
            setter = getattr(camera, "set_zoom", None)
            if callable(setter):
                try:
                    setter(zoom_value)
                except Exception as exc:
                    if "camera_set_zoom" not in _LOG_ONCE:
                        logger.warning("set_zoom() failed: %s", exc, exc_info=True)
                        _LOG_ONCE.add("camera_set_zoom")

    def build_camera_areas(self, entries: list[Any]) -> None:
        areas: list[CameraArea] = []
        for index, entry in enumerate(entries):
            parsed = self._parse_camera_area(entry, index)
            if parsed is not None:
                areas.append(parsed)
        areas.sort(key=lambda area: area.priority, reverse=True)
        self.areas = areas

    def _parse_camera_area(self, entry: Any, index: int) -> CameraArea | None:
        if not isinstance(entry, dict):
            print(f"[Mesh][Camera] WARNING: camera areas[{index}] must be an object")
            return None
        try:
            x = float(entry["x"])
            y = float(entry["y"])
            width = float(entry["width"])
            height = float(entry["height"])
        except (KeyError, TypeError, ValueError):
            print(f"[Mesh][Camera] WARNING: camera areas[{index}] missing numeric x/y/width/height")
            return None
        if width <= 0 or height <= 0:
            print(f"[Mesh][Camera] WARNING: camera areas[{index}] must have positive width/height")
            return None
        name = str(entry.get("name") or f"area_{index}")
        zoom_value = entry.get("zoom")
        lerp_value = entry.get("lerp_factor")
        padding_value = entry.get("padding")
        priority_value = entry.get("priority")
        zoom = None if zoom_value is None else self._coerce_optional_float(zoom_value)
        lerp = None if lerp_value is None else self._coerce_optional_float(lerp_value)
        padding = self._coerce_float(padding_value, 0.0) if padding_value is not None else 0.0
        priority = int(priority_value) if isinstance(priority_value, (int, float)) else 0
        return CameraArea(
            name=name,
            x=x,
            y=y,
            width=width,
            height=height,
            zoom=zoom,
            lerp_factor=lerp,
            padding=max(0.0, padding),
            priority=priority,
        )

    def _coerce_optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def configure_from_scene(self, settings: dict[str, Any]) -> None:
        camera_settings = settings.get("camera") if isinstance(settings, dict) else None
        self.areas = []
        self.active_area = None
        self.bounds = None
        self.padding = 0.0
        self.default_padding = 0.0

        if not isinstance(camera_settings, dict):
            self.set_zoom_target(self.default_zoom)
            return

        lerp_value = camera_settings.get("lerp_factor")
        if isinstance(lerp_value, (int, float)):
            self.default_lerp = float(lerp_value)
        padding_value = camera_settings.get("padding")
        if isinstance(padding_value, (int, float)):
            self.padding = max(0.0, float(padding_value))
            self.default_padding = self.padding
        follow_value = camera_settings.get("follow_strength")
        if isinstance(follow_value, (int, float)):
            self.default_lerp = float(follow_value)
        deadzone_value = camera_settings.get("deadzone_px")
        if isinstance(deadzone_value, (int, float)):
            self.default_deadzone = max(0.0, float(deadzone_value))
        max_speed_value = camera_settings.get("max_speed")
        if isinstance(max_speed_value, (int, float)):
            self.default_max_speed = max(0.0, float(max_speed_value))

        bounds_entry = camera_settings.get("bounds")
        if isinstance(bounds_entry, dict):
            parsed_bounds = self._parse_camera_bounds(bounds_entry)
            if parsed_bounds:
                self.bounds = parsed_bounds

        zoom_config = camera_settings.get("zoom")
        if isinstance(zoom_config, dict):
            self._configure_zoom_defaults(zoom_config)
        else:
            self.set_zoom_target(self.default_zoom)

        raw_areas = camera_settings.get("areas")
        if isinstance(raw_areas, list):
            self.build_camera_areas(raw_areas)

    def _configure_zoom_defaults(self, payload: dict[str, Any]) -> None:
        initial = self._coerce_float(payload.get("initial"), self.default_zoom)
        target = self._coerce_float(payload.get("target"), initial)
        speed = self._coerce_float(payload.get("speed"), self.default_zoom_speed)
        min_zoom = self._coerce_float(payload.get("min"), self.zoom_state.min_zoom)
        max_zoom = self._coerce_float(payload.get("max"), self.zoom_state.max_zoom)
        self.default_zoom = max(0.05, initial)
        self.default_zoom_speed = max(0.01, speed)
        self.zoom_state.current = self.zoom_state.clamp(self.default_zoom)
        self.zoom_state.target = self.zoom_state.clamp(target)
        self.zoom_state.speed = self.default_zoom_speed
        self.zoom_state.min_zoom = max(0.05, min_zoom)
        self.zoom_state.max_zoom = max(self.zoom_state.min_zoom + 0.01, max_zoom)

    def _parse_camera_bounds(self, payload: dict[str, Any]) -> tuple[float, float, float, float] | None:
        try:
            left = float(payload["left"])
            right = float(payload["right"])
            bottom = float(payload["bottom"])
            top = float(payload["top"])
        except (KeyError, TypeError, ValueError):
            print("[Mesh][Camera] WARNING: bounds must include numeric left/right/top/bottom")
            return None
        if right == left or top == bottom:
            print("[Mesh][Camera] WARNING: bounds must span a positive width and height")
            return None
        return (min(left, right), min(bottom, top), max(left, right), max(bottom, top))

    def on_resize(self, width: int, height: int) -> None:
        self.resize(width, height)

    def resize(self, width: int, height: int) -> None:
        if hasattr(self.camera, "resize"):
            try:
                self.camera.resize(width, height)
                self.gui_camera.resize(width, height)
            except Exception as exc:
                if "camera_resize" not in _LOG_ONCE:
                    logger.warning("resize() failed: %s", exc, exc_info=True)
                    _LOG_ONCE.add("camera_resize")

    def start_camera_shake(
        self,
        *,
        duration: float,
        amplitude: float,
        frequency: float = 18.0,
        falloff: float = 1.0,
    ) -> None:
        state = self.shake_state
        state.timer = 0.0
        state.duration = max(0.0, float(duration))
        state.amplitude = float(amplitude)
        state.frequency = max(0.1, float(frequency))
        state.falloff = max(0.1, float(falloff))
        state.offset_x = 0.0
        state.offset_y = 0.0

    def add_camera_trauma(
        self,
        amount: float,
        *,
        decay: float | None = None,
        max_offset: float | None = None,
        frequency: float | None = None,
        seed: int | None = None,
    ) -> None:
        self.shake_state.add_trauma(
            amount,
            decay=decay,
            max_offset=max_offset,
            frequency=frequency,
            seed=seed,
        )

    def set_shake_seed(self, seed: int | None) -> None:
        self.shake_state.set_seed(seed)

    def stop_camera_shake(self) -> None:
        self.shake_state.reset()
