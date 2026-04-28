from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from engine.swallowed_exceptions import _log_swallow


def _clamp01(value: Any, default: float) -> float:
    try:
        f = float(value)
    except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
        f = float(default)
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _clamp_text_scale(value: Any, default: float = 1.0) -> float:
    """Clamp text_scale to [0.5, 3.0]."""
    try:
        f = float(value)
    except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
        f = float(default)
    return max(0.5, min(3.0, f))


@dataclass(slots=True)
class RuntimeSettings:
    music_volume: float = 1.0
    sfx_volume: float = 1.0
    fog_enabled: bool = False
    soft_shadows_enabled: bool = False
    text_scale: float = 1.0

    def to_payload(self) -> dict[str, object]:
        return {
            "music_volume": float(_clamp01(self.music_volume, 1.0)),
            "sfx_volume": float(_clamp01(self.sfx_volume, 1.0)),
            "fog_enabled": bool(self.fog_enabled),
            "soft_shadows_enabled": bool(self.soft_shadows_enabled),
            "text_scale": float(_clamp_text_scale(self.text_scale)),
        }

    @classmethod
    def from_config(cls, cfg: Any | None) -> "RuntimeSettings":
        return cls(
            music_volume=_clamp01(getattr(cfg, "music_volume", 1.0), 1.0),
            sfx_volume=_clamp01(getattr(cfg, "sfx_volume", 1.0), 1.0),
            fog_enabled=bool(getattr(cfg, "fog_enabled", False)),
            soft_shadows_enabled=bool(getattr(cfg, "soft_shadows_enabled", False)),
            text_scale=_clamp_text_scale(getattr(cfg, "text_scale", 1.0)),
        )

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object] | None,
        *,
        base: "RuntimeSettings" | None = None,
    ) -> "RuntimeSettings":
        if base is None:
            base = cls()
        if not isinstance(payload, dict):
            return cls(
                music_volume=base.music_volume,
                sfx_volume=base.sfx_volume,
                fog_enabled=base.fog_enabled,
                soft_shadows_enabled=base.soft_shadows_enabled,
                text_scale=base.text_scale,
            )
        return cls(
            music_volume=_clamp01(payload.get("music_volume", base.music_volume), base.music_volume),
            sfx_volume=_clamp01(payload.get("sfx_volume", base.sfx_volume), base.sfx_volume),
            fog_enabled=bool(payload.get("fog_enabled", base.fog_enabled)),
            soft_shadows_enabled=bool(payload.get("soft_shadows_enabled", base.soft_shadows_enabled)),
            text_scale=_clamp_text_scale(payload.get("text_scale", base.text_scale)),
        )

    def apply(self, window: Any) -> None:
        self.music_volume = _clamp01(self.music_volume, 1.0)
        self.sfx_volume = _clamp01(self.sfx_volume, 1.0)
        self.text_scale = _clamp_text_scale(self.text_scale)

        audio = getattr(window, "audio", None)
        if audio is not None:
            setter = getattr(audio, "set_music_volume", None)
            if callable(setter):
                setter(self.music_volume)
            setter = getattr(audio, "set_sfx_volume", None)
            if callable(setter):
                setter(self.sfx_volume)

        cfg = getattr(window, "engine_config", None)
        if cfg is not None:
            try:
                cfg.music_volume = float(self.music_volume)
            except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("RUNT-001", "engine/runtime_settings.py pass-only blanket swallow")
                pass
            try:
                cfg.sfx_volume = float(self.sfx_volume)
            except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("RUNT-002", "engine/runtime_settings.py pass-only blanket swallow")
                pass
            try:
                cfg.fog_enabled = bool(self.fog_enabled)
            except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("RUNT-003", "engine/runtime_settings.py pass-only blanket swallow")
                pass
            try:
                cfg.soft_shadows_enabled = bool(self.soft_shadows_enabled)
            except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("RUNT-004", "engine/runtime_settings.py pass-only blanket swallow")
                pass

        # Push text scale to the text drawing module
        try:
            from engine.text_draw import set_text_scale
            set_text_scale(self.text_scale)
        except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("RUNT-005", "engine/runtime_settings.py pass-only blanket swallow")
            pass


def ensure_runtime_settings(window: Any) -> RuntimeSettings:
    settings = getattr(window, "runtime_settings", None)
    if isinstance(settings, RuntimeSettings):
        return settings
    cfg = getattr(window, "engine_config", None)
    settings = RuntimeSettings.from_config(cfg)
    setattr(window, "runtime_settings", settings)
    return settings
