"""Battle sprite rendering helpers for monster battle overlay.

Integration layer: may use arcade textures and AssetManager, but not the pure
battle math/controller modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.animation import SpriteSheetCache, SpriteSheetSpec
from engine.logging_tools import get_logger

from .battle_model import BattleSprite, BattleSpriteClip, Species

if TYPE_CHECKING:
    from engine.game import GameWindow

logger = get_logger(__name__)

SheetPoolKey = tuple[str, int, int, int]

_CLIP_SHEET_TEXTURE_CACHE: dict[SheetPoolKey, tuple[Any, ...]] = {}

_CLIP_FALLBACK_CHAINS: dict[str, tuple[str, ...]] = {
    "special": ("attack", "idle"),
}
_DEFAULT_CLIP_FALLBACK: tuple[str, ...] = ("idle",)


def _sheet_pool_key(clip: BattleSpriteClip, battle_sprite: BattleSprite) -> SheetPoolKey:
    return (
        clip.sheet or battle_sprite.sheet,
        clip.frame_width or battle_sprite.frame_width,
        clip.frame_height or battle_sprite.frame_height,
        clip.columns or battle_sprite.columns,
    )


def _parent_sheet_pool_key(battle_sprite: BattleSprite) -> SheetPoolKey:
    return (
        battle_sprite.sheet,
        battle_sprite.frame_width,
        battle_sprite.frame_height,
        battle_sprite.columns,
    )


@dataclass
class BattleSpriteAnimator:
    """Per-sprite clip state machine over one or more sliced sprite sheets."""

    textures: tuple[Any, ...]
    clips: dict[str, BattleSpriteClip]
    battle_sprite: BattleSprite | None = None
    texture_pools: dict[SheetPoolKey, tuple[Any, ...]] | None = None
    active_clip_name: str = "idle"
    frame_cursor: int = 0
    elapsed: float = 0.0
    last_requested_clip: str | None = None
    last_effective_clip: str | None = None
    _logged_missing_clip_fallback: bool = False

    def play_clip(self, name: str, *, fallbacks: tuple[str, ...] | None = None) -> str:
        """Request a clip; returns the clip actually playing (fallback chain)."""
        self.last_requested_clip = name
        if fallbacks is not None:
            chain = (name, *fallbacks)
        elif name in _CLIP_FALLBACK_CHAINS:
            chain = (name, *_CLIP_FALLBACK_CHAINS[name])
        else:
            chain = (name, *_DEFAULT_CLIP_FALLBACK)
        resolved = "idle"
        for candidate in chain:
            if candidate in self.clips:
                resolved = candidate
                break
        if name not in self.clips and resolved != name and not self._logged_missing_clip_fallback:
            logger.debug("Battle clip '%s' not defined; falling back to '%s'", name, resolved)
            self._logged_missing_clip_fallback = True
        self.last_effective_clip = resolved
        self.active_clip_name = resolved
        self.frame_cursor = 0
        self.elapsed = 0.0
        return resolved

    def _active_clip(self) -> BattleSpriteClip | None:
        clip = self.clips.get(self.active_clip_name)
        if clip is not None:
            return clip
        return self.clips.get("idle")

    def _textures_for_clip(self, clip: BattleSpriteClip) -> tuple[Any, ...]:
        if self.battle_sprite is not None and self.texture_pools is not None:
            pool = self.texture_pools.get(_sheet_pool_key(clip, self.battle_sprite))
            if pool:
                return pool
        return self.textures

    def update(self, dt: float) -> None:
        self.elapsed += max(0.0, float(dt))
        while True:
            clip = self._active_clip()
            if clip is None or len(clip.frames) <= 1 or clip.fps <= 0.0:
                return
            frame_duration = 1.0 / float(clip.fps)
            if self.elapsed < frame_duration:
                return
            self.elapsed -= frame_duration
            next_cursor = self.frame_cursor + 1
            if next_cursor >= len(clip.frames):
                if clip.loop:
                    self.frame_cursor = 0
                    continue
                idle = self.clips.get("idle")
                if idle is None:
                    self.frame_cursor = len(clip.frames) - 1
                    return
                self.active_clip_name = "idle"
                self.frame_cursor = 0
                self.elapsed = 0.0
                continue
            self.frame_cursor = next_cursor

    def current_texture(self) -> Any | None:
        clip = self._active_clip()
        if clip is None or not clip.frames:
            return None
        textures = self._textures_for_clip(clip)
        if not textures:
            return None
        frame_index = clip.frames[self.frame_cursor % len(clip.frames)]
        if frame_index < 0 or frame_index >= len(textures):
            return None
        return textures[frame_index]


class BattleSpriteDisplay:
    """Resolves and draws one battle combatant sprite."""

    def __init__(self, window: GameWindow) -> None:
        self._window = window
        self.species_id: str | None = None
        self._animator: BattleSpriteAnimator | None = None

    def reload(self, species: Species) -> None:
        self.species_id = species.id
        battle_sprite = species.battle_sprite
        if battle_sprite is None:
            self._animator = None
            return
        texture_pools = _load_battle_sprite_texture_pools(self._window, battle_sprite)
        parent_key = _parent_sheet_pool_key(battle_sprite)
        default_textures = texture_pools.get(parent_key, ())
        if not default_textures or not _battle_sprite_frames_ready(battle_sprite, texture_pools):
            self._animator = None
            return
        self._animator = BattleSpriteAnimator(
            textures=default_textures,
            clips=dict(battle_sprite.clips),
            battle_sprite=battle_sprite,
            texture_pools=texture_pools,
        )
        self._animator.play_clip("idle")

    def play_clip(self, name: str) -> str | None:
        if self._animator is None:
            return None
        return self._animator.play_clip(name)

    def update(self, dt: float) -> None:
        if self._animator is not None:
            self._animator.update(dt)

    def draw(self, center_x: float, center_y: float) -> None:
        if self._animator is None:
            return
        texture = self._animator.current_texture()
        if texture is None:
            return
        width = float(getattr(texture, "width", 0) or 0)
        height = float(getattr(texture, "height", 0) or 0)
        if width <= 0.0 or height <= 0.0:
            return
        optional_arcade.draw_texture_rect_compat(
            float(center_x),
            float(center_y),
            width,
            height,
            texture,
        )

    @property
    def frame_cursor(self) -> int | None:
        if self._animator is None:
            return None
        return int(self._animator.frame_cursor)

    @property
    def last_requested_clip(self) -> str | None:
        if self._animator is None:
            return None
        return self._animator.last_requested_clip

    @property
    def last_effective_clip(self) -> str | None:
        if self._animator is None:
            return None
        return self._animator.last_effective_clip

    @property
    def has_sprite(self) -> bool:
        return self._animator is not None


def _battle_sprite_frames_ready(
    battle_sprite: BattleSprite,
    texture_pools: dict[SheetPoolKey, tuple[Any, ...]],
) -> bool:
    for clip in battle_sprite.clips.values():
        textures = texture_pools.get(_sheet_pool_key(clip, battle_sprite), ())
        if not textures:
            return False
        if clip.frames and max(clip.frames) >= len(textures):
            return False
    return True


def _sheet_cache(window: GameWindow) -> SpriteSheetCache | None:
    factory = getattr(window, "animation_factory", None)
    if factory is not None:
        sheets = getattr(factory, "sheets", None)
        if sheets is not None:
            return sheets
    assets = getattr(window, "assets", None)
    if assets is None:
        return None
    return SpriteSheetCache(assets)


def _load_parent_sheet_textures(window: GameWindow, battle_sprite: BattleSprite) -> tuple[Any, ...]:
    cache = _sheet_cache(window)
    if cache is None:
        return ()
    spec = SpriteSheetSpec(
        path=battle_sprite.sheet,
        frame_width=int(battle_sprite.frame_width),
        frame_height=int(battle_sprite.frame_height),
        columns=int(battle_sprite.columns),
        rows=int(battle_sprite.rows),
    )
    sheet = cache.get_or_build(spec)
    if sheet is None:
        return ()
    return tuple(sheet.frames)


def _max_frame_index_for_key(
    battle_sprite: BattleSprite,
    key: SheetPoolKey,
) -> int:
    last_index = -1
    for clip in battle_sprite.clips.values():
        if _sheet_pool_key(clip, battle_sprite) != key or not clip.frames:
            continue
        last_index = max(last_index, max(clip.frames))
    return last_index


def _load_battle_sprite_texture_pools(
    window: GameWindow,
    battle_sprite: BattleSprite,
) -> dict[SheetPoolKey, tuple[Any, ...]]:
    parent_key = _parent_sheet_pool_key(battle_sprite)
    keys_needed: set[SheetPoolKey] = {parent_key}
    for clip in battle_sprite.clips.values():
        keys_needed.add(_sheet_pool_key(clip, battle_sprite))

    pools: dict[SheetPoolKey, tuple[Any, ...]] = {}
    assets = getattr(window, "assets", None)

    for key in keys_needed:
        if key in _CLIP_SHEET_TEXTURE_CACHE:
            pools[key] = _CLIP_SHEET_TEXTURE_CACHE[key]
            continue

        if key == parent_key:
            textures = _load_parent_sheet_textures(window, battle_sprite)
        elif assets is None:
            textures = ()
        else:
            sheet, frame_width, frame_height, _columns = key
            total_frames = _max_frame_index_for_key(battle_sprite, key) + 1
            if total_frames <= 0:
                total_frames = 1
            textures = tuple(
                assets.load_sprite_sheet(
                    sheet,
                    int(frame_width),
                    int(frame_height),
                    int(total_frames),
                )
            )

        _CLIP_SHEET_TEXTURE_CACHE[key] = textures
        pools[key] = textures

    return pools


def clear_clip_sheet_texture_cache() -> None:
    """Reset cached per-clip sheet textures (for tests and hot reload)."""
    _CLIP_SHEET_TEXTURE_CACHE.clear()
