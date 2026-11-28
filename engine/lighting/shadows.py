from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import engine.optional_arcade as optional_arcade
from engine.arcade_compat import (
    capture_active_framebuffer,
    clear_framebuffer,
    close_framebuffer_activation,
    restore_framebuffer,
)
from engine.geometry_tools import sanitize_poly
from engine.swallowed_exceptions import _log_swallow, record_swallowed

from .occluders import Rect
from .shadow_backend import (
    ShadowBackendDecision,
    build_shadow_pipeline,
    choose_shadow_backend,
    decision_to_diagnostics,
)

Point = tuple[float, float]
Polygon = list[Point]

MAX_SHADOW_POLYS_PER_LIGHT = 512
_LAST_SHADOW_BACKEND_DIAGNOSTICS: dict[str, object] = {
    "schema_version": 1,
    "selected": "none",
    "reason": "uninitialized",
    "fallbacks": [],
}


@dataclass(frozen=True, slots=True)
class Viewport:
    x: float
    y: float
    width: float
    height: float


def _set_shadow_backend_diagnostics(decision: ShadowBackendDecision) -> None:
    global _LAST_SHADOW_BACKEND_DIAGNOSTICS
    _LAST_SHADOW_BACKEND_DIAGNOSTICS = decision_to_diagnostics(decision)


def get_shadow_backend_diagnostics() -> dict[str, object]:
    raw_fallbacks = _LAST_SHADOW_BACKEND_DIAGNOSTICS.get("fallbacks", [])
    if isinstance(raw_fallbacks, (list, tuple)):
        fallbacks = [str(item) for item in raw_fallbacks]
    else:
        fallbacks = []
    return {
        "schema_version": 1,
        "selected": str(_LAST_SHADOW_BACKEND_DIAGNOSTICS.get("selected", "none")),
        "reason": str(_LAST_SHADOW_BACKEND_DIAGNOSTICS.get("reason", "")),
        "fallbacks": fallbacks,
    }


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


def _shadow_behind(lx: float, ly: float, radius: float, near_a: Point, near_b: Point) -> Polygon:
    """The shadow an occluder's silhouette edge ``near_a``-``near_b`` throws away from the light at (lx, ly).

    It covers what the light would have lit behind the edge and nothing more: out to the light's reach, along an
    arc so a wide edge's shadow follows the light's circle. Past the reach only the room's own ambient light falls,
    and a shadow drawn there showed as black beams across the map. A corner already beyond the reach keeps its
    place (the arc goes out to it): pulling it back onto the radius put the shadow between the light and the
    wall, over the lit floor.
    """

    def unit(p: Point) -> tuple[float, float, float]:
        dx, dy = p[0] - lx, p[1] - ly
        d = math.hypot(dx, dy)
        return (dx / d, dy / d, d) if d > 1e-9 else (0.0, 0.0, 0.0)

    ax, ay, da = unit(near_a)
    bx, by, db = unit(near_b)
    if da == 0.0 or db == 0.0:  # the light sits on a corner: nothing sensible to cast
        return [near_a, near_b, (lx, ly)]
    reach = max(radius, da, db)
    start, turn = math.atan2(by, bx), math.atan2(ay, ax) - math.atan2(by, bx)
    turn = (turn + math.pi) % (2 * math.pi) - math.pi  # from b round to a, the short way (through the shadow)
    steps = max(1, math.ceil(abs(turn) / math.radians(15)))
    arc = [(lx + math.cos(start + turn * i / steps) * reach, ly + math.sin(start + turn * i / steps) * reach)
           for i in range(steps + 1)]
    return [near_a, near_b, *arc]


def build_shadow_polygons(
    light_pos: Point,
    light_radius: float,
    occluder_rects: Sequence[Rect],
) -> list[Polygon]:
    """
    Build deterministic shadow polygons by extruding an occluder's silhouette corners away from the light.

    Returns one polygon per occluder: its near edge, then an arc at the light's reach behind it.
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

        poly = _shadow_behind(lx, ly, radius, near_a, near_b)
        polys.append([(round(x, 3), round(y, 3)) for x, y in poly])

    polys.sort(key=lambda p: (p[0][1], p[0][0], p[1][1], p[1][0]))
    if len(polys) > MAX_SHADOW_POLYS_PER_LIGHT:
        polys = polys[:MAX_SHADOW_POLYS_PER_LIGHT]
    return polys


def _inside_polygon(x: float, y: float, points: Sequence[Point]) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(points, [*points[1:], points[0]]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def light_shadow_polygons(
    light_pos: Point,
    light_radius: float,
    occluder_rects: Sequence[Rect],
    occluder_polys: Sequence[Polygon],
) -> list[Polygon]:
    """Every shadow one light throws, for a renderer that masks that light alone (light_compositor).

    Shadows only remove their own light, so they may run past its reach. All of them end on one arc,
    beyond the farthest corner in play, so two shadows meeting along a ray share their end points (no
    cracks between neighbouring walls). A polygon's back edges each throw an arc-ended shadow (a straight
    end inside the light's circle left a lit wedge behind long edges). An occluder the light is inside
    casts nothing: there is no sensible shadow from within a wall.
    """
    lx, ly = float(light_pos[0]), float(light_pos[1])
    if float(light_radius) <= 0:
        return []
    rects = [r for r in occluder_rects if not (r.x < lx < r.x + r.width and r.y < ly < r.y + r.height)]
    polys = [p for p in (sanitize_poly(poly) for poly in occluder_polys) if len(p) >= 3 and not _inside_polygon(lx, ly, p)]
    corners = [pt for r in rects for pt in ((r.x, r.y), (r.x + r.width, r.y + r.height), (r.x + r.width, r.y), (r.x, r.y + r.height))]
    corners += [pt for p in polys for pt in p]
    reach = max([float(light_radius), *(math.hypot(px - lx, py - ly) for px, py in corners)]) + 1.0
    # Rectangles cast like polygons, from their back edges: a shadow starting at the chord between the two
    # outermost corners covered part of the wall itself (all of it when lit from straight on).
    shapes = [[(r.x, r.y), (r.x + r.width, r.y), (r.x + r.width, r.y + r.height), (r.x, r.y + r.height)] for r in rects]
    joined = _same_wall(rects)
    out: list[Polygon] = []
    for index, points in enumerate(shapes + polys):
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, [*points[1:], points[0]]))
        if area == 0:
            continue
        neighbours = [rects[j] for j in joined[index]] if index < len(rects) else []
        for p0, p1 in zip(points, [*points[1:], points[0]]):
            # An edge facing away from the light (its outward side away from it) throws the shadow.
            ex, ey = p1[0] - p0[0], p1[1] - p0[1]
            nx, ny = (ey, -ex) if area > 0 else (-ey, ex)
            if nx * (lx - p0[0]) + ny * (ly - p0[1]) >= 0:
                continue
            pieces = [_shadow_behind(lx, ly, reach, p0, p1)]
            for other in neighbours:  # one wall never shadows its own face (an L of tiles is several rectangles)
                pieces = [part for piece in pieces for part in _minus_rect(piece, other)]
            out.extend([(round(x, 3), round(y, 3)) for x, y in piece] for piece in pieces)
    return out


def _same_wall(rects: Sequence[Rect]) -> list[list[int]]:
    """For each rectangle, the others it touches through a chain of touching rectangles: one painted wall."""
    group = list(range(len(rects)))

    def root(i: int) -> int:
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    for i, a in enumerate(rects):  # ponytail: O(n^2) over the light's nearby rectangles (merged strips: few)
        for j in range(i + 1, len(rects)):
            b = rects[j]
            if a.x <= b.x + b.width and b.x <= a.x + a.width and a.y <= b.y + b.height and b.y <= a.y + a.height:
                group[root(i)] = root(j)
    members: dict[int, list[int]] = {}
    for i in range(len(rects)):
        members.setdefault(root(i), []).append(i)
    return [[j for j in members[root(i)] if j != i] for i in range(len(rects))]


def _clip(poly: Polygon, keep: Callable[[Point], float]) -> Polygon:
    """The part of a convex polygon where ``keep`` is >= 0 (a half-plane; Sutherland-Hodgman)."""
    out: Polygon = []
    for a, b in zip(poly, [*poly[1:], poly[0]]):
        ka, kb = keep(a), keep(b)
        if ka >= 0:
            out.append(a)
        if (ka >= 0) != (kb >= 0):
            t = ka / (ka - kb)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def _minus_rect(poly: Polygon, r: Rect) -> list[Polygon]:
    """A convex polygon less a rectangle: up to four convex pieces (left, right, below, above it)."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    if max(xs) <= r.x or min(xs) >= r.x + r.width or max(ys) <= r.y or min(ys) >= r.y + r.height:
        return [poly]
    x0, x1, y0, y1 = r.x, r.x + r.width, r.y, r.y + r.height
    pieces = [_clip(poly, lambda p: x0 - p[0])]
    rest = _clip(poly, lambda p: p[0] - x0)
    pieces.append(_clip(rest, lambda p: p[0] - x1))
    rest = _clip(rest, lambda p: x1 - p[0])
    pieces.append(_clip(rest, lambda p: y0 - p[1]))
    pieces.append(_clip(_clip(rest, lambda p: p[1] - y0), lambda p: p[1] - y1))
    return [piece for piece in pieces if len(piece) >= 3 and abs(sum(
        ax * by - bx * ay for (ax, ay), (bx, by) in zip(piece, [*piece[1:], piece[0]]))) > 1e-6]


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

        poly_out = _shadow_behind(lx, ly, radius, near_a, near_b)
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
        _set_shadow_backend_diagnostics(
            ShadowBackendDecision(
                name="none",
                reason="arcade unavailable",
                fallbacks=[],
                ok=False,
            )
        )
        return None

    polys = list(polygons)

    window = getattr(optional_arcade.arcade, "get_window", None)
    try:
        win = window() if callable(window) else None
    except Exception:  # noqa: BLE001  # REASON: lighting fallback isolation
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
            prev_fbo = capture_active_framebuffer(ctx)
            decision = choose_shadow_backend(
                env=os.environ,
                flags=None,
                capabilities={
                    "has_use": callable(getattr(fbo, "use", None)),
                    "has_activate": callable(getattr(fbo, "activate", None)),
                },
            )
            _set_shadow_backend_diagnostics(decision)
            pipeline = build_shadow_pipeline(decision, texture=texture, fbo=fbo)
            backend = decision.name
            activate_cm = pipeline.activate_cm
            if not decision.ok:
                try:
                    setattr(renderer, "_mesh_shadow_mask_backend", "none")
                except Exception:  # noqa: BLE001  # REASON: lighting fallback isolation
                    _log_swallow("SHAD-001", "engine/lighting/shadows.py pass-only blanket swallow")
                    pass
                return None

            if clear:
                # Clear to white (lit everywhere).
                clear_framebuffer(ctx, fbo, 1.0, 1.0, 1.0, 1.0)

            # Draw shadow polys as black into the active framebuffer.
            draw_filled = getattr(optional_arcade.arcade, "draw_polygon_filled", None)
            if callable(draw_filled):
                try:
                    for poly in polys:
                        pts = [(float(x - viewport.x), float(y - viewport.y)) for x, y in poly]
                        if len(pts) < 3:
                            continue
                        draw_filled(pts, (0, 0, 0, alpha_int))
                except Exception as exc:  # noqa: BLE001  # REASON: lighting fallback isolation
                    # Keep the cleared white mask so composite can run (lit everywhere),
                    # but expose the failure when tracing is enabled.
                    record_swallowed("engine.lighting.shadows.render_shadow_mask.draw_polygons", exc)
                    mask_error = repr(exc)
                    if os.environ.get("MESH_SHADOWS_TRACE") == "1":
                        _log_swallow("render_shadow_mask_trace", f"render_shadow_mask draw failed backend={backend}")
                    else:
                        print(f"Shadow Exception: {exc}")

            try:
                setattr(renderer, "_mesh_shadow_mask_backend", backend)
            except Exception:  # noqa: BLE001  # REASON: lighting fallback isolation
                _log_swallow("SHAD-002", "engine/lighting/shadows.py pass-only blanket swallow")
                pass
            return texture
        except Exception as exc:  # noqa: BLE001  # REASON: lighting fallback isolation
            record_swallowed("engine.lighting.shadows.render_shadow_mask.fbo_path", exc)
            mask_error = repr(exc)
            if os.environ.get("MESH_SHADOWS_TRACE") == "1":
                _log_swallow("render_shadow_mask_trace", f"render_shadow_mask failed backend={backend}")
            try:
                setattr(renderer, "_mesh_shadow_mask_backend", backend)
            except Exception:  # noqa: BLE001  # REASON: lighting fallback isolation
                _log_swallow("SHAD-003", "engine/lighting/shadows.py pass-only blanket swallow")
                pass
            return None
        finally:
            if mask_error is not None:
                try:
                    setattr(renderer, "_mesh_shadow_mask_error", mask_error)
                except Exception:  # noqa: BLE001  # REASON: lighting fallback isolation
                    _log_swallow("SHAD-004", "engine/lighting/shadows.py pass-only blanket swallow")
                    pass
            # Ensure activate() context managers are closed.
            close_framebuffer_activation(activate_cm)
            # Restore framebuffer binding best-effort.
            restore_framebuffer(ctx, prev_fbo)

    draw_filled = getattr(optional_arcade.arcade, "draw_polygon_filled", None)
    if not callable(draw_filled):
        _set_shadow_backend_diagnostics(
            ShadowBackendDecision(
                name="none",
                reason="draw_polygon_filled unavailable",
                fallbacks=[],
                ok=False,
            )
        )
        return None
    _set_shadow_backend_diagnostics(
        ShadowBackendDecision(
            name="none",
            reason="direct draw fallback",
            fallbacks=[],
            ok=True,
        )
    )
    vx = float(getattr(viewport, "x", 0.0) or 0.0)
    vy = float(getattr(viewport, "y", 0.0) or 0.0)
    for poly in polys:
        pts = [(float(x - vx), float(y - vy)) for x, y in poly]
        if len(pts) < 3:
            continue
        draw_filled(pts, (0, 0, 0, alpha_int))
    return None
