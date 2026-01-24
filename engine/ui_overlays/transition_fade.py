from __future__ import annotations

from typing import Callable, Optional

import engine.optional_arcade as optional_arcade

from .common import UIElement, _draw_rectangle_filled
from ..text_draw import draw_text_cached
from ..i18n import tr


class TransitionFadeOverlay(UIElement):
    """Fullscreen fade overlay for scene transitions."""

    _LOADING_ALPHA_THRESHOLD = 24.0

    def __init__(self, window) -> None:
        super().__init__(window)
        self._state: str = "idle"
        self._timer: float = 0.0
        self._duration: float = 0.0
        self._alpha: float = 0.0
        self._on_complete: Optional[Callable[[], None]] = None

    @property
    def is_active(self) -> bool:
        return self._state != "idle"

    @property
    def blocks_input(self) -> bool:
        return self.is_active

    @property
    def alpha(self) -> float:
        return self._alpha

    def start_fade_out(
        self,
        duration_s: float,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._duration = max(0.0, float(duration_s))
        self._timer = 0.0
        self._on_complete = on_complete
        if self._duration <= 0.0:
            self._alpha = 255.0
            self._state = "hold"
            self._invoke_on_complete()
            return
        self._state = "fading_out"
        self._alpha = 0.0

    def start_fade_in(self, duration_s: float) -> None:
        self._duration = max(0.0, float(duration_s))
        self._timer = 0.0
        self._on_complete = None
        if self._duration <= 0.0:
            self._alpha = 0.0
            self._state = "idle"
            return
        self._state = "fading_in"
        self._alpha = 255.0

    def _invoke_on_complete(self) -> None:
        callback = self._on_complete
        self._on_complete = None
        if callback is not None:
            callback()

    def _ease_in_out(self, t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        if t < 0.5:
            return 2.0 * t * t
        inv = 1.0 - t
        return 1.0 - 2.0 * inv * inv

    def _loading_text_enabled(self) -> bool:
        window = self.window
        cfg = getattr(window, "engine_config", None)
        enabled = bool(getattr(cfg, "scene_fade_show_loading_text", False))
        scene_controller = getattr(window, "scene_controller", None)
        settings = getattr(scene_controller, "scene_settings", None) if scene_controller is not None else None
        if isinstance(settings, dict) and "scene_fade_show_loading_text" in settings:
            enabled = bool(settings.get("scene_fade_show_loading_text"))
        return enabled

    @property
    def should_draw_loading_text(self) -> bool:
        if not self.is_active:
            return False
        if self._alpha < self._LOADING_ALPHA_THRESHOLD:
            return False
        return self._loading_text_enabled()

    def update(self, dt: float) -> None:
        if self._state == "idle":
            return
        dt = max(0.0, float(dt))
        if self._state == "fading_out":
            self._timer += dt
            progress = min(1.0, self._timer / max(self._duration, 1e-6))
            eased = self._ease_in_out(progress)
            self._alpha = 255.0 * eased
            if progress >= 1.0:
                self._alpha = 255.0
                self._state = "hold"
                self._invoke_on_complete()
            return
        if self._state == "fading_in":
            self._timer += dt
            progress = min(1.0, self._timer / max(self._duration, 1e-6))
            eased = self._ease_in_out(progress)
            self._alpha = 255.0 * (1.0 - eased)
            if progress >= 1.0:
                self._alpha = 0.0
                self._state = "idle"

    def draw(self) -> None:
        if self._alpha <= 0.0:
            return
        if optional_arcade.arcade is None:
            return
        color = (0, 0, 0, int(self._alpha))
        _draw_rectangle_filled(
            self.window.width / 2.0,
            self.window.height / 2.0,
            self.window.width,
            self.window.height,
            color,
        )
        if not self.should_draw_loading_text:
            return
        label_alpha = max(0, min(255, int(self._alpha)))
        cache = getattr(self.window, "text_cache", None)
        draw_text_cached(
            tr("UI_LOADING"),
            self.window.width / 2.0,
            self.window.height / 2.0,
            color=(255, 255, 255, label_alpha),
            font_size=16.0,
            anchor_x="center",
            anchor_y="center",
            cache=cache,
        )
