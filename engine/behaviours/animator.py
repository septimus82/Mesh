"""Simple sprite animation behaviour."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from .base import Behaviour, ParamDef
from .registry import register_behaviour

if TYPE_CHECKING:  # pragma: no cover - typing only
    import arcade


@register_behaviour(
    "Animator",
    description="Cycles sprite textures using named animation states.",
    config_fields=[
        {
            "name": "animations",
            "description": "Mapping of state name to a list of texture paths",
            "type": "string",
            "default": {},
        },
        {
            "name": "animation_state",
            "description": "Initial animation state to play",
            "type": "string",
            "default": "idle",
        },
        {
            "name": "animation_frame_rate",
            "description": "Frames per second for the active animation",
            "type": "float",
            "default": 8.0,
        },
        {
            "name": "enable_auto_state",
            "description": "Automatically switch idle/walk based on movement",
            "type": "bool",
            "default": False,
        },
        {
            "name": "idle_clip",
            "description": "Clip to use when speed is below threshold",
            "type": "string",
            "default": "idle",
        },
        {
            "name": "walk_clip",
            "description": "Clip to use when speed is above threshold",
            "type": "string",
            "default": "walk",
        },
        {
            "name": "speed_threshold",
            "description": "Minimum speed to consider the entity moving",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "override_duration",
            "description": "Default duration (seconds) for temporary state overrides",
            "type": "float",
            "default": 0.2,
        },
        {
            "name": "directional_mode",
            "description": "Direction handling: 'none' or '4-way' for directional idle/walk clips",
            "type": "string",
            "default": "none",
        },
        {
            "name": "facing_default",
            "description": "Initial facing direction (up/down/left/right) used with directional_mode",
            "type": "string",
            "default": "down",
        },
    ],
)
class SpriteAnimatorBehaviour(Behaviour):
    """Cycles through sprite textures based on animation state."""

    PARAM_DEFS = {
        "animations": ParamDef(dict, default={}, description="Mapping of state name to a list of texture paths"),
        "animation_state": ParamDef(str, default="idle", description="Initial animation state to play"),
        "animation_frame_rate": ParamDef(float, default=8.0, description="Frames per second for the active animation"),
        "enable_auto_state": ParamDef(bool, default=False, description="Auto idle/walk switching based on movement"),
        "idle_clip": ParamDef(str, default="idle", description="Clip to use when idle"),
        "walk_clip": ParamDef(str, default="walk", description="Clip to use when moving"),
        "speed_threshold": ParamDef(float, default=1.0, description="Speed threshold for walk detection"),
        "override_duration": ParamDef(float, default=0.2, description="Default duration for state overrides"),
        "directional_mode": ParamDef(str, default="none", description="Direction handling: none or 4-way"),
        "facing_default": ParamDef(str, default="down", description="Initial facing direction"),
    }

    def __init__(self, entity, window, **config) -> None:
        super().__init__(entity, window, **config)

        raw_animations = self.config.get("animations") or {}
        self.animations: Dict[str, List[arcade.Texture]] = {}
        self.animation_configs: Dict[str, dict] = {}

        for name, definition in raw_animations.items():
            textures: List[arcade.Texture] = []

            # Case 1: List of paths (Legacy)
            if isinstance(definition, list):
                for frame_path in definition:
                    t = window.assets.get_texture(frame_path)
                    if t:
                        textures.append(t)
                default_fps = float(self.config.get("animation_frame_rate", 8.0))
                self.animation_configs[name] = {"fps": default_fps, "mode": "loop"}

            # Case 2: Sprite sheet definition
            elif isinstance(definition, dict):
                sheet_path = definition.get("sheet")
                if sheet_path:
                    # Sprite sheet mode
                    try:
                        # We need frame dimensions. If not provided, we might be in trouble or need to guess.
                        # For now, require them or assume square if only one dim provided?
                        # Let's assume the user provides frame_width/height or we fail.
                        # Actually, let's look for 'frame_width' and 'frame_height' in the definition.
                        # If not found, maybe we can infer from 'cols'/'rows' if we load the full image first?
                        # For simplicity, let's require frame_width/height in the JSON for now.

                        # Wait, arcade.load_spritesheet arguments: file_name, sprite_width, sprite_height, sprite_count, columns, margin
                        # My asset manager wrapper: path, frame_width, frame_height, total_frames, start_frame

                        fw = definition.get("frame_width") or definition.get("width") or 32
                        fh = definition.get("frame_height") or definition.get("height") or 32
                        count = definition.get("frames", 1)
                        start = definition.get("start", 0)

                        textures = window.assets.load_sprite_sheet(sheet_path, fw, fh, count, start)
                    except Exception as e:
                        print(f"[Mesh][Animator] Failed to load sheet for '{name}': {e}")
                else:
                    # Maybe explicit list of frames in a dict?
                    # "idle": { "frames": ["path1", "path2"], "fps": 10 }
                    frames = definition.get("frames")
                    if isinstance(frames, list):
                        for frame_path in frames:
                            t = window.assets.get_texture(frame_path)
                            if t:
                                textures.append(t)

                # Store config
                self.animation_configs[name] = {
                    "fps": float(definition.get("fps", self.config.get("animation_frame_rate", 8.0))),
                    "mode": definition.get("mode", "loop"),
                    "next": definition.get("next"), # For 'once' mode, what to play next
                }

            if textures:
                self.animations[name] = textures

        if not self.animations:
            # print("[Mesh][Behaviour:Animator] WARNING: No valid animations provided")
            # Don't disable, maybe they will be added later? But for now, yes.
            self._disabled = True
            return

        self.current_state: str = self.config.get("animation_state") or next(iter(self.animations))
        if self.current_state not in self.animations:
            self.current_state = next(iter(self.animations))

        self.timer: float = 0.0
        self.frame_index: int = 0
        self._disabled = False
        self._finished = False
        self._ping_direction: int = 1

        self._auto_state_enabled = bool(self.config.get("enable_auto_state", False))
        self._idle_clip = str(self.config.get("idle_clip", "idle") or "idle")
        self._walk_clip = str(self.config.get("walk_clip", "walk") or "walk")
        self._speed_threshold = float(self.config.get("speed_threshold", 1.0) or 0.0)
        self._override_default_duration = float(self.config.get("override_duration", 0.2) or 0.0)
        self._current_clip_name: str | None = self.current_state
        self._override_state: str | None = None
        self._override_clip: str | None = None
        self._override_timer: float = 0.0
        self._directional_mode = str(self.config.get("directional_mode", "none") or "none").lower()
        facing_default = str(self.config.get("facing_default", "down") or "down").lower()
        self._facing = facing_default if facing_default in {"up", "down", "left", "right"} else "down"

        self._apply_frame()

    def pre_update(self, dt: float) -> None:
        """Check for state changes requested by other behaviours."""
        if self._disabled:
            return

        data = getattr(self.entity, "mesh_entity_data", {}) or {}
        desired_state = data.get("animation_state")

        if desired_state and desired_state in self.animations and desired_state != self.current_state:
            self.play(desired_state)

    def update(self, dt: float) -> None:
        if self._disabled:
            return

        if self._override_clip and self._override_timer > 0.0:
            self._override_timer -= dt
            if self._override_timer > 0.0:
                self._set_clip_if_changed(self._override_clip)
                return
            self._override_clip = None
            self._override_state = None
            self._override_timer = 0.0

        if self._auto_state_enabled:
            vx = getattr(self.entity, "change_x", 0.0)
            vy = getattr(self.entity, "change_y", 0.0)
            speed = (vx * vx + vy * vy) ** 0.5
            target_clip = self._resolve_directional_clip(speed > self._speed_threshold)
            self._set_clip_if_changed(target_clip)

        config = self.animation_configs.get(self.current_state, {})
        fps = config.get("fps", 8.0)
        mode = config.get("mode", "loop")

        if fps <= 0:
            return

        self.timer += dt
        frame_time = 1.0 / fps

        frames = self.animations[self.current_state]
        total_frames = len(frames)

        if self.timer >= frame_time:
            self.timer -= frame_time

            if mode == "loop":
                self.frame_index = (self.frame_index + 1) % total_frames
            elif mode == "once":
                if self.frame_index < total_frames - 1:
                    self.frame_index += 1
                else:
                    self._finished = True
                    # Check if we should transition
                    next_anim = config.get("next")
                    if next_anim and next_anim in self.animations:
                        self.play(next_anim)
            elif mode == "ping-pong":
                if total_frames <= 1:
                    self.frame_index = 0
                    self._ping_direction = 0
                else:
                    next_index = self.frame_index + self._ping_direction
                    if next_index >= total_frames:
                        self._ping_direction = -1
                        next_index = max(0, total_frames - 2)
                    elif next_index < 0:
                        self._ping_direction = 1
                        next_index = 1 if total_frames > 1 else 0
                    self.frame_index = next_index

    def late_update(self, dt: float) -> None:
        """Apply the current frame to the sprite."""
        if self._disabled:
            return
        self._apply_frame()

    def play(self, state_name: str, force: bool = False) -> None:
        if state_name not in self.animations:
            return

        if self.current_state == state_name and not force and not self._finished:
            return

        self.current_state = state_name
        self.frame_index = 0
        self.timer = 0.0
        self._finished = False
        self._ping_direction = 1

        # Update entity data to reflect reality
        data = getattr(self.entity, "mesh_entity_data", {})
        if isinstance(data, dict):
            data["animation_state"] = state_name

    def _set_clip_if_changed(self, clip_name: str) -> None:
        if not clip_name:
            return
        if self.current_state == clip_name:
            return
        self.play(clip_name, force=True)
        self._current_clip_name = clip_name

    def _resolve_directional_clip(self, moving: bool) -> str:
        base = self._walk_clip if moving else self._idle_clip
        if self._directional_mode != "4-way":
            return base
        clip_name = f"{'walk' if moving else 'idle'}_{self._facing}"
        if clip_name in self.animations:
            return clip_name
        return base

    def set_facing(self, facing: str) -> None:
        facing_norm = str(facing or "").lower()
        if facing_norm not in {"up", "down", "left", "right"}:
            return
        self._facing = facing_norm

    def request_state_override(
        self,
        state_name: str,
        clip_name: str | None = None,
        duration: float | None = None,
    ) -> None:
        """Request a temporary animation state override."""
        if not state_name:
            return
        clip = clip_name or state_name
        if duration is None:
            duration = self._override_default_duration
        if duration is None or duration <= 0:
            self._override_state = None
            self._override_clip = None
            self._override_timer = 0.0
            self._set_clip_if_changed(clip)
            return
        self._override_state = state_name
        self._override_clip = clip
        self._override_timer = float(duration)

    def _apply_frame(self) -> None:
        textures = self.animations.get(self.current_state)
        if not textures:
            return

        idx = max(0, min(self.frame_index, len(textures) - 1))
        self.entity.texture = textures[idx]
