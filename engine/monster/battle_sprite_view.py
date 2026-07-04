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


@dataclass
class BattleSpriteAnimator:
    """Per-sprite clip state machine over a sliced sprite sheet."""

    textures: tuple[Any, ...]
    clips: dict[str, BattleSpriteClip]
    active_clip_name: str = "idle"
    frame_cursor: int = 0
    elapsed: float = 0.0
    last_requested_clip: str | None = None
    last_effective_clip: str | None = None
    _logged_missing_clip_fallback: bool = False

    def play_clip(self, name: str) -> str:
        """Request a clip; returns the clip actually playing (idle fallback)."""
        self.last_requested_clip = name
        resolved = name if name in self.clips else "idle"
        if resolved not in self.clips:
            resolved = "idle"
        if name not in self.clips and not self._logged_missing_clip_fallback:
            logger.debug("Battle clip '%s' not defined; falling back to idle", name)
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
        if clip is None or not self.textures or not clip.frames:
            return None
        frame_index = clip.frames[self.frame_cursor % len(clip.frames)]
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
        if not textures or not _battle_sprite_frames_ready(battle_sprite, textures):
            self._animator = None
            return
        self._animator = BattleSpriteAnimator(
            textures=textures,
            clips=dict(battle_sprite.clips),
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


def _battle_sprite_frames_ready(battle_sprite: BattleSprite, textures: tuple[Any, ...]) -> bool:
    if not textures:
        return False
    last_index = -1
    for clip in battle_sprite.clips.values():
        if clip.frames:
            last_index = max(last_index, max(clip.frames))
    return last_index < len(textures)


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
