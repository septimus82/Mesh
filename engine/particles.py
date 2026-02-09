from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any, TypeAlias, cast
import engine.optional_arcade as optional_arcade

from .particles_core import ParticleData, ParticleSystem, appearance_key
from .culling import is_sprite_visible, sprite_bounds
from .paths import resolve_path
from .render_queue import DrawSpriteCmd

if TYPE_CHECKING:
    # Use TYPE_CHECKING import to allow type hints without runtime dependency
    try:
        from arcade import Sprite, SpriteList, Texture
    except ImportError:
        Sprite: TypeAlias = Any  # type: ignore
        SpriteList: TypeAlias = Any  # type: ignore
        Texture: TypeAlias = Any  # type: ignore

    from .game import GameWindow
else:
    Sprite = object  # type: ignore[misc,assignment]
    SpriteList = object  # type: ignore[misc,assignment]
    Texture = object  # type: ignore[misc,assignment]

_DEFAULT_WHITE = (255, 255, 255)
_DEFAULT_GOLD = (255, 215, 0)
_DEFAULT_RED = (255, 0, 0)

if optional_arcade.arcade is not None:
    try:
        _DEFAULT_WHITE = optional_arcade.arcade.color.WHITE
        _DEFAULT_GOLD = optional_arcade.arcade.color.GOLD
        _DEFAULT_RED = optional_arcade.arcade.color.RED
    except Exception:
        pass


BaseParticleSprite: TypeAlias = Sprite


def _resolve_particle_seed(window: Any) -> int | None:
    seed_value = getattr(window, "particle_seed", None)
    if seed_value is None:
        cfg = getattr(window, "engine_config", None)
        seed_value = getattr(cfg, "particle_seed", None) if cfg is not None else None
    if seed_value is None:
        return None
    try:
        return int(seed_value)
    except Exception:  # noqa: BLE001
        return None


def _build_effect_rng(window: Any) -> random.Random | None:
    seed = _resolve_particle_seed(window)
    if seed is None:
        return None
    return random.Random(seed)


class Particle(BaseParticleSprite):
    """Legacy particle sprite retained for compatibility."""

    def __init__(self, texture, center_x, center_y, change_x, change_y, lifetime, scale_change=0):
        if optional_arcade.arcade is None:
            raise RuntimeError("Particle requires optional_arcade.arcade; use ParticleManager for headless usage.")
        super().__init__(texture, center_x=center_x, center_y=center_y)
        self.change_x = change_x
        self.change_y = change_y
        self.lifetime = lifetime
        self.life = lifetime
        self.scale_change = scale_change

    def update(self, delta_time: float = 1 / 60):
        dt = float(delta_time) if delta_time else 1 / 60
        frame_scale = dt * 60.0

        self.center_x += self.change_x * frame_scale
        self.center_y += self.change_y * frame_scale
        self.life -= dt

        delta_scale = self.scale_change * frame_scale
        sprite = cast(Any, self)
        current_scale = sprite.scale
        if isinstance(current_scale, tuple) and len(current_scale) == 2:
            sprite.scale = (float(current_scale[0]) + delta_scale, float(current_scale[1]) + delta_scale)
            scale_value = min(float(sprite.scale[0]), float(sprite.scale[1]))
        else:
            sprite.scale = float(current_scale) + delta_scale
            scale_value = float(sprite.scale)

        if self.life <= 0 or scale_value <= 0:
            self.kill()
        else:
            # Fade out
            self.alpha = int((self.life / self.lifetime) * 255)


class ParticleManager:
    def __init__(self, window: "GameWindow") -> None:
        self.window = window
        self.system = ParticleSystem()
        self._effect_rng = _build_effect_rng(window)
        self._arcade_available = optional_arcade.arcade is not None
        self._sprites: list["Sprite"] = []
        self._sprite_pool: dict[tuple[Any, ...], list["Sprite"]] = {}
        self._texture_cache: dict[tuple[Any, ...], "Texture"] = {}
        self.sprite_load_failures = 0
        self._additive_blend_warned = False
        self.particles: "SpriteList" | None
        if self._arcade_available:
            self.particles = optional_arcade.arcade.SpriteList()
            self._draw_normal = optional_arcade.arcade.SpriteList()
            self._draw_additive = optional_arcade.arcade.SpriteList()
        else:
            self.particles = None
            self._draw_normal = None
            self._draw_additive = None

    def update(self, dt: float | None = None) -> None:
        self.system.reset_frame_counters()
        self.system.update(dt)
        if self._arcade_available:
            self._sync_sprites()

    def draw(self) -> None:
        if self.particles is None:
            return
        if not self._sprites:
            return
        render_queue = getattr(self.window, "render_queue", None)
        use_batching = False
        if render_queue is not None and getattr(self.window, "render_batching_enabled", False):
            enabled = getattr(render_queue, "is_enabled", None)
            use_batching = enabled() if callable(enabled) else True
        culled = 0
        if use_batching and render_queue is not None:
            use_culling = bool(getattr(self.window, "render_culling_enabled", False))
            camera_rect = self._get_camera_rect() if use_culling else None
            for particle, sprite in zip(self.system.particles, self._sprites):
                scale_value = self._coerce_scale(getattr(sprite, "scale", 1.0))
                if use_culling and camera_rect is not None:
                    width = getattr(sprite, "width", None)
                    height = getattr(sprite, "height", None)
                    sprite_rect = None
                    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
                        if float(width) > 0.0 and float(height) > 0.0:
                            sprite_rect = sprite_bounds(
                                float(getattr(sprite, "center_x", 0.0)),
                                float(getattr(sprite, "center_y", 0.0)),
                                float(width),
                                float(height),
                            )
                    rect = particle.sprite_rect
                    if sprite_rect is None and rect is not None:
                        _, _, w, h = rect
                        sprite_rect = sprite_bounds(
                            float(getattr(sprite, "center_x", 0.0)),
                            float(getattr(sprite, "center_y", 0.0)),
                            float(w),
                            float(h),
                            scale=scale_value,
                        )
                    if sprite_rect is None and getattr(particle, "size", None) is not None:
                        sprite_rect = sprite_bounds(
                            float(getattr(sprite, "center_x", 0.0)),
                            float(getattr(sprite, "center_y", 0.0)),
                            float(getattr(particle, "size", 0.0)),
                            float(getattr(particle, "size", 0.0)),
                            scale=scale_value,
                        )
                    if sprite_rect is not None and not is_sprite_visible(camera_rect, sprite_rect):
                        culled += 1
                        continue
                blend = "additive" if getattr(particle, "additive", False) else "normal"
                render_queue.submit(
                    DrawSpriteCmd(
                        texture_key=self._texture_key(particle),
                        texture=getattr(sprite, "texture", None),
                        x=float(getattr(sprite, "center_x", 0.0)),
                        y=float(getattr(sprite, "center_y", 0.0)),
                        scale=scale_value,
                        alpha=float(getattr(sprite, "alpha", 255)),
                        rotation=float(getattr(sprite, "angle", 0.0)),
                        layer=1000,
                        blend_mode=blend,
                        color=getattr(sprite, "color", None),
                    )
                )
            render_queue.flush()
            self._set_particle_cull_counter(culled)
            return
        self._rebuild_draw_groups()
        if self._draw_normal is None or self._draw_additive is None:
            self.particles.draw()
            self._set_particle_cull_counter(culled)
            return
        if len(self._draw_normal) > 0:
            self._draw_normal.draw()
        if len(self._draw_additive) == 0:
            self._set_particle_cull_counter(culled)
            return
        if self._enable_additive_blend():
            try:
                self._draw_additive.draw()
            finally:
                self._restore_default_blend()
        else:
            self._draw_additive.draw()
        self._set_particle_cull_counter(culled)

    def emit_hit_effect(self, x: float, y: float, color: tuple = _DEFAULT_WHITE) -> None:
        """Emit a burst of particles for a hit effect."""
        rng = self._effect_rng or random
        particles = []
        for _ in range(8):
            angle = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(1.0, 3.0)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            life = rng.uniform(0.3, 0.6)
            life, scale1 = _apply_scale_change(scale0=1.0, scale_change=-0.05, life=life)
            particles.append(
                ParticleData(
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy,
                    life=life,
                    scale0=1.0,
                    scale1=scale1,
                    alpha0=255.0,
                    alpha1=0.0,
                    color=color,
                    shape="circle",
                    size=4.0,
                )
            )
        self.system.spawn(particles)

    def emit_collect_effect(self, x: float, y: float) -> None:
        """Emit a burst of particles for a collection effect."""
        rng = self._effect_rng or random
        particles = []
        for _ in range(12):
            angle = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(2.0, 4.0)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            life = rng.uniform(0.5, 0.8)
            life, scale1 = _apply_scale_change(scale0=1.0, scale_change=-0.03, life=life)
            particles.append(
                ParticleData(
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy,
                    life=life,
                    scale0=1.0,
                    scale1=scale1,
                    alpha0=255.0,
                    alpha1=0.0,
                    color=_DEFAULT_GOLD,
                    shape="circle",
                    size=5.0,
                )
            )
        self.system.spawn(particles)

    def emit_death_effect(self, x: float, y: float, color: tuple = _DEFAULT_RED) -> None:
        """Emit a larger burst for death."""
        rng = self._effect_rng or random
        particles = []
        for _ in range(20):
            angle = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(2.0, 5.0)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            life = rng.uniform(0.8, 1.2)
            life, scale1 = _apply_scale_change(scale0=1.5, scale_change=-0.05, life=life)
            particles.append(
                ParticleData(
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy,
                    life=life,
                    scale0=1.5,
                    scale1=scale1,
                    alpha0=255.0,
                    alpha1=0.0,
                    color=color,
                    shape="circle",
                    size=6.0,
                )
            )
        self.system.spawn(particles)

    def clear(self) -> None:
        self.system.clear()
        if self.particles is not None:
            self.particles.clear()
            for sprite in self._sprites:
                self._release_sprite(sprite)
            self._sprites = []

    def clear_render_cache(self) -> dict[str, int]:
        texture_count = len(self._texture_cache)
        sprite_count = len(self._sprites)
        sprite_count += sum(len(pool) for pool in self._sprite_pool.values()) if self._sprite_pool else 0
        self._texture_cache.clear()
        self._sprite_pool.clear()
        self._sprites.clear()
        if self.particles is not None:
            self.particles.clear()
        if self._draw_normal is not None:
            self._draw_normal.clear()
        if self._draw_additive is not None:
            self._draw_additive.clear()
        return {
            "particle_textures_cleared": int(texture_count),
            "particle_sprites_cleared": int(sprite_count),
        }

    def _sync_sprites(self) -> None:
        if self.particles is None:
            return
        particles = self.system.particles
        active: list["Sprite"] = []

        for index, particle in enumerate(particles):
            key = self._pool_key(particle)
            sprite = None
            if index < len(self._sprites):
                candidate = self._sprites[index]
                if getattr(candidate, "_particle_key", None) == key:
                    sprite = candidate
                else:
                    self._release_sprite(candidate)
            if sprite is None:
                sprite = self._acquire_sprite(key, particle)
            self._apply_particle(sprite, particle)
            active.append(sprite)

        for idx in range(len(particles), len(self._sprites)):
            self._release_sprite(self._sprites[idx])

        self._sprites = active
        self.particles.clear()
        for sprite in active:
            self.particles.append(sprite)

    def _rebuild_draw_groups(self) -> None:
        if self._draw_normal is None or self._draw_additive is None:
            return
        self._draw_normal.clear()
        self._draw_additive.clear()
        for particle, sprite in zip(self.system.particles, self._sprites):
            if getattr(particle, "additive", False):
                self._draw_additive.append(sprite)
            else:
                self._draw_normal.append(sprite)

    def _enable_additive_blend(self) -> bool:
        if optional_arcade.arcade is None:
            return False
        gl = getattr(optional_arcade.arcade, "gl", None)
        ctx = getattr(self.window, "ctx", None)
        if gl is None or ctx is None or not hasattr(ctx, "blend_func"):
            self._log_additive_unavailable_once()
            return False
        try:
            ctx.enable(ctx.BLEND)
        except Exception:
            pass
        try:
            ctx.blend_func = gl.BLEND_ADDITIVE
        except Exception:
            self._log_additive_unavailable_once()
            return False
        return True

    def _restore_default_blend(self) -> None:
        if optional_arcade.arcade is None:
            return
        gl = getattr(optional_arcade.arcade, "gl", None)
        ctx = getattr(self.window, "ctx", None)
        if gl is None or ctx is None or not hasattr(ctx, "blend_func"):
            return
        try:
            ctx.blend_func = gl.BLEND_DEFAULT
        except Exception:
            return

    def _log_additive_unavailable_once(self) -> None:
        if self._additive_blend_warned:
            return
        self._additive_blend_warned = True
        print("[Mesh][Particles] WARNING: additive blend unavailable; drawing as normal blend")

    def _pool_key(self, particle: ParticleData) -> tuple[Any, ...]:
        key = appearance_key(particle)
        if key and key[0] == "sprite":
            return ("sprite", key[1])
        return key

    def _texture_key(self, particle: ParticleData) -> tuple[Any, ...]:
        if particle.sprite_path:
            return ("sprite", str(particle.sprite_path), particle.sprite_rect)
        return appearance_key(particle)

    def _acquire_sprite(self, key: tuple[Any, ...], particle: ParticleData) -> "Sprite":
        pool = self._sprite_pool.get(key)
        if pool:
            sprite = pool.pop()
        else:
            sprite = self._create_sprite(key, particle)
        setattr(sprite, "_particle_key", key)
        return sprite

    def _create_sprite(self, key: tuple[Any, ...], particle: ParticleData) -> "Sprite":
        texture = self._get_texture(self._texture_key(particle), particle)
        sprite = optional_arcade.arcade.Sprite(texture, center_x=particle.x, center_y=particle.y)
        setattr(sprite, "_particle_texture_key", self._texture_key(particle))
        return cast("Sprite", sprite)

    def _get_texture(self, key: tuple[Any, ...], particle: ParticleData) -> "Texture":
        cached = self._texture_cache.get(key)
        if cached is not None:
            return cached

        texture = None
        if key and key[0] == "sprite":
            path = str(key[1])
            rect = key[2] if len(key) > 2 else particle.sprite_rect
            try:
                resolved = str(resolve_path(path))
                if rect is not None:
                    x, y, w, h = rect
                    texture = optional_arcade.arcade.load_texture(resolved, x, y, w, h)
                else:
                    manager = getattr(self.window, "assets", None)
                    if manager is not None:
                        texture = manager.get_texture(path)
                    else:
                        texture = optional_arcade.arcade.load_texture(resolved)
            except Exception:
                texture = None
        else:
            shape = key[1] if len(key) > 1 else "circle"
            size = key[2] if len(key) > 2 else 4.0
            color = key[3] if len(key) > 3 else _DEFAULT_WHITE
            if shape != "circle":
                shape = "circle"
            texture = optional_arcade.arcade.make_circle_texture(int(size), color)

        if texture is None:
            if key and key[0] == "sprite":
                self.sprite_load_failures += 1
            texture = optional_arcade.arcade.make_circle_texture(4, _DEFAULT_WHITE)

        self._texture_cache[key] = texture
        return cast("Texture", texture)

    def _release_sprite(self, sprite: "Sprite") -> None:
        key = getattr(sprite, "_particle_key", None)
        if key is None:
            return
        pool = self._sprite_pool.setdefault(key, [])
        pool.append(sprite)

    def _apply_particle(self, sprite: "Sprite", particle: ParticleData) -> None:
        scale = getattr(particle, "scale_now", particle.scale0)
        alpha = getattr(particle, "alpha_now", particle.alpha0)
        sprite.center_x = particle.x
        sprite.center_y = particle.y
        sprite.scale = max(0.0, float(scale))
        sprite.alpha = int(max(0.0, min(255.0, alpha)))
        self._sync_sprite_texture(sprite, particle)

    def _sync_sprite_texture(self, sprite: "Sprite", particle: ParticleData) -> None:
        if not particle.sprite_path:
            return
        texture_key = self._texture_key(particle)
        last_key = getattr(sprite, "_particle_texture_key", None)
        if last_key == texture_key:
            return
        texture = self._get_texture(texture_key, particle)
        try:
            sprite.texture = texture
        except Exception:
            return
        setattr(sprite, "_particle_texture_key", texture_key)

    def _get_camera_rect(self) -> tuple[float, float, float, float]:
        camera_pos = self.window.get_camera_center()
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

    def _set_particle_cull_counter(self, value: int) -> None:
        perf = getattr(self.window, "perf_stats", None)
        setter = getattr(perf, "set_counter", None) if perf is not None else None
        if not callable(setter):
            return
        setter("particle_sprites_culled", int(value))

    def _coerce_scale(self, value: Any) -> float:
        if isinstance(value, tuple) and value:
            try:
                return float(value[0])
            except (TypeError, ValueError):
                return 1.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 1.0


def _apply_scale_change(*, scale0: float, scale_change: float, life: float) -> tuple[float, float]:
    if scale_change >= 0.0:
        return life, scale0 + scale_change * life * 60.0
    time_to_zero = scale0 / (-scale_change * 60.0) if scale0 > 0.0 else 0.0
    if time_to_zero > 0.0 and time_to_zero < life:
        life = time_to_zero
    return life, max(0.0, scale0 + scale_change * life * 60.0)
