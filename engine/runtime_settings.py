from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _clamp01(value: Any, default: float) -> float:
    try:
        f = float(value)
    except Exception:  # noqa: BLE001
        f = float(default)
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


@dataclass(slots=True)
class RuntimeSettings:
    music_volume: float = 1.0
    sfx_volume: float = 1.0
    fog_enabled: bool = False
    soft_shadows_enabled: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "music_volume": float(_clamp01(self.music_volume, 1.0)),
            "sfx_volume": float(_clamp01(self.sfx_volume, 1.0)),
            "fog_enabled": bool(self.fog_enabled),
            "soft_shadows_enabled": bool(self.soft_shadows_enabled),
        }

    @classmethod
    def from_config(cls, cfg: Any | None) -> "RuntimeSettings":
        return cls(
            music_volume=_clamp01(getattr(cfg, "music_volume", 1.0), 1.0),
            sfx_volume=_clamp01(getattr(cfg, "sfx_volume", 1.0), 1.0),
            fog_enabled=bool(getattr(cfg, "fog_enabled", False)),
            soft_shadows_enabled=bool(getattr(cfg, "soft_shadows_enabled", False)),
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
            )
        return cls(
            music_volume=_clamp01(payload.get("music_volume", base.music_volume), base.music_volume),
            sfx_volume=_clamp01(payload.get("sfx_volume", base.sfx_volume), base.sfx_volume),
            fog_enabled=bool(payload.get("fog_enabled", base.fog_enabled)),
            soft_shadows_enabled=bool(payload.get("soft_shadows_enabled", base.soft_shadows_enabled)),
        )

    def apply(self, window: Any) -> None:
        self.music_volume = _clamp01(self.music_volume, 1.0)
        self.sfx_volume = _clamp01(self.sfx_volume, 1.0)

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
            except Exception:  # noqa: BLE001
                pass
            try:
                cfg.sfx_volume = float(self.sfx_volume)
            except Exception:  # noqa: BLE001
                pass
            try:
                cfg.fog_enabled = bool(self.fog_enabled)
            except Exception:  # noqa: BLE001
                pass
            try:
                cfg.soft_shadows_enabled = bool(self.soft_shadows_enabled)
            except Exception:  # noqa: BLE001
                pass


def ensure_runtime_settings(window: Any) -> RuntimeSettings:
    settings = getattr(window, "runtime_settings", None)
    if isinstance(settings, RuntimeSettings):
        return settings
    cfg = getattr(window, "engine_config", None)
    settings = RuntimeSettings.from_config(cfg)
    setattr(window, "runtime_settings", settings)
    return settings
