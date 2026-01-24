"""Particle emitter behaviour for Mesh Engine."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .base import Behaviour, ParamDef
from .registry import register_behaviour
from ..particles_core import (
    ParticleSystem,
    RateAccumulator,
    compute_anim_frame_index,
    normalize_rect,
    sample_spawn_offset,
    spawn_radial_particles,
)

if TYPE_CHECKING:
    from arcade import Sprite

    from engine.game import GameWindow


@register_behaviour(
    "ParticleEmitter",
    description="Spawns particle bursts or continuous emissions.",
)
class ParticleEmitter(Behaviour):
    """Emits particles into the shared ParticleSystem."""
    # Example:
    # "behaviours": ["ParticleEmitter"],
    # "behaviour_config": {
    #   "ParticleEmitter": {
    #     "mode": "burst",
    #     "count": 6,
    #     "sprite": "packs/.../fx/spark.png",
    #     "rect": [0, 0, 16, 16]
    #   }
    # }
    # Frame (requires grid_cols) or frame_xy example:
    # "behaviour_config": {"ParticleEmitter": {"sprite": "packs/.../fx/spark.png", "frame": 5, "frame_size": [16,16], "grid_cols": 4}}
    # "behaviour_config": {"ParticleEmitter": {"sprite": "packs/.../fx/spark.png", "frame_xy": [2,3], "frame_size": [16,16]}}
    # "behaviour_config": {"ParticleEmitter": {"sprite": "packs/.../fx/spark.png", "additive": true}}
    # "behaviour_config": {"ParticleEmitter": {"sprite": "packs/.../fx/spark.png", "frames": [0,1,2], "frame_size": [16,16], "grid_cols": 4}}
    # "behaviour_config": {"ParticleEmitter": {"sprite": "packs/.../fx/spark.png", "frame_range": [2,5], "frame_size": [16,16], "grid_cols": 4}}
    # "behaviour_config": {"ParticleEmitter": {"sprite": "packs/.../fx/spark.png", "anim_frames": [0,1,2,3], "anim_fps": 12, "frame_size": [16,16], "grid_cols": 4}}
    # "behaviour_config": {"ParticleEmitter": {"spawn_shape": "circle", "radius": 12.0}}
    # "behaviour_config": {"ParticleEmitter": {"spawn_shape": "box", "box_size": [16, 8]}}
    # "behaviour_config": {"ParticleEmitter": {"spawn_shape": "line", "line_from": [-8, 0], "line_to": [8, 0]}}
    # "behaviour_config": {"ParticleEmitter": {"spawn_shape": "line", "line_len": 12, "line_angle_deg": 45}}
    # "behaviour_config": {"ParticleEmitter": {"alpha_curve": "ease_out", "scale_curve": "ease_in"}}
    # "behaviour_config": {"ParticleEmitter": {"preset": "spark_hit", "count": 12}}

    PARAM_DEFS = {
        "mode": ParamDef(str, default="burst", description="burst or rate"),
        "count": ParamDef(int, default=8, description="Burst particle count"),
        "rate": ParamDef(float, default=12.0, description="Particles per second"),
        "preset": ParamDef(str, default="", description="FX preset id"),
        "seed": ParamDef(str, default="", description="Optional RNG seed"),
        "emitter_id": ParamDef(str, default="", description="Stable id for per-emitter budgets"),
        "max_alive": ParamDef(int, default=0, description="Max alive particles for this emitter (0=unbounded)"),
        "offset": ParamDef(list, default=[0.0, 0.0], description="Spawn offset [x,y]"),
        "spawn_shape": ParamDef(str, default="point", description="Spawn shape: point/circle/box/line"),
        "radius": ParamDef(float, default=0.0, description="Circle radius"),
        "radius_min": ParamDef(float, default=0.0, description="Circle inner radius"),
        "radius_max": ParamDef(float, default=0.0, description="Circle outer radius"),
        "box_size": ParamDef(list, default=[], description="Box size [w,h]"),
        "line_from": ParamDef(list, default=[], description="Line start [x,y]"),
        "line_to": ParamDef(list, default=[], description="Line end [x,y]"),
        "line_len": ParamDef(float, default=0.0, description="Line length"),
        "line_angle_deg": ParamDef(float, default=0.0, description="Line angle in degrees"),
        "life_min": ParamDef(float, default=0.3, description="Min lifetime seconds"),
        "life_max": ParamDef(float, default=0.6, description="Max lifetime seconds"),
        "alpha_curve": ParamDef(str, default="linear", description="Alpha over-life curve"),
        "scale_curve": ParamDef(str, default="linear", description="Scale over-life curve"),
        "speed_min": ParamDef(float, default=1.0, description="Min speed"),
        "speed_max": ParamDef(float, default=3.0, description="Max speed"),
        "size": ParamDef(float, default=4.0, description="Circle texture size"),
        "color": ParamDef(list, default=[255, 255, 255], description="RGB(A) list"),
        "shape": ParamDef(str, default="circle", description="Generated shape"),
        "sprite": ParamDef(str, default="", description="Optional sprite texture path"),
        "rect": ParamDef(list, default=[], description="Sprite rect [x,y,w,h]"),
        "frame": ParamDef(int, default=-1, description="Sprite frame index"),
        "frame_size": ParamDef(list, default=[], description="Sprite frame size [w,h]"),
        "frame_xy": ParamDef(list, default=[], description="Sprite frame coords [col,row]"),
        "grid_cols": ParamDef(int, default=0, description="Sprite sheet columns (for frame index)"),
        "frames": ParamDef(list, default=[], description="Random frame choices"),
        "frame_range": ParamDef(list, default=[], description="Random frame range [min,max]"),
        "frame_weights": ParamDef(dict, default={}, description="Weighted frame choices {index: weight}"),
        "anim_frames": ParamDef(list, default=[], description="Animated frame sequence"),
        "anim_frame_range": ParamDef(list, default=[], description="Animated frame range [min,max]"),
        "anim_fps": ParamDef(float, default=0.0, description="Animation frames per second"),
        "anim_loop": ParamDef(bool, default=True, description="Loop animation"),
        "anim_phase": ParamDef(str, default="sync", description="Animation phase sync or random"),
        "additive": ParamDef(bool, default=False, description="Additive blend draw"),
        "scale0": ParamDef(float, default=1.0, description="Start scale"),
        "scale1": ParamDef(float, default=0.0, description="End scale"),
        "alpha0": ParamDef(float, default=255.0, description="Start alpha"),
        "alpha1": ParamDef(float, default=0.0, description="End alpha"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config: Any) -> None:
        raw_config = _resolve_raw_config(entity, config)
        merged_config = _apply_preset_config(raw_config, entity, window)
        errors = validate_particle_emitter_config(merged_config, allow_preset=True)
        if errors:
            raise ValueError(errors[0])
        super().__init__(entity, window, **merged_config)
        self._mode = _coerce_mode(self.mode)
        self._count = max(0, int(self.count))
        self._rate = float(self.rate)
        self._offset = _coerce_offset(self.offset)
        self._spawn_cfg = _resolve_spawn_shape_config(self.config)
        self._life_min, self._life_max = _coerce_range(self.life_min, self.life_max, 0.1, 0.2)
        self._speed_min, self._speed_max = _coerce_range(self.speed_min, self.speed_max, 0.0, 0.0)
        self._alpha_curve = _coerce_curve(self.alpha_curve)
        self._scale_curve = _coerce_curve(self.scale_curve)
        self._size = max(0.0, float(self.size))
        self._color = _coerce_color(self.color)
        self._shape = str(self.shape or "circle")
        self._sprite_path = _coerce_sprite_path(self.sprite)
        if self._sprite_path is None:
            self._sprite_path = _coerce_sprite_path(self.config.get("sprite_path"))
        anim_config = _resolve_animation_config(self.config, self._sprite_path)
        if anim_config is not None:
            (
                self._anim_frames,
                self._anim_fps,
                self._anim_loop,
                self._anim_phase,
                self._anim_frame_size,
                self._anim_grid_cols,
            ) = anim_config
            self._sprite_rect = None
            self._random_frame_picker = None
        else:
            self._anim_frames = None
            self._anim_fps = None
            self._anim_loop = True
            self._anim_phase = "sync"
            self._anim_frame_size = None
            self._anim_grid_cols = None
            self._sprite_rect, self._random_frame_picker = _resolve_sprite_frame_config(
                self.config,
                self._sprite_path,
            )
        self._additive = bool(self.additive)
        self._scale0 = float(self.scale0)
        self._scale1 = float(self.scale1)
        self._alpha0 = float(self.alpha0)
        self._alpha1 = float(self.alpha1)
        self._max_alive = int(self.max_alive) if int(self.max_alive) > 0 else 0
        self._emitter_id = self._resolve_emitter_id(self.emitter_id)
        self._rng = random.Random(_coerce_optional_int(self.seed))
        self._rate_accum = RateAccumulator()
        self._burst_fired = False

    def update(self, dt: float) -> None:
        system = _resolve_particle_system(self.window)
        if system is None:
            return
        if dt <= 0.0:
            return

        desired = 0
        if self._mode == "rate":
            desired = self._rate_accum.step(self._rate, dt)
        else:
            if self._burst_fired:
                return
            desired = self._count

        if desired <= 0:
            return

        allowed = self._apply_emitter_cap(system, desired)
        if self._mode == "rate" and allowed < desired:
            self._rate_accum.spawn_accum += desired - allowed
        if allowed <= 0:
            return
        if self._mode == "burst":
            self._burst_fired = True

        base_x = float(getattr(self.entity, "center_x", 0.0)) + self._offset[0]
        base_y = float(getattr(self.entity, "center_y", 0.0)) + self._offset[1]

        particles = spawn_radial_particles(
            self._rng,
            count=allowed,
            x=base_x,
            y=base_y,
            speed_min=self._speed_min,
            speed_max=self._speed_max,
            life_min=self._life_min,
            life_max=self._life_max,
            size=self._size,
            color=self._color,
            scale0=self._scale0,
            scale1=self._scale1,
            alpha0=self._alpha0,
            alpha1=self._alpha1,
            shape=self._shape,
            sprite_path=self._sprite_path,
            sprite_rect=self._sprite_rect,
            additive=self._additive,
            emitter_id=self._emitter_id,
        )
        if self._spawn_cfg.get("shape") != "point":
            for particle in particles:
                dx, dy = sample_spawn_offset(self._rng, self._spawn_cfg)
                particle.x += dx
                particle.y += dy
        for particle in particles:
            particle.alpha_curve = self._alpha_curve
            particle.scale_curve = self._scale_curve
        if self._anim_frames is not None:
            self._apply_animation_metadata(particles)
        elif self._random_frame_picker is not None:
            for particle in particles:
                frame = self._random_frame_picker.pick(self._rng)
                particle.sprite_rect = _frame_index_to_rect(frame, self._random_frame_picker.frame_size, self._random_frame_picker.grid_cols)
        system.spawn(particles)

    def _apply_animation_metadata(self, particles: list[Any]) -> None:
        if not particles or self._anim_frames is None:
            return
        for particle in particles:
            particle.anim_frames = self._anim_frames
            particle.anim_fps = self._anim_fps
            particle.anim_loop = self._anim_loop
            particle.frame_size = self._anim_frame_size
            particle.grid_cols = self._anim_grid_cols
            if self._anim_phase == "random":
                particle.anim_phase_offset = self._rng.randrange(len(self._anim_frames))
            else:
                particle.anim_phase_offset = 0
            idx = compute_anim_frame_index(particle)
            if idx is None:
                continue
            frame = self._anim_frames[idx]
            particle.sprite_rect = _frame_index_to_rect(frame, self._anim_frame_size, self._anim_grid_cols)

    def _apply_emitter_cap(self, system: ParticleSystem, desired: int) -> int:
        if self._max_alive <= 0:
            return desired
        alive = system.count_alive(self._emitter_id)
        remaining = self._max_alive - alive
        if remaining <= 0:
            return 0
        return min(desired, remaining)

    def _resolve_emitter_id(self, raw: str) -> str:
        if raw and str(raw).strip():
            return str(raw).strip()
        data = getattr(self.entity, "mesh_entity_data", {}) or {}
        for key in ("id", "entity_id", "mesh_id", "uuid", "guid", "name"):
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        name = getattr(self.entity, "mesh_name", None)
        if name:
            return str(name)
        return f"emitter:{id(self.entity)}"


def _resolve_particle_system(window: Any) -> ParticleSystem | None:
    manager = getattr(window, "particle_manager", None)
    if manager is not None:
        system = getattr(manager, "system", None)
        if isinstance(system, ParticleSystem):
            return system
    system = getattr(window, "particle_system", None)
    if isinstance(system, ParticleSystem):
        return system
    return None


def validate_particle_emitter_config(config: dict[str, Any], *, allow_preset: bool = True) -> list[str]:
    if not isinstance(config, dict):
        return ["config must be an object"]

    errors: list[str] = []

    if not allow_preset and _coerce_preset_name(config.get("preset")) is not None:
        errors.append("preset is not allowed in presets")

    try:
        _resolve_spawn_shape_config(config)
    except ValueError as exc:
        errors.append(str(exc))

    for key in ("alpha_curve", "scale_curve"):
        try:
            _coerce_curve(config.get(key))
        except ValueError as exc:
            errors.append(str(exc))

    sprite_path = _coerce_sprite_path(config.get("sprite"))
    if sprite_path is None:
        sprite_path = _coerce_sprite_path(config.get("sprite_path"))

    anim_error = False
    try:
        anim_config = _resolve_animation_config(config, sprite_path)
    except ValueError as exc:
        errors.append(str(exc))
        anim_config = None
        anim_error = True

    if anim_config is None and not anim_error:
        try:
            _resolve_sprite_frame_config(config, sprite_path)
        except ValueError as exc:
            errors.append(str(exc))

    return errors


def _resolve_raw_config(entity: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    data = getattr(entity, "mesh_entity_data", None)
    if isinstance(data, dict):
        cfg_root = data.get("behaviour_config")
        if isinstance(cfg_root, dict):
            raw = cfg_root.get("ParticleEmitter")
            if isinstance(raw, dict):
                return dict(raw)
    return dict(fallback or {})


def _apply_preset_config(config: dict[str, Any], entity: Any, window: Any) -> dict[str, Any]:
    preset_name = _coerce_preset_name(config.get("preset"))
    if preset_name is None:
        return dict(config)
    registry = _resolve_fx_preset_registry(window)
    if registry is None:
        raise ValueError(f"ParticleEmitter preset '{preset_name}' requires fx preset registry")
    context_pack_id = _resolve_context_pack_id(window, entity)
    preset_config = registry.resolve(preset_name, context_pack_id=context_pack_id)
    if "preset" in preset_config:
        raise ValueError(f"Preset '{preset_name}' may not include 'preset'")
    merged = dict(preset_config)
    for key, value in config.items():
        if key == "preset":
            continue
        merged[key] = value
    merged["preset"] = preset_name
    return merged


def _resolve_fx_preset_registry(window: Any) -> Any:
    registry = getattr(window, "fx_presets", None)
    if registry is None:
        return None
    if hasattr(registry, "resolve"):
        return registry
    return None


def _resolve_context_pack_id(window: Any, entity: Any) -> str | None:
    data = getattr(entity, "mesh_entity_data", None)
    if isinstance(data, dict):
        pack_id = data.get("pack_id")
        if isinstance(pack_id, str) and pack_id.strip():
            return pack_id.strip()
    scene_controller = getattr(window, "scene_controller", None)
    scene_path = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None
    return _infer_pack_id_from_path(scene_path)


def _infer_pack_id_from_path(path: Any) -> str | None:
    if not isinstance(path, str):
        return None
    value = path.strip()
    if not value:
        return None
    parts = Path(value).parts
    for idx, part in enumerate(parts):
        if part.lower() == "packs" and idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            return int(value)
        except ValueError:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_mode(mode: Any) -> str:
    value = str(mode or "burst").strip().lower()
    if value not in {"burst", "rate"}:
        return "burst"
    return value


def _coerce_offset(raw: Any) -> tuple[float, float]:
    if isinstance(raw, dict):
        return (float(raw.get("x", 0.0)), float(raw.get("y", 0.0)))
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return (float(raw[0]), float(raw[1]))
    return (0.0, 0.0)


def _coerce_range(min_value: Any, max_value: Any, fallback_min: float, fallback_max: float) -> tuple[float, float]:
    try:
        min_val = float(min_value)
    except (TypeError, ValueError):
        min_val = fallback_min
    try:
        max_val = float(max_value)
    except (TypeError, ValueError):
        max_val = fallback_max
    if max_val < min_val:
        min_val, max_val = max_val, min_val
    return min_val, max_val


def _coerce_color(raw: Any) -> tuple[int, int, int, int]:
    if isinstance(raw, dict):
        values = [raw.get("r", 255), raw.get("g", 255), raw.get("b", 255), raw.get("a", 255)]
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = [255, 255, 255, 255]
    if len(values) >= 4:
        r, g, b, a = values[:4]
    elif len(values) >= 3:
        r, g, b = values[:3]
        a = 255
    else:
        r, g, b, a = 255, 255, 255, 255
    return (int(r), int(g), int(b), int(a))


def _coerce_sprite_path(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    return value if value else None


def _coerce_preset_name(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    return value if value else None


def _resolve_sprite_frame_config(
    config: dict[str, Any],
    sprite_path: str | None,
) -> tuple[tuple[int, int, int, int] | None, "_RandomFramePicker | None"]:
    if not sprite_path:
        return None, None
    direct = normalize_rect(config.get("rect"))
    if direct is not None:
        _ensure_no_random_frame_config(config)
        return direct, None

    frame_size = _coerce_frame_size(config.get("frame_size"))
    frame_xy = _coerce_frame_xy(config.get("frame_xy"))
    if frame_xy is not None:
        _ensure_no_random_frame_config(config)
        if frame_size is None:
            raise ValueError("frame_xy requires frame_size")
        col, row = frame_xy
        w, h = frame_size
        return (col * w, row * h, w, h), None

    frame = _coerce_non_negative_int(config.get("frame"))
    if frame is not None:
        _ensure_no_random_frame_config(config)
        grid_cols = _coerce_positive_int(config.get("grid_cols"))
        if frame_size is None or grid_cols is None:
            raise ValueError("frame requires frame_size and grid_cols")
        return _frame_index_to_rect(frame, frame_size, grid_cols), None

    random_picker = _resolve_random_frame_picker(config)
    return None, random_picker


def _resolve_random_frame_picker(config: dict[str, Any]) -> "_RandomFramePicker | None":
    frames = _coerce_frame_list(config.get("frames"))
    frame_range = _coerce_frame_range(config.get("frame_range"))
    weights = _coerce_frame_weights(config.get("frame_weights"))
    if frames is None and frame_range is None and weights is None:
        return None

    if sum(value is not None for value in (frames, frame_range, weights)) > 1:
        raise ValueError("frames, frame_range, and frame_weights are mutually exclusive")

    frame_size = _coerce_frame_size(config.get("frame_size"))
    grid_cols = _coerce_positive_int(config.get("grid_cols"))
    if frame_size is None or grid_cols is None:
        raise ValueError("random frames require frame_size and grid_cols")

    if weights is not None:
        return _RandomFramePicker.from_weights(weights, frame_size, grid_cols)
    if frames is not None:
        return _RandomFramePicker.from_frames(frames, frame_size, grid_cols)
    if frame_range is not None:
        return _RandomFramePicker.from_range(frame_range, frame_size, grid_cols)
    return None


def _resolve_animation_config(
    config: dict[str, Any],
    sprite_path: str | None,
) -> tuple[tuple[int, ...], float, bool, str, tuple[int, int], int] | None:
    raw_frames = config.get("anim_frames")
    if isinstance(raw_frames, (list, tuple)) and len(raw_frames) == 0:
        raw_frames = None
    raw_range = config.get("anim_frame_range")
    if isinstance(raw_range, (list, tuple)) and len(raw_range) == 0:
        raw_range = None
    if raw_frames is None and raw_range is None:
        return None
    if not sprite_path:
        raise ValueError("anim_frames requires sprite")
    if raw_frames is not None and raw_range is not None:
        raise ValueError("anim_frames and anim_frame_range are mutually exclusive")
    _ensure_no_fixed_frame_config(config)

    if raw_frames is not None:
        frames = _coerce_anim_frames(raw_frames)
    else:
        frames = _expand_anim_range(_coerce_anim_frame_range(raw_range))

    fps = _coerce_positive_float(config.get("anim_fps"))
    if fps is None:
        raise ValueError("anim_fps must be > 0 when using anim_frames")
    frame_size = _coerce_frame_size(config.get("frame_size"))
    grid_cols = _coerce_positive_int(config.get("grid_cols"))
    if frame_size is None or grid_cols is None:
        raise ValueError("anim_frames require frame_size and grid_cols")
    loop = bool(config.get("anim_loop", True))
    phase = _coerce_anim_phase(config.get("anim_phase"))
    return (tuple(frames), float(fps), loop, phase, frame_size, int(grid_cols))


def _ensure_no_random_frame_config(config: dict[str, Any]) -> None:
    if _coerce_frame_list(config.get("frames")) is not None:
        raise ValueError("frames is mutually exclusive with rect/frame/frame_xy")
    if _coerce_frame_range(config.get("frame_range")) is not None:
        raise ValueError("frame_range is mutually exclusive with rect/frame/frame_xy")
    if _coerce_frame_weights(config.get("frame_weights")) is not None:
        raise ValueError("frame_weights is mutually exclusive with rect/frame/frame_xy")


def _ensure_no_fixed_frame_config(config: dict[str, Any]) -> None:
    if normalize_rect(config.get("rect")) is not None:
        raise ValueError("rect is mutually exclusive with anim_frames")
    if _coerce_frame_xy(config.get("frame_xy")) is not None:
        raise ValueError("frame_xy is mutually exclusive with anim_frames")
    if _coerce_non_negative_int(config.get("frame")) is not None:
        raise ValueError("frame is mutually exclusive with anim_frames")


def _coerce_frame_size(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        w = int(raw[0])
        h = int(raw[1])
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (w, h)


def _coerce_frame_xy(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        col = int(raw[0])
        row = int(raw[1])
    except (TypeError, ValueError):
        return None
    if col < 0 or row < 0:
        return None
    return (col, row)


def _coerce_non_negative_int(raw: Any) -> int | None:
    value = _coerce_optional_int(raw)
    if value is None:
        return None
    return value if value >= 0 else None


def _coerce_positive_int(raw: Any) -> int | None:
    value = _coerce_optional_int(raw)
    if value is None:
        return None
    return value if value > 0 else None


def _resolve_spawn_shape_config(config: dict[str, Any]) -> dict[str, Any]:
    shape = _coerce_spawn_shape(config.get("spawn_shape"))
    if shape == "point":
        return {"shape": "point"}
    if shape == "circle":
        radius = _coerce_positive_float(config.get("radius"))
        radius_min = _coerce_non_negative_float(config.get("radius_min"))
        radius_max = _coerce_non_negative_float(config.get("radius_max"))
        if radius is not None:
            if (radius_min or 0.0) > 0.0 or (radius_max or 0.0) > 0.0:
                raise ValueError("radius is mutually exclusive with radius_min/radius_max")
            return {"shape": "circle", "radius_min": 0.0, "radius_max": radius}
        if radius_min is None or radius_max is None:
            raise ValueError("circle spawn_shape requires radius or radius_min/radius_max")
        if radius_max <= 0.0:
            raise ValueError("circle radius_max must be > 0")
        if radius_min < 0.0:
            raise ValueError("circle radius_min must be >= 0")
        if radius_min > radius_max:
            raise ValueError("circle radius_min must be <= radius_max")
        return {"shape": "circle", "radius_min": radius_min, "radius_max": radius_max}
    if shape == "box":
        box = _coerce_vector2(config.get("box_size"))
        if box is None:
            raise ValueError("box spawn_shape requires box_size [w,h]")
        w, h = box
        if w <= 0.0 or h <= 0.0:
            raise ValueError("box_size must be positive")
        return {"shape": "box", "box_w": w, "box_h": h}
    if shape == "line":
        line_from = _coerce_vector2(config.get("line_from"))
        line_to = _coerce_vector2(config.get("line_to"))
        line_len = _coerce_positive_float(config.get("line_len"))
        angle_deg = _coerce_optional_float(config.get("line_angle_deg"))
        if line_from is not None or line_to is not None:
            if line_len is not None and line_len > 0.0:
                raise ValueError("line_from/line_to is mutually exclusive with line_len/line_angle_deg")
            if line_from is None or line_to is None:
                raise ValueError("line_from and line_to must both be provided")
            return {"shape": "line", "line_from": line_from, "line_to": line_to}
        if line_len is None or line_len <= 0.0:
            raise ValueError("line spawn_shape requires line_from/line_to or line_len")
        angle = math.radians(angle_deg or 0.0)
        line_to = (math.cos(angle) * line_len, math.sin(angle) * line_len)
        return {"shape": "line", "line_from": (0.0, 0.0), "line_to": line_to}
    raise ValueError(f"Unknown spawn_shape '{shape}'")


def _coerce_spawn_shape(raw: Any) -> str:
    value = str(raw or "point").strip().lower()
    if value not in {"point", "circle", "box", "line"}:
        return "point"
    return value


def _coerce_vector2(raw: Any) -> tuple[float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return (float(raw[0]), float(raw[1]))
    except (TypeError, ValueError):
        return None


def _coerce_optional_float(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _coerce_non_negative_float(raw: Any) -> float | None:
    value = _coerce_optional_float(raw)
    if value is None:
        return None
    if value < 0:
        raise ValueError("value must be >= 0")
    return value


def _coerce_curve(raw: Any) -> str:
    value = str(raw or "linear").strip().lower()
    if value not in {"linear", "ease_in", "ease_out", "ease_in_out"}:
        raise ValueError(f"Unknown curve '{raw}'")
    return value


def _coerce_frame_list(raw: Any) -> list[int] | None:
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    frames: list[int] = []
    for entry in raw:
        value = _coerce_non_negative_int(entry)
        if value is None:
            raise ValueError("frames must be non-negative integers")
        frames.append(value)
    if not frames:
        raise ValueError("frames must be non-empty")
    return frames


def _coerce_frame_range(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    start = _coerce_non_negative_int(raw[0])
    end = _coerce_non_negative_int(raw[1])
    if start is None or end is None:
        raise ValueError("frame_range must be [min,max] non-negative integers")
    if start > end:
        raise ValueError("frame_range min must be <= max")
    return (start, end)


def _coerce_anim_frames(raw: Any) -> list[int]:
    frames = _coerce_frame_list(raw)
    if frames is None:
        raise ValueError("anim_frames must be a non-empty list")
    return frames


def _coerce_anim_frame_range(raw: Any) -> tuple[int, int]:
    frame_range = _coerce_frame_range(raw)
    if frame_range is None:
        raise ValueError("anim_frame_range must be [min,max]")
    return frame_range


def _expand_anim_range(frame_range: tuple[int, int]) -> list[int]:
    start, end = frame_range
    return list(range(start, end + 1))


def _coerce_positive_float(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _coerce_anim_phase(raw: Any) -> str:
    value = str(raw or "sync").strip().lower()
    if value not in {"sync", "random"}:
        return "sync"
    return value


def _coerce_frame_weights(raw: Any) -> dict[int, float] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    weights: dict[int, float] = {}
    for key, value in raw.items():
        frame = _coerce_non_negative_int(key)
        if frame is None:
            raise ValueError("frame_weights keys must be non-negative integers")
        try:
            weight = float(value)
        except (TypeError, ValueError):
            raise ValueError("frame_weights values must be numeric") from None
        if weight <= 0:
            raise ValueError("frame_weights values must be > 0")
        weights[frame] = weight
    if not weights:
        raise ValueError("frame_weights must be non-empty")
    return weights


def _frame_index_to_rect(frame: int, frame_size: tuple[int, int], grid_cols: int) -> tuple[int, int, int, int]:
    w, h = frame_size
    col = frame % grid_cols
    row = frame // grid_cols
    return (col * w, row * h, w, h)


class _RandomFramePicker:
    def __init__(
        self,
        *,
        frames: list[int] | None,
        frame_range: tuple[int, int] | None,
        weights: list[tuple[int, float]] | None,
        frame_size: tuple[int, int],
        grid_cols: int,
    ) -> None:
        self.frames = frames
        self.frame_range = frame_range
        self.weights = weights
        self.frame_size = frame_size
        self.grid_cols = grid_cols
        if weights:
            total = sum(weight for _, weight in weights)
            if total <= 0:
                raise ValueError("frame_weights total must be > 0")
            self._weight_total = total
        else:
            self._weight_total = 0.0

    @classmethod
    def from_frames(cls, frames: list[int], frame_size: tuple[int, int], grid_cols: int) -> "_RandomFramePicker":
        return cls(frames=frames, frame_range=None, weights=None, frame_size=frame_size, grid_cols=grid_cols)

    @classmethod
    def from_range(cls, frame_range: tuple[int, int], frame_size: tuple[int, int], grid_cols: int) -> "_RandomFramePicker":
        return cls(frames=None, frame_range=frame_range, weights=None, frame_size=frame_size, grid_cols=grid_cols)

    @classmethod
    def from_weights(cls, weights: dict[int, float], frame_size: tuple[int, int], grid_cols: int) -> "_RandomFramePicker":
        ordered = sorted(weights.items(), key=lambda item: item[0])
        return cls(frames=None, frame_range=None, weights=ordered, frame_size=frame_size, grid_cols=grid_cols)

    def pick(self, rng: random.Random) -> int:
        if self.weights is not None:
            target = rng.random() * self._weight_total
            acc = 0.0
            for frame, weight in self.weights:
                acc += weight
                if target <= acc:
                    return frame
            return self.weights[-1][0]
        if self.frames is not None:
            return rng.choice(self.frames)
        if self.frame_range is not None:
            start, end = self.frame_range
            return rng.randrange(start, end + 1)
        return 0
