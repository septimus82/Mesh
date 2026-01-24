from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnimationDef:
    frames: list[int]
    fps: float
    loop: bool = True


class SpriteAnimator:
    def __init__(self, anim_defs: dict[str, AnimationDef], initial: str) -> None:
        if not anim_defs:
            raise ValueError("SpriteAnimator requires at least one animation")
        self._anims = dict(anim_defs)
        self._active = initial if initial in self._anims else sorted(self._anims)[0]
        self._cursor = 0
        self._elapsed = 0.0
        self._paused = False
        self._sanitize_active()

    def _sanitize_active(self) -> None:
        anim = self._anims.get(self._active)
        if anim is None or not anim.frames:
            # Pick first valid animation deterministically.
            for name in sorted(self._anims):
                candidate = self._anims[name]
                if candidate.frames:
                    self._active = name
                    self._cursor = 0
                    self._elapsed = 0.0
                    self._paused = False
                    return
            self._paused = True

    def set_animation(self, name: str) -> None:
        if name not in self._anims:
            return
        if name == self._active:
            return
        self._active = name
        self._cursor = 0
        self._elapsed = 0.0
        self._paused = False
        self._sanitize_active()

    def update(self, dt: float) -> None:
        if dt <= 0:
            return
        if self._paused:
            return
        anim = self._anims.get(self._active)
        if anim is None or not anim.frames:
            return
        fps = float(anim.fps)
        if fps <= 0:
            return
        if len(anim.frames) == 1:
            return

        frame_time = 1.0 / max(fps, 0.0001)
        self._elapsed += float(dt)
        while self._elapsed >= frame_time and not self._paused:
            self._elapsed -= frame_time
            self._cursor += 1
            if self._cursor >= len(anim.frames):
                if anim.loop:
                    self._cursor = 0
                else:
                    self._cursor = len(anim.frames) - 1
                    self._paused = True

    def current_frame_index(self) -> int:
        anim = self._anims.get(self._active)
        if anim is None or not anim.frames:
            return 0
        idx = min(max(0, int(self._cursor)), len(anim.frames) - 1)
        return int(anim.frames[idx])

    def active_animation_name(self) -> str:
        return self._active

