"""A read-only snapshot of what the running game is doing: lighting, particles, camera, audio.

For tests and verification harnesses that drive the real window (Mesh Studio's layout dump
includes it while play-testing). It only reads; every part is best-effort so a missing system
reads as absent rather than failing.
"""

from __future__ import annotations

from typing import Any


def _xy(value: Any) -> list[float] | None:
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError, IndexError):
        return None


def runtime_snapshot(window: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    lighting = getattr(window, "lighting", None)
    if lighting is not None:
        out["lighting"] = {
            "available": bool(getattr(lighting, "available", False)),
            "enabled": bool(getattr(lighting, "enabled", False)),
            "shadows_mode": str(getattr(lighting, "shadows_mode", "")),
            "clock": round(float(getattr(lighting, "_flicker_time", 0.0) or 0.0), 2),
            "ambient": list(getattr(lighting, "ambient_color", ()) or ()),
            "ambient_tint": list(getattr(lighting, "ambient_tint", ()) or ()),
            "static_lights": len(getattr(lighting, "_static_lights", []) or []),
            "occluders": len(getattr(lighting, "_static_occluders", []) or []),
            "dynamic": [{"at": _xy(getattr(getattr(h, "light", None), "position", None)),
                         "radius": float(getattr(h, "base_radius", 0) or 0),
                         "owner": type(getattr(h, "owner", None)).__name__,
                         "owner_at": _xy((getattr(h.owner, "center_x", None), getattr(h.owner, "center_y", None)))}
                        for h in getattr(lighting, "_dynamic_handles", []) or []],
        }
    particles = getattr(window, "particle_manager", None)
    if particles is not None:
        sprites = getattr(particles, "particles", None)
        system = getattr(particles, "system", None)
        out["particles"] = {"sprites": len(sprites) if sprites is not None else 0,
                            "alive": len(getattr(system, "particles", []) or [])}
    camera = getattr(window, "camera_controller", None)
    if camera is not None:
        zoom = getattr(camera, "zoom_state", None)
        area = getattr(camera, "active_area", None)
        out["camera"] = {"zoom": float(getattr(zoom, "current", 1.0) or 1.0),
                         "zoom_target": float(getattr(zoom, "target", 1.0) or 1.0),
                         "trauma": float(getattr(camera, "trauma", 0.0) or 0.0),
                         "center": _xy(window.get_camera_center()) if hasattr(window, "get_camera_center") else None,
                         "area": getattr(area, "name", None) if area is not None else None}
    audio = getattr(window, "audio", None)
    if audio is not None:
        out["audio"] = {"recent": list(getattr(audio, "recent_plays", []) or [])[-12:]}
    return out
