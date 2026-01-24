from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

_DEFAULT_DT = 1.0 / 60.0


@dataclass(slots=True)
class ParticleData:
    x: float
    y: float
    vx: float
    vy: float
    age: float = 0.0
    life: float = 1.0
    scale0: float = 1.0
    scale1: float = 1.0
    alpha0: float = 255.0
    alpha1: float = 0.0
    alpha_curve: str = "linear"
    color: tuple[int, int, int] | tuple[int, int, int, int] | None = None
    shape: str | None = "circle"
    size: float = 4.0
    sprite_path: str | None = None
    sprite_rect: tuple[int, int, int, int] | None = None
    additive: bool = False
    anim_frames: tuple[int, ...] | None = None
    anim_fps: float | None = None
    anim_loop: bool = True
    anim_phase_offset: int = 0
    frame_size: tuple[int, int] | None = None
    grid_cols: int | None = None
    scale_curve: str = "linear"
    alpha_now: float = 255.0
    scale_now: float = 1.0
    emitter_id: str | None = None
    gravity_x: float = 0.0
    gravity_y: float = 0.0
    drag: float = 0.0


def appearance_key(particle: ParticleData) -> tuple[Any, ...]:
    sprite_path = particle.sprite_path
    if sprite_path:
        return ("sprite", str(sprite_path), particle.sprite_rect)
    shape = str(particle.shape or "circle")
    size = float(particle.size or 0.0)
    color = _normalize_color(particle.color)
    return ("shape", shape, size, color)


class ParticleSystem:
    def __init__(self, max_particles: int = 2000) -> None:
        self.max_particles = int(max_particles)
        self.particles: list[ParticleData] = []
        self.spawned_this_frame = 0
        self.dropped_this_frame = 0
        self.dropped_total = 0

    @property
    def alive_count(self) -> int:
        return len(self.particles)

    def reset_frame_counters(self) -> None:
        self.spawned_this_frame = 0
        self.dropped_this_frame = 0

    def clear(self) -> None:
        self.particles.clear()

    def spawn(self, particles: list[ParticleData]) -> int:
        spawned = 0
        if not particles:
            return 0

        available = self.max_particles - len(self.particles)
        if available <= 0:
            dropped = len(particles)
            self.dropped_this_frame += dropped
            self.dropped_total += dropped
            return 0

        for particle in particles:
            if len(self.particles) >= self.max_particles:
                self.dropped_this_frame += 1
                self.dropped_total += 1
                continue
            particle.alpha_now = float(particle.alpha0)
            particle.scale_now = float(particle.scale0)
            self.particles.append(particle)
            spawned += 1

        self.spawned_this_frame += spawned
        return spawned

    def update(self, dt: float | None = None) -> None:
        dt_value = _coerce_dt(dt)
        frame_scale = dt_value * 60.0
        if frame_scale <= 0.0:
            return

        alive: list[ParticleData] = []
        for particle in self.particles:
            if particle.life <= 0:
                continue

            if particle.gravity_x or particle.gravity_y:
                particle.vx += particle.gravity_x * frame_scale
                particle.vy += particle.gravity_y * frame_scale

            if particle.drag:
                drag_factor = max(0.0, 1.0 - particle.drag * frame_scale)
                particle.vx *= drag_factor
                particle.vy *= drag_factor

            particle.x += particle.vx * frame_scale
            particle.y += particle.vy * frame_scale
            particle.age += dt_value

            t_norm = _normalized_age(particle.age, particle.life)
            alpha_factor = apply_curve(particle.alpha_curve, t_norm)
            scale_factor = apply_curve(particle.scale_curve, t_norm)
            particle.alpha_now = _clamp(alpha_factor * (particle.alpha1 - particle.alpha0) + particle.alpha0, 0.0, 255.0)
            particle.scale_now = max(0.0, scale_factor * (particle.scale1 - particle.scale0) + particle.scale0)

            _apply_particle_animation(particle)

            if particle.age < particle.life:
                alive.append(particle)

        self.particles = alive

    def count_alive(self, emitter_id: str | None) -> int:
        if not emitter_id:
            return 0
        return sum(1 for particle in self.particles if particle.emitter_id == emitter_id)


@dataclass(slots=True)
class RateAccumulator:
    spawn_accum: float = 0.0

    def step(self, rate: float, dt: float) -> int:
        if rate <= 0.0 or dt <= 0.0:
            return 0
        self.spawn_accum += rate * dt
        count = int(self.spawn_accum)
        if count:
            self.spawn_accum -= count
        return count


@dataclass(slots=True)
class BurstController:
    fired: bool = False

    def trigger(self, count: int, *, reset: bool = False) -> int:
        if reset:
            self.fired = False
        if self.fired or count <= 0:
            return 0
        self.fired = True
        return count


def spawn_radial_particles(
    rng: random.Random,
    *,
    count: int,
    x: float,
    y: float,
    speed_min: float,
    speed_max: float,
    life_min: float,
    life_max: float,
    size: float,
    color: tuple[int, int, int] | tuple[int, int, int, int],
    scale0: float = 1.0,
    scale1: float = 0.0,
    alpha0: float = 255.0,
    alpha1: float = 0.0,
    shape: str = "circle",
    sprite_path: str | None = None,
    sprite_rect: tuple[int, int, int, int] | None = None,
    additive: bool = False,
    emitter_id: str | None = None,
) -> list[ParticleData]:
    particles: list[ParticleData] = []
    if count <= 0:
        return particles

    for _ in range(count):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        speed = rng.uniform(speed_min, speed_max)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed
        life = rng.uniform(life_min, life_max)
        particles.append(
            ParticleData(
                x=x,
                y=y,
                vx=vx,
                vy=vy,
                life=life,
                scale0=scale0,
                scale1=scale1,
                alpha0=alpha0,
                alpha1=alpha1,
                color=color,
                shape=shape,
                size=size,
                sprite_path=sprite_path,
                sprite_rect=sprite_rect,
                additive=bool(additive),
                emitter_id=emitter_id,
            )
        )
    return particles


def _coerce_dt(dt: float | None) -> float:
    if dt is None:
        return _DEFAULT_DT
    try:
        value = float(dt)
    except (TypeError, ValueError):
        return _DEFAULT_DT
    if value <= 0.0:
        return _DEFAULT_DT
    return value


def _normalize_color(color: tuple[int, int, int] | tuple[int, int, int, int] | None) -> tuple[int, int, int, int]:
    if color is None:
        return (255, 255, 255, 255)
    values = list(color)
    if len(values) >= 4:
        r, g, b, a = values[:4]
    elif len(values) >= 3:
        r, g, b = values[:3]
        a = 255
    else:
        r, g, b, a = 255, 255, 255, 255
    return (int(r), int(g), int(b), int(a))


def normalize_rect(obj: Any) -> tuple[int, int, int, int] | None:
    if obj is None:
        return None
    if not isinstance(obj, (list, tuple)) or len(obj) != 4:
        return None
    try:
        x, y, w, h = (int(obj[0]), int(obj[1]), int(obj[2]), int(obj[3]))
    except (TypeError, ValueError):
        return None
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def apply_curve(kind: str, t: float) -> float:
    value = _clamp(t, 0.0, 1.0)
    mode = str(kind or "linear").strip().lower()
    if mode == "linear":
        return value
    if mode == "ease_in":
        return value * value
    if mode == "ease_out":
        return 1.0 - (1.0 - value) * (1.0 - value)
    if mode == "ease_in_out":
        if value < 0.5:
            return 2.0 * value * value
        return 1.0 - 2.0 * (1.0 - value) * (1.0 - value)
    raise ValueError(f"Unknown curve '{kind}'")


def _normalized_age(age: float, life: float) -> float:
    if life <= 0.0:
        return 1.0
    return _clamp(age / life, 0.0, 1.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def sample_spawn_offset(rng: random.Random, cfg: dict[str, Any]) -> tuple[float, float]:
    shape = str(cfg.get("shape", "point")).strip().lower()
    if shape == "point":
        return (0.0, 0.0)
    if shape == "circle":
        radius_min = float(cfg.get("radius_min", 0.0))
        radius_max = float(cfg.get("radius_max", 0.0))
        if radius_max <= 0.0:
            return (0.0, 0.0)
        u = rng.random()
        angle = rng.random() * 2.0 * math.pi
        r_min_sq = max(0.0, radius_min) ** 2
        r_max_sq = radius_max ** 2
        if r_max_sq <= r_min_sq:
            radius = math.sqrt(r_max_sq)
        else:
            radius = math.sqrt(r_min_sq + (r_max_sq - r_min_sq) * u)
        return (math.cos(angle) * radius, math.sin(angle) * radius)
    if shape == "box":
        w = float(cfg.get("box_w", 0.0))
        h = float(cfg.get("box_h", 0.0))
        if w <= 0.0 or h <= 0.0:
            return (0.0, 0.0)
        x = (rng.random() * 2.0 - 1.0) * (w * 0.5)
        y = (rng.random() * 2.0 - 1.0) * (h * 0.5)
        return (x, y)
    if shape == "line":
        start = cfg.get("line_from", (0.0, 0.0))
        end = cfg.get("line_to", (0.0, 0.0))
        try:
            x0, y0 = float(start[0]), float(start[1])
            x1, y1 = float(end[0]), float(end[1])
        except (TypeError, ValueError, IndexError):
            return (0.0, 0.0)
        t = rng.random()
        return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    return (0.0, 0.0)


def compute_anim_frame_index(particle: ParticleData) -> int | None:
    frames = particle.anim_frames
    if not frames:
        return None
    fps = particle.anim_fps
    if fps is None or fps <= 0:
        return None
    frame_count = len(frames)
    if frame_count <= 0:
        return None
    frame_pos = int(particle.age * fps) + int(particle.anim_phase_offset or 0)
    if particle.anim_loop:
        return frame_pos % frame_count
    if frame_pos < 0:
        return 0
    return min(frame_pos, frame_count - 1)


def _apply_particle_animation(particle: ParticleData) -> None:
    if not particle.anim_frames:
        return
    idx = compute_anim_frame_index(particle)
    if idx is None:
        return
    frame_size = particle.frame_size
    grid_cols = particle.grid_cols
    if not frame_size or not grid_cols or grid_cols <= 0:
        return
    frame = particle.anim_frames[idx]
    w, h = frame_size
    if w <= 0 or h <= 0:
        return
    col = int(frame) % grid_cols
    row = int(frame) // grid_cols
    particle.sprite_rect = (col * w, row * h, w, h)
