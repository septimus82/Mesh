from __future__ import annotations

from typing import Any
import engine.optional_arcade as optional_arcade
from engine.paths import resolve_path
from engine.render_queue import BatchKey, DrawSpriteCmd, RenderQueueStats, SpriteDrawList


class ArcadeSpriteBatcher:
    def __init__(self, window: Any) -> None:
        self.window = window
        self.available = optional_arcade.arcade is not None
        self._sprite_lists: dict[BatchKey, Any] = {}
        self._sprite_pool: dict[BatchKey, list[Any]] = {}
        self._texture_cache: dict[Any, Any] = {}
        self._additive_warned = False

    def draw(self, draw_list: SpriteDrawList) -> RenderQueueStats:
        stats = RenderQueueStats()
        if not self.available or optional_arcade.arcade is None:
            return stats

        batches = draw_list.build_batches()
        stats.sprites_submitted = len(draw_list.commands)
        stats.batches_drawn = len(batches)
        stats.draw_calls_estimate = stats.batches_drawn
        stats.sprites_drawn = sum(len(cmds) for _, cmds in batches)

        current_blend = "normal"
        for key, cmds in batches:
            if not cmds:
                continue
            blend = key.blend_mode
            if blend != current_blend:
                if blend == "additive":
                    self._enable_additive_blend()
                else:
                    self._restore_default_blend()
                current_blend = blend

            sprite_list = self._sprite_lists.get(key)
            if sprite_list is None:
                sprite_list = optional_arcade.arcade.SpriteList()
                self._sprite_lists[key] = sprite_list
            sprite_list.clear()

            active: list[Any] = []
            for cmd in cmds:
                texture = cmd.texture or self._resolve_texture(cmd)
                sprite = self._acquire_sprite(key, texture)
                self._apply_cmd(sprite, cmd)
                sprite_list.append(sprite)
                active.append(sprite)

            sprite_list.draw()
            sprite_list.clear()
            self._release_sprites(key, active)

        if current_blend != "normal":
            self._restore_default_blend()
        return stats

    def _apply_cmd(self, sprite: Any, cmd: DrawSpriteCmd) -> None:
        sprite.center_x = float(cmd.x)
        sprite.center_y = float(cmd.y)
        sprite.scale = float(cmd.scale)
        sprite.alpha = int(max(0, min(255, float(cmd.alpha))))
        sprite.angle = float(cmd.rotation)
        if cmd.color is not None:
            try:
                sprite.color = cmd.color
            except Exception:
                pass

    def _acquire_sprite(self, key: BatchKey, texture: Any) -> Any:
        pool = self._sprite_pool.get(key)
        if pool:
            sprite = pool.pop()
            try:
                sprite.texture = texture
            except Exception:
                pass
            return sprite
        return optional_arcade.arcade.Sprite(texture)

    def _release_sprites(self, key: BatchKey, sprites: list[Any]) -> None:
        if not sprites:
            return
        pool = self._sprite_pool.setdefault(key, [])
        pool.extend(sprites)

    def _resolve_texture(self, cmd: DrawSpriteCmd) -> Any:
        key = cmd.texture_key
        cached = self._texture_cache.get(key)
        if cached is not None:
            return cached

        texture = None
        if isinstance(key, tuple) and key:
            if key[0] == "sprite" and len(key) >= 2:
                path = str(key[1])
                rect = key[2] if len(key) > 2 else None
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
            elif key[0] == "shape" and len(key) >= 3:
                size = int(key[2])
                color = key[3] if len(key) > 3 else optional_arcade.arcade.color.WHITE
                texture = optional_arcade.arcade.make_circle_texture(size, color)

        if texture is None:
            texture = optional_arcade.arcade.make_circle_texture(4, optional_arcade.arcade.color.WHITE)

        self._texture_cache[key] = texture
        return texture

    def _enable_additive_blend(self) -> None:
        if optional_arcade.arcade is None:
            return
        gl = getattr(optional_arcade.arcade, "gl", None)
        ctx = getattr(self.window, "ctx", None)
        if gl is None or ctx is None or not hasattr(ctx, "blend_func"):
            self._log_additive_unavailable_once()
            return
        try:
            ctx.enable(ctx.BLEND)
        except Exception:
            pass
        try:
            ctx.blend_func = gl.BLEND_ADDITIVE
        except Exception:
            self._log_additive_unavailable_once()

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
        if self._additive_warned:
            return
        self._additive_warned = True
        print("[Mesh][RenderQueue] WARNING: additive blend unavailable; drawing as normal blend")

    def clear_texture_cache(self) -> int:
        count = len(self._texture_cache)
        self._texture_cache.clear()
        return count

    def clear_sprite_cache(self) -> int:
        pool_count = sum(len(pool) for pool in self._sprite_pool.values()) if self._sprite_pool else 0
        list_count = len(self._sprite_lists)
        for sprite_list in self._sprite_lists.values():
            try:
                sprite_list.clear()
            except Exception:
                pass
        self._sprite_pool.clear()
        self._sprite_lists.clear()
        return pool_count + list_count
