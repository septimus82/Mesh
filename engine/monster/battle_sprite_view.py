"""Battle sprite rendering helpers for monster battle overlay.

Integration layer: may use arcade textures and AssetManager, but not the pure
battle math/controller modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.animation import SpriteSheetCache, SpriteSheetSpec

from .battle_model import BattleSprite, Species

if TYPE_CHECKING:
    from engine.game import GameWindow


@dataclass
class BattleSpriteAnimator:
    """Cycles idle frames from a sliced sprite sheet."""

    textures: tuple[Any, ...]
    idle_frames: tuple[int, ...]
    fps: float
    frame_cursor: int = 0
    elapsed: float = 0.0

    def update(self, dt: float) -> None:
        if len(self.idle_frames) <= 1 or self.fps <= 0.0:
            return
        self.elapsed += max(0.0, float(dt))
        frame_duration = 1.0 / float(self.fps)
        while self.elapsed >= frame_duration:
            self.elapsed -= frame_duration
            self.frame_cursor = (self.frame_cursor + 1) % len(self.idle_frames)

    def current_texture(self) -> Any | None:
        if not self.textures or not self.idle_frames:
            return None
        frame_index = self.idle_frames[self.frame_cursor % len(self.idle_frames)]
        if frame_index < 0 or frame_index >= len(self.textures):
            return None
        return self.textures[frame_index]


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
        textures = _load_battle_sprite_textures(self._window, battle_sprite)
        if not textures:
            self._animator = None
            return
        self._animator = BattleSpriteAnimator(
            textures=textures,
            idle_frames=battle_sprite.idle_frames,
            fps=float(battle_sprite.fps),
        )

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
    def has_sprite(self) -> bool:
        return self._animator is not None


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


def _load_battle_sprite_textures(window: GameWindow, battle_sprite: BattleSprite) -> tuple[Any, ...]:
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
