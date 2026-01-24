from __future__ import annotations

import math
import os
import logging
from dataclasses import dataclass
from contextlib import nullcontext
from typing import Any, Sequence, Iterable
import engine.optional_arcade as optional_arcade
from .occluders import Rect
from engine.geometry_tools import sanitize_poly

Point = tuple[float, float]
Polygon = list[Point]

MAX_SHADOW_POLYS_PER_LIGHT = 512
_LOG_ONCE: set[str] = set()
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Viewport:
    x: float
    y: float
    width: float
    height: float


def cull_occluders_for_light(
    light_x: float,
    light_y: float,
    radius: float,
    rects: Sequence[Rect],
    *,
    debug: dict[str, Any] | None = None,
) -> list[Rect]:
    """
    Cull rect occluders conservatively using a light-centered bounding square.

    A rect is kept if it intersects the square [lx-radius, lx+radius] x [ly-radius, ly+radius].
    Iterates in input order and preserves it for determinism.
    """
    lx = float(light_x)
    ly = float(light_y)
    r = float(radius)
    if r <= 0:
        if isinstance(debug, dict):
            debug["tested_count"] = int(len(rects))
            debug["kept_count"] = 0
        return []

    left = lx - r
    right = lx + r
    bottom = ly - r
    top = ly + r

    kept: list[Rect] = []
    for rect in rects:
        rx0 = float(rect.x)
        ry0 = float(rect.y)
        rx1 = rx0 + float(rect.width)
        ry1 = ry0 + float(rect.height)
        if rx1 >= left and rx0 <= right and ry1 >= bottom and ry0 <= top:
            kept.append(rect)
    if isinstance(debug, dict):
        debug["tested_count"] = int(len(rects))
        debug["kept_count"] = int(len(kept))
    return kept


def cull_polygons_for_light(
    light_x: float,
    light_y: float,
    radius: float,
    polygons: Sequence[Polygon],
) -> list[Polygon]:
    lx = float(light_x)
    ly = float(light_y)
    r = float(radius)
    if r <= 0:
        return []

    left = lx - r
    right = lx + r
    bottom = ly - r
    top = ly + r

    kept: list[Polygon] = []
    for poly in polygons:
        if not poly:
            continue
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        if not xs or not ys:
            continue
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        if max_x >= left and min_x <= right and max_y >= bottom and min_y <= top:
            kept.append(poly)
    return kept


def build_shadow_polygons(
    light_pos: Point,
    light_radius: float,
    occluder_rects: Sequence[Rect],
) -> list[Polygon]:
    """
    Build deterministic shadow polygons by extruding an occluder's silhouette corners away from the light.

    Returns one quad per occluder: [near_a, near_b, far_b, far_a].
    """
    lx, ly = float(light_pos[0]), float(light_pos[1])
    radius = float(light_radius)
    if radius <= 0:
        return []

    rects = sorted(occluder_rects, key=lambda r: (r.y, r.x, r.height, r.width))
    polys: list[Polygon] = []

    for r in rects:
        corners: list[Point] = [
            (r.x, r.y),
            (r.x + r.width, r.y),
            (r.x + r.width, r.y + r.height),
            (r.x, r.y + r.height),
        ]

        angles: list[tuple[float, Point]] = []
        for (px, py) in corners:
            angles.append((math.atan2(py - ly, px - lx) % (2 * math.pi), (float(px), float(py))))

        angles.sort(key=lambda ap: ap[0])
        angle_values = [a for a, _ in angles]

        max_gap = -1.0
        gap_start_idx = 0
        for i in range(len(angle_values)):
            a0 = angle_values[i]
            a1 = angle_values[(i + 1) % len(angle_values)]
            gap = (a1 - a0) % (2 * math.pi)
            if gap > max_gap:
                max_gap = gap
                gap_start_idx = i

        start_idx = (gap_start_idx + 1) % len(angles)
        end_idx = gap_start_idx
        near_a = angles[start_idx][1]
        near_b = angles[end_idx][1]

        def _far(p: Point) -> Point:
            dx = p[0] - lx
            dy = p[1] - ly
            d = math.hypot(dx, dy)
            if d <= 1e-9:
                return (lx, ly)
            scale = radius / d
            return (lx + dx * scale, ly + dy * scale)

        far_a = _far(near_a)
        far_b = _far(near_b)

        poly = [near_a, near_b, far_b, far_a]
        polys.append([(round(x, 3), round(y, 3)) for x, y in poly])

    polys.sort(key=lambda p: (p[0][1], p[0][0], p[1][1], p[1][0]))
    if len(polys) > MAX_SHADOW_POLYS_PER_LIGHT:
        polys = polys[:MAX_SHADOW_POLYS_PER_LIGHT]
    return polys


def build_shadow_polygons_for_polys(
    light_pos: Point,
    light_radius: float,
    occluder_polys: Sequence[Polygon],
) -> list[Polygon]:
    lx, ly = float(light_pos[0]), float(light_pos[1])
    radius = float(light_radius)
    if radius <= 0:
        return []

    polys_out: list[Polygon] = []
    for poly in occluder_polys:
        points = sanitize_poly(poly)
        if len(points) < 3:
            continue

        angles: list[tuple[float, Point]] = []
        for (px, py) in points:
            angles.append((math.atan2(py - ly, px - lx) % (2 * math.pi), (float(px), float(py))))
        if len(angles) < 2:
            continue
        angles.sort(key=lambda ap: ap[0])
        angle_values = [a for a, _ in angles]

        max_gap = -1.0
        gap_start_idx = 0
        for i in range(len(angle_values)):
            a0 = angle_values[i]
            a1 = angle_values[(i + 1) % len(angle_values)]
            gap = (a1 - a0) % (2 * math.pi)
            if gap > max_gap:
                max_gap = gap
                gap_start_idx = i

        start_idx = (gap_start_idx + 1) % len(angles)
        end_idx = gap_start_idx
        near_a = angles[start_idx][1]
        near_b = angles[end_idx][1]

        def _far(p: Point) -> Point:
            dx = p[0] - lx
            dy = p[1] - ly
            d = math.hypot(dx, dy)
            if d <= 1e-9:
                return (lx, ly)
            scale = radius / d
            return (lx + dx * scale, ly + dy * scale)

        far_a = _far(near_a)
        far_b = _far(near_b)
        poly_out = [near_a, near_b, far_b, far_a]
        polys_out.append([(round(x, 3), round(y, 3)) for x, y in poly_out])

    polys_out.sort(key=lambda p: (p[0][1], p[0][0], p[1][1], p[1][0]))
    if len(polys_out) > MAX_SHADOW_POLYS_PER_LIGHT:
        polys_out = polys_out[:MAX_SHADOW_POLYS_PER_LIGHT]
    return polys_out


def render_shadow_mask(
    renderer: Any,
    polygons: Sequence[Polygon],
    viewport: Viewport,
    *,
    target_texture: Any | None = None,
    target_fbo: Any | None = None,
    alpha: float | int = 1.0,
    clear: bool = True,
) -> Any:
    """
    Best-effort shadow mask render hook.

    The engine currently uses Arcade's LightLayer as the primary lighting backend; this helper exists
    as a reusable rendering seam for future mask-composite paths and for tooling.

    Convention:
    - White = lit
    - Black = shadow

    If a render target API isn't available, this function draws filled shadow polygons directly
    into the active framebuffer as a best-effort fallback and returns None.
    """
    if optional_arcade.arcade is None:  # pragma: no cover
        return None

    polys = list(polygons)

    window = getattr(optional_arcade.arcade, "get_window", None)
    try:
        win = window() if callable(window) else None
    except Exception:  # noqa: BLE001
        win = None

    # Prefer the explicitly passed renderer ctx (e.g. LightManager passes the window),
    # and only fall back to a global active Arcade window if needed.
    ctx = getattr(renderer, "ctx", None) if renderer is not None else None
    if ctx is None and win is not None:
        ctx = getattr(win, "ctx", None)
    w = int(viewport.width)
    h = int(viewport.height)

    alpha_value = float(alpha)
    if alpha_value <= 1.0:
        alpha_value *= 255.0
    alpha_value = max(0.0, min(255.0, alpha_value))
    alpha_int = int(round(alpha_value))

    if ctx is not None and w > 0 and h > 0:
        backend = "none"
        mask_error: str | None = None
        activate_cm: Any | None = None
        prev_fbo: Any | None = None
        try:
            texture = target_texture if target_texture is not None else ctx.texture((w, h), components=4)
            fbo = target_fbo if target_fbo is not None else ctx.framebuffer(color_attachments=[texture])

            # Best-effort record of prior binding for restore.
            prev_fbo = getattr(ctx, "active_framebuffer", None)

            # Bind framebuffer (Arcade 3.x uses .use()).
            use = getattr(fbo, "use", None)
            if callable(use):
                backend = "fbo.use"
                use()
            else:
                activate = getattr(fbo, "activate", None)
                if callable(activate):
                    backend = "fbo.activate"
                    activate_cm = activate()
                    enter = getattr(activate_cm, "__enter__", None) if activate_cm is not None else None
                    if callable(enter):
                        enter()
                else:
                    # No known way to bind the target framebuffer.
                    try:
                        setattr(renderer, "_mesh_shadow_mask_backend", "none")
                    except Exception:  # noqa: BLE001
                        pass
                    return None

            if clear:
                # Clear to white (lit everywhere).
                cleared = False
                try:
                    clear_fn = getattr(fbo, "clear", None)
                    if callable(clear_fn):
                        try:
                            clear_fn(1.0, 1.0, 1.0, 1.0)
                        except TypeError:
                            clear_fn()
                        cleared = True
                except Exception:  # noqa: BLE001
                    cleared = False
                if not cleared:
                    try:
                        ctx.clear(1.0, 1.0, 1.0, 1.0)
                    except Exception:  # noqa: BLE001
                        pass

            # Draw shadow polys as black into the active framebuffer.
            draw_filled = getattr(optional_arcade.arcade, "draw_polygon_filled", None)
            if callable(draw_filled):
                try:
                    for poly in polys:
                        pts = [(float(x - viewport.x), float(y - viewport.y)) for x, y in poly]
                        if len(pts) < 3:
                            continue
                        draw_filled(pts, (0, 0, 0, alpha_int))
                except Exception as exc:  # noqa: BLE001
                    # Keep the cleared white mask so composite can run (lit everywhere),
                    # but expose the failure when tracing is enabled.
                    mask_error = repr(exc)
                    if os.environ.get("MESH_SHADOWS_TRACE") == "1" and "render_shadow_mask_trace" not in _LOG_ONCE:
                        logger.exception("[Mesh][Lighting] render_shadow_mask draw failed backend=%s", backend)
                        _LOG_ONCE.add("render_shadow_mask_trace")
                    else:
                        print(f"Shadow Exception: {exc}")

            try:
                setattr(renderer, "_mesh_shadow_mask_backend", backend)
            except Exception:  # noqa: BLE001
                pass
            return texture
        except Exception as exc:  # noqa: BLE001
            mask_error = repr(exc)
            if os.environ.get("MESH_SHADOWS_TRACE") == "1" and "render_shadow_mask_trace" not in _LOG_ONCE:
                logger.exception("[Mesh][Lighting] render_shadow_mask failed backend=%s", backend)
                _LOG_ONCE.add("render_shadow_mask_trace")
            try:
                setattr(renderer, "_mesh_shadow_mask_backend", backend)
            except Exception:  # noqa: BLE001
                pass
            return None
        finally:
            if mask_error is not None:
                try:
                    setattr(renderer, "_mesh_shadow_mask_error", mask_error)
                except Exception:  # noqa: BLE001
                    pass
            # Ensure activate() context managers are closed.
            if activate_cm is not None:
                exit_ = getattr(activate_cm, "__exit__", None)
                if callable(exit_):
                    try:
                        exit_(None, None, None)
                    except Exception:  # noqa: BLE001
                        pass
            # Restore framebuffer binding best-effort.
            try:
                screen = getattr(ctx, "screen", None)
                screen_use = getattr(screen, "use", None) if screen is not None else None
                if callable(screen_use):
                    screen_use()
                elif prev_fbo is not None:
                    prev_use = getattr(prev_fbo, "use", None)
                    if callable(prev_use):
                        prev_use()
            except Exception:  # noqa: BLE001
                pass

    draw_filled = getattr(optional_arcade.arcade, "draw_polygon_filled", None)
    if not callable(draw_filled):
        return None
    vx = float(getattr(viewport, "x", 0.0) or 0.0)
    vy = float(getattr(viewport, "y", 0.0) or 0.0)
    for poly in polys:
        pts = [(float(x - vx), float(y - vy)) for x, y in poly]
        if len(pts) < 3:
            continue
        draw_filled(pts, (0, 0, 0, alpha_int))
    return None
