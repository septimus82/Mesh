"""Shadow selection helpers extracted from the lighting module."""

from __future__ import annotations

from typing import Any


def extract_light_pos_radius(light: Any) -> tuple[float, float, float] | None:
    pos = getattr(light, "position", None)
    radius = getattr(light, "radius", None)
    if pos is not None and radius is not None:
        try:
            if isinstance(pos, (tuple, list)) and len(pos) >= 2:
                lx, ly = float(pos[0]), float(pos[1])
            elif hasattr(pos, "x") and hasattr(pos, "y"):
                lx, ly = float(getattr(pos, "x")), float(getattr(pos, "y"))
            else:
                it = iter(pos)
                lx = float(next(it))
                ly = float(next(it))
            r = float(radius)
            if r > 0:
                return (lx, ly, r)
        except Exception:  # noqa: BLE001  # REASON: malformed light position/radius descriptors should skip that light during shadow selection
            return None
    try:
        lx = float(getattr(light, "x", 0.0))
        ly = float(getattr(light, "y", 0.0))
        r = float(getattr(light, "radius", 0.0))
        if r > 0:
            return (lx, ly, r)
    except Exception:  # noqa: BLE001  # REASON: malformed fallback light position/radius attributes should skip that light during shadow selection
        return None
    return None


def select_shadow_light(manager: Any) -> tuple[str, tuple[float, float], float, Any] | None:
    """Choose the primary light for hard shadows/debug computations.

    Priority (deterministic):
        1. player dynamic light (LightSource attached to player)
        2. first dynamic light in insertion order
        3. first static light in insertion order
    """
    window = manager.window
    scene = getattr(window, "scene_controller", None)
    finder = getattr(scene, "_find_player_sprite", None) if scene is not None else None
    player = finder() if callable(finder) else None

    debug = bool(getattr(manager, "debug_geometry_enabled", False) or getattr(manager, "shadowcast_debug_enabled", False))
    skip_reasons: list[str] = []

    def _record(reason: str) -> None:
        if debug:
            skip_reasons.append(reason)

    if player is not None:
        for handle in list(manager._dynamic_handles):
            if getattr(handle, "owner", None) is not player:
                continue
            light = getattr(handle, "light", None)
            if light is None:
                _record("player_dynamic:missing_light")
                continue
            posrad = extract_light_pos_radius(light)
            if posrad is None:
                _record("player_dynamic:missing_pos_or_radius")
                continue
            lx, ly, r = posrad
            setattr(manager, "_last_shadow_light_skip_reasons", skip_reasons)
            return ("dynamic", (lx, ly), r, light)

    for handle in list(manager._dynamic_handles):
        light = getattr(handle, "light", None)
        if light is None:
            _record("dynamic:missing_light")
            continue
        posrad = extract_light_pos_radius(light)
        if posrad is None:
            _record("dynamic:missing_pos_or_radius")
            continue
        lx, ly, r = posrad
        setattr(manager, "_last_shadow_light_skip_reasons", skip_reasons)
        return ("dynamic", (lx, ly), r, light)

    for light in list(manager._static_lights):
        posrad = extract_light_pos_radius(light)
        if posrad is None:
            _record("static:missing_pos_or_radius")
            continue
        lx, ly, r = posrad
        setattr(manager, "_last_shadow_light_skip_reasons", skip_reasons)
        return ("static", (lx, ly), r, light)

    for cfg in manager._static_configs:
        if not bool(cfg.get("enabled", True)):
            continue
        if cfg.get("x") is None or cfg.get("y") is None or cfg.get("radius") is None:
            continue
        try:
            lx = float(cfg.get("x", 0.0))
            ly = float(cfg.get("y", 0.0))
            r = float(cfg.get("radius", 0.0))
            if r <= 0:
                _record("static_cfg:non_positive_radius")
                continue
            setattr(manager, "_last_shadow_light_skip_reasons", skip_reasons)
            return ("static", (lx, ly), r, cfg)
        except Exception:  # noqa: BLE001  # REASON: malformed static-light config values should skip that config during shadow selection
            _record("static_cfg:bad_values")
            continue

    setattr(manager, "_last_shadow_light_skip_reasons", skip_reasons)
    return None


def select_shadow_light_params(manager: Any) -> tuple[float, float, float] | None:
    selected = select_shadow_light(manager)
    if selected is None:
        return None
    _kind, (lx, ly), radius, _light = selected
    return (lx, ly, radius)
