"""Behaviour that moves the camera toward its entity."""

from __future__ import annotations

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "CameraFollow",
    description="Moves the window camera toward the entity each frame.",
    config_fields=[
        {
            "name": "lerp_factor",
            "description": "How quickly the camera catches up to the entity",
            "type": "float",
            "default": 5.0,
        },
        {
            "name": "follow_strength",
            "description": "Alias for lerp_factor (higher = snappier follow)",
            "type": "float",
            "default": 5.0,
        },
        {
            "name": "deadzone_px",
            "description": "Pixels of deadzone before the camera moves",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "deadzone_w",
            "description": "Deadzone width in screen pixels",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "deadzone_h",
            "description": "Deadzone height in screen pixels",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "max_speed",
            "description": "Clamp camera movement speed (px/sec), 0 disables",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "padding",
            "description": "Clamp padding applied before reaching bounds",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "offset_x",
            "description": "Horizontal offset applied before following",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "offset_y",
            "description": "Vertical offset applied before following",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "zoom",
            "description": "Optional zoom override (leave unset to inherit scene)",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "zoom_speed",
            "description": "How quickly zoom eases toward its target",
            "type": "float",
            "default": 5.0,
        },
        {
            "name": "min_zoom",
            "description": "Minimum zoom clamp when overriding zoom",
            "type": "float",
            "default": 0.25,
        },
        {
            "name": "max_zoom",
            "description": "Maximum zoom clamp when overriding zoom",
            "type": "float",
            "default": 3.0,
        },
    ],
)
class CameraFollowBehaviour(Behaviour):
    """Smoothly follows the attached entity using the window camera."""

    PARAM_DEFS = {
        "lerp_factor": ParamDef(float, default=5.0, description="How quickly the camera catches up to the entity"),
        "follow_strength": ParamDef(float, default=5.0, description="Alias for lerp_factor"),
        "deadzone_px": ParamDef(float, default=0.0, description="Pixels of deadzone before the camera moves"),
        "deadzone_w": ParamDef(float, default=0.0, description="Deadzone width in screen pixels"),
        "deadzone_h": ParamDef(float, default=0.0, description="Deadzone height in screen pixels"),
        "max_speed": ParamDef(float, default=0.0, description="Clamp camera movement speed (px/sec), 0 disables"),
        "padding": ParamDef(float, default=0.0, description="Clamp padding applied before reaching bounds"),
        "offset_x": ParamDef(float, default=0.0, description="Horizontal offset applied before following"),
        "offset_y": ParamDef(float, default=0.0, description="Vertical offset applied before following"),
        "zoom": ParamDef(float, default=1.0, description="Optional zoom override (leave unset to inherit scene)"),
        "zoom_speed": ParamDef(float, default=5.0, description="How quickly zoom eases toward its target"),
        "min_zoom": ParamDef(float, default=0.25, description="Minimum zoom clamp when overriding zoom"),
        "max_zoom": ParamDef(float, default=3.0, description="Maximum zoom clamp when overriding zoom"),
    }

    def __init__(self, entity, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.lerp_factor = float(self.config.get("lerp_factor", 5.0))
        self.follow_strength = float(self.config.get("follow_strength", self.lerp_factor))
        self.deadzone_px = float(self.config.get("deadzone_px", 0.0))
        self.deadzone_w = float(self.config.get("deadzone_w", 0.0))
        self.deadzone_h = float(self.config.get("deadzone_h", 0.0))
        self.max_speed = float(self.config.get("max_speed", 0.0))
        if "follow_strength" in self._explicit_params and "lerp_factor" not in self._explicit_params:
            self.lerp_factor = self.follow_strength
        self.padding = float(self.config.get("padding", 0.0))
        self.offset_x = float(self.config.get("offset_x", 0.0))
        self.offset_y = float(self.config.get("offset_y", 0.0))
        self.zoom_speed = float(self.config.get("zoom_speed", 5.0))
        self.min_zoom = float(self.config.get("min_zoom", 0.25))
        self.max_zoom = float(self.config.get("max_zoom", 3.0))

        if "zoom" in self._explicit_params:
            self.zoom_target = self._parse_optional_float(self.config.get("zoom"))
        else:
            entity_values = getattr(entity, "mesh_entity_data", {}) or {}
            self.zoom_target = self._parse_optional_float(entity_values.get("zoom"))

    def update(self, dt: float) -> None:
        camera = getattr(self.window, "camera", None)
        if camera is None:
            print("[Mesh][CameraFollow] WARNING: Window has no camera instance")
            return

        if not self.entity:
            print("[Mesh][CameraFollow] WARNING: No entity to follow")
            return

        target_x = float(self.entity.center_x) + self.offset_x
        target_y = float(self.entity.center_y) + self.offset_y

        update_camera = getattr(self.window, "update_camera_follow", None)
        if callable(update_camera):
            update_camera(
                target_x=target_x,
                target_y=target_y,
                dt=dt,
                lerp_factor=self.lerp_factor,
                follow_strength=self.follow_strength,
                deadzone_px=self.deadzone_px,
                deadzone_w=self.deadzone_w if self.deadzone_w > 0.0 else None,
                deadzone_h=self.deadzone_h if self.deadzone_h > 0.0 else None,
                max_speed=self.max_speed if self.max_speed > 0.0 else None,
                padding=self.padding,
                zoom=self.zoom_target,
                zoom_speed=self.zoom_speed,
                min_zoom=self.min_zoom,
                max_zoom=self.max_zoom,
            )
            return

        current_x, current_y = self.window.get_camera_center()
        new_x = current_x + (target_x - current_x) * self.lerp_factor * dt
        new_y = current_y + (target_y - current_y) * self.lerp_factor * dt
        clamped_x, clamped_y = self.window.clamp_camera_to_world(new_x, new_y, padding=self.padding)

        move_to = getattr(camera, "move_to", None)
        if callable(move_to):
            move_to((clamped_x, clamped_y), 1.0)
        else:
            setattr(camera, "position", (clamped_x, clamped_y))

    @property
    def zoom(self) -> float | None:  # pragma: no cover - simple accessor
        return self.zoom_target

    @zoom.setter
    def zoom(self, value) -> None:
        self.zoom_target = self._parse_optional_float(value)

    @staticmethod
    def _parse_optional_float(value) -> float | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if stripped.lower() in {"none", "auto", "inherit"}:
                return None
            try:
                return float(stripped)
            except ValueError:
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
