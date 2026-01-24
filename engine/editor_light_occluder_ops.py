from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, cast

LIGHT_COLOR_PRESETS: list[str] = [
    "#ffffff",  # white
    "#ffddaa",  # warm
    "#88bbff",  # cold
    "#ff5555",  # red
    "#66ff66",  # green
    "#5599ff",  # blue
]

COOKIE_PRESETS: list[str | None] = [None, "torch", "window", "water"]

LIGHTING_PRESETS: dict[str, dict[str, Any]] = {
    "torch_cave": {
        "ambient_light_rgba": [255, 180, 120, 255],
        "ambient_darkness_alpha": 230,
        "default_light_color_rgba": [255, 200, 140, 255],
        "default_flicker_enabled": True,
    },
    "moonlight": {
        "ambient_light_rgba": [140, 170, 255, 255],
        "ambient_darkness_alpha": 210,
        "default_light_color_rgba": [180, 200, 255, 255],
        "default_flicker_enabled": False,
    },
    "toxic_horror": {
        "ambient_light_rgba": [120, 255, 160, 255],
        "ambient_darkness_alpha": 240,
        "default_light_color_rgba": [140, 255, 180, 255],
        "default_flicker_enabled": True,
    },
    "hospital_white": {
        "ambient_light_rgba": [255, 255, 255, 255],
        "ambient_darkness_alpha": 200,
        "default_light_color_rgba": [255, 255, 255, 255],
        "default_flicker_enabled": False,
    },
}

LIGHTING_PRESET_ORDER: list[str] = [
    "torch_cave",
    "moonlight",
    "toxic_horror",
    "hospital_white",
]


@dataclass(frozen=True)
class OccluderEditCommand:
    kind: str
    payload: dict[str, Any]


def ensure_scene_lights(scene: dict[str, Any]) -> list[dict[str, Any]]:
    lights = scene.setdefault("lights", [])
    if not isinstance(lights, list):
        scene["lights"] = []
        lights = scene["lights"]
    return cast(list[dict[str, Any]], lights)


def ensure_scene_occluders(scene: dict[str, Any]) -> list[dict[str, Any]]:
    occluders = scene.setdefault("occluders", [])
    if not isinstance(occluders, list):
        scene["occluders"] = []
        occluders = scene["occluders"]
    return cast(list[dict[str, Any]], occluders)


def new_light_payload(
    x: float,
    y: float,
    *,
    default_color_rgba: list[int] | None = None,
    default_flicker_enabled: bool | None = None,
) -> dict[str, Any]:
    color_rgba = None
    if isinstance(default_color_rgba, list) and len(default_color_rgba) >= 3:
        try:
            color_rgba = [int(default_color_rgba[0]), int(default_color_rgba[1]), int(default_color_rgba[2]), int(default_color_rgba[3]) if len(default_color_rgba) > 3 else 255]
        except Exception:  # noqa: BLE001
            color_rgba = None
    return {
        "x": float(x),
        "y": float(y),
        "radius": 160.0,
        "color": LIGHT_COLOR_PRESETS[1],
        "color_rgba": color_rgba,
        "mode": "soft",
        "flicker_enabled": bool(default_flicker_enabled) if default_flicker_enabled is not None else False,
        "cookie_id": None,
        "cookie_scale": 1.0,
        "cookie_rotation_deg": 0.0,
        "cookie_offset_px": (0.0, 0.0),
    }


def add_light(scene: dict[str, Any], x: float, y: float) -> tuple[int, dict[str, Any]]:
    lights = ensure_scene_lights(scene)
    settings = scene.get("settings")
    default_color = None
    default_flicker = None
    if isinstance(settings, dict):
        default_color = settings.get("default_light_color_rgba")
        default_flicker = settings.get("default_flicker_enabled")
    light = new_light_payload(x, y, default_color_rgba=default_color, default_flicker_enabled=default_flicker)
    lights.append(light)
    return len(lights) - 1, light


def cycle_light_color(light: dict[str, Any], palette: list[str] | None = None) -> tuple[str | None, str]:
    if palette is None:
        palette = LIGHT_COLOR_PRESETS
    old_color = light.get("color")
    old_text = str(old_color) if isinstance(old_color, str) else palette[0]
    try:
        idx = palette.index(old_text)
    except ValueError:
        idx = -1
    new_color = palette[(idx + 1) % len(palette)]
    light["color"] = new_color
    return old_text, new_color


def toggle_light_flicker(light: dict[str, Any]) -> tuple[bool, bool]:
    old_value = bool(light.get("flicker_enabled", False))
    new_value = not old_value
    light["flicker_enabled"] = new_value
    return old_value, new_value


def cycle_light_cookie(light: dict[str, Any], cookies: list[str | None] | None = None) -> tuple[str | None, str | None]:
    if cookies is None:
        cookies = COOKIE_PRESETS
    old_cookie = light.get("cookie_id")
    normalized = None
    if isinstance(old_cookie, str) and old_cookie.strip():
        normalized = old_cookie.strip()
    try:
        idx = cookies.index(normalized)
    except ValueError:
        idx = -1
    new_cookie = cookies[(idx + 1) % len(cookies)]
    light["cookie_id"] = new_cookie
    return normalized, new_cookie


def _normalize_points(points: list[tuple[float, float]]) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in points]


def next_occluder_id(occluders: list[dict[str, Any]]) -> str:
    base = "occ"
    used = set()
    for occ in occluders:
        if isinstance(occ, dict):
            oid = occ.get("id")
            if isinstance(oid, str) and oid.strip():
                used.add(oid.strip())
    idx = 1
    while True:
        candidate = f"{base}_{idx}"
        if candidate not in used:
            return candidate
        idx += 1


def add_occluder(scene: dict[str, Any], points: list[tuple[float, float]]) -> tuple[int, dict[str, Any]]:
    occluders = ensure_scene_occluders(scene)
    payload = {
        "type": "poly",
        "id": next_occluder_id(occluders),
        "points": _normalize_points(points),
    }
    occluders.append(payload)
    return len(occluders) - 1, payload


def update_occluder_point(
    occluders: list[dict[str, Any]], occ_idx: int, point_idx: int, point: tuple[float, float]
) -> tuple[list[float] | None, list[float]]:
    if not (0 <= occ_idx < len(occluders)):
        return None, [float(point[0]), float(point[1])]
    occ = occluders[occ_idx]
    points = occ.get("points")
    if not isinstance(points, list) or not (0 <= point_idx < len(points)):
        return None, [float(point[0]), float(point[1])]
    before = points[point_idx]
    after = [float(point[0]), float(point[1])]
    points[point_idx] = after
    return before if isinstance(before, list) else None, after


def build_add_point_cmd(
    *,
    occ_index: int,
    point_index: int,
    point: tuple[float, float],
    occ_id: str | None = None,
) -> OccluderEditCommand:
    return OccluderEditCommand(
        kind="add_point",
        payload={
            "occ_index": int(occ_index),
            "point_index": int(point_index),
            "point": [float(point[0]), float(point[1])],
            "occ_id": occ_id,
        },
    )


def build_remove_point_cmd(
    *,
    occ_index: int,
    point_index: int,
    point: list[float],
    occ_id: str | None = None,
) -> OccluderEditCommand:
    return OccluderEditCommand(
        kind="remove_point",
        payload={
            "occ_index": int(occ_index),
            "point_index": int(point_index),
            "point": list(point),
            "occ_id": occ_id,
        },
    )


def build_move_point_cmd(
    *,
    occ_index: int,
    point_index: int,
    before: list[float],
    after: list[float],
    occ_id: str | None = None,
) -> OccluderEditCommand:
    return OccluderEditCommand(
        kind="move_point",
        payload={
            "occ_index": int(occ_index),
            "point_index": int(point_index),
            "before": list(before),
            "after": list(after),
            "occ_id": occ_id,
        },
    )


def build_insert_point_cmd(
    *,
    occ_index: int,
    insert_index: int,
    point: tuple[float, float],
    occ_id: str | None = None,
) -> OccluderEditCommand:
    return OccluderEditCommand(
        kind="insert_point",
        payload={
            "occ_index": int(occ_index),
            "insert_index": int(insert_index),
            "point": [float(point[0]), float(point[1])],
            "occ_id": occ_id,
        },
    )


def build_finish_polygon_cmd(*, index: int, occluder: dict[str, Any]) -> OccluderEditCommand:
    return OccluderEditCommand(
        kind="finish_polygon",
        payload={
            "index": int(index),
            "occluder": dict(occluder),
            "occ_id": occluder.get("id"),
        },
    )


def build_delete_polygon_cmd(*, index: int, occluder: dict[str, Any]) -> OccluderEditCommand:
    return OccluderEditCommand(
        kind="delete_polygon",
        payload={
            "index": int(index),
            "occluder": dict(occluder),
            "occ_id": occluder.get("id"),
        },
    )


def _coerce_cmd(cmd: OccluderEditCommand | dict[str, Any]) -> OccluderEditCommand:
    if isinstance(cmd, OccluderEditCommand):
        return cmd
    kind = str(cmd.get("kind") or "")
    payload = cmd.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return OccluderEditCommand(kind=kind, payload=dict(payload))


def _resolve_occluder_index(occluders: list[dict[str, Any]], payload: dict[str, Any]) -> int | None:
    index = payload.get("occ_index")
    if isinstance(index, int) and 0 <= index < len(occluders):
        return index
    index = payload.get("index")
    if isinstance(index, int) and 0 <= index < len(occluders):
        return index
    occ_id = payload.get("occ_id")
    if isinstance(occ_id, str) and occ_id:
        for idx, occ in enumerate(occluders):
            if isinstance(occ, dict) and occ.get("id") == occ_id:
                return idx
    return None


def apply_occluder_command(scene: dict[str, Any], cmd: OccluderEditCommand | dict[str, Any]) -> None:
    command = _coerce_cmd(cmd)
    occluders = ensure_scene_occluders(scene)
    payload = command.payload
    kind = command.kind

    if kind == "finish_polygon":
        index = payload.get("index")
        occluder = payload.get("occluder")
        if not isinstance(occluder, dict):
            return
        if isinstance(index, int) and 0 <= index <= len(occluders):
            occluders.insert(index, dict(occluder))
        else:
            occluders.append(dict(occluder))
        return

    if kind == "delete_polygon":
        idx = _resolve_occluder_index(occluders, payload)
        if idx is None:
            return
        occluders.pop(idx)
        return

    idx = _resolve_occluder_index(occluders, payload)
    if idx is None:
        return
    occ = occluders[idx]
    points = occ.get("points")
    if not isinstance(points, list):
        return

    if kind == "add_point":
        point = payload.get("point")
        if not isinstance(point, list) or len(point) != 2:
            return
        insert_at = payload.get("point_index")
        if isinstance(insert_at, int) and 0 <= insert_at <= len(points):
            points.insert(insert_at, list(point))
        else:
            points.append(list(point))
        return

    if kind == "remove_point":
        point_index = payload.get("point_index")
        if not isinstance(point_index, int) or not (0 <= point_index < len(points)):
            return
        points.pop(point_index)
        return

    if kind == "insert_point":
        point = payload.get("point")
        insert_index = payload.get("insert_index")
        if not isinstance(point, list) or len(point) != 2:
            return
        if not isinstance(insert_index, int) or not (0 <= insert_index <= len(points)):
            return
        points.insert(insert_index, list(point))
        return

    if kind == "move_point":
        point_index = payload.get("point_index")
        after = payload.get("after")
        if not isinstance(point_index, int) or not (0 <= point_index < len(points)):
            return
        if not isinstance(after, list) or len(after) != 2:
            return
        points[point_index] = list(after)


def invert_occluder_command(cmd: OccluderEditCommand | dict[str, Any]) -> OccluderEditCommand:
    command = _coerce_cmd(cmd)
    payload = dict(command.payload)
    kind = command.kind
    if kind == "finish_polygon":
        return OccluderEditCommand(kind="delete_polygon", payload=payload)
    if kind == "delete_polygon":
        return OccluderEditCommand(kind="finish_polygon", payload=payload)
    if kind == "add_point":
        return OccluderEditCommand(kind="remove_point", payload=payload)
    if kind == "remove_point":
        return OccluderEditCommand(kind="add_point", payload=payload)
    if kind == "insert_point":
        payload["point_index"] = payload.get("insert_index")
        return OccluderEditCommand(kind="remove_point", payload=payload)
    if kind == "move_point":
        before = payload.get("before")
        after = payload.get("after")
        payload["before"] = after
        payload["after"] = before
        return OccluderEditCommand(kind="move_point", payload=payload)
    return OccluderEditCommand(kind=kind, payload=payload)


def find_closest_edge_insert_index(
    polygon_points: list[tuple[float, float]] | list[list[float]],
    world_point: tuple[float, float],
) -> tuple[int, tuple[float, float]]:
    if not polygon_points:
        return (0, (float(world_point[0]), float(world_point[1])))
    points = []
    for entry in polygon_points:
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            try:
                points.append((float(entry[0]), float(entry[1])))
            except Exception:  # noqa: BLE001
                continue
    if len(points) < 2:
        return (len(points), (float(world_point[0]), float(world_point[1])))

    wx = float(world_point[0])
    wy = float(world_point[1])
    best_idx = 0
    best_dist = float("inf")
    best_proj = (wx, wy)
    count = len(points)
    for i in range(count):
        ax, ay = points[i]
        bx, by = points[(i + 1) % count]
        vx = bx - ax
        vy = by - ay
        wxv = wx - ax
        wyv = wy - ay
        denom = vx * vx + vy * vy
        if denom <= 1e-12:
            t = 0.0
        else:
            t = (wxv * vx + wyv * vy) / denom
            t = max(0.0, min(1.0, t))
        proj_x = ax + t * vx
        proj_y = ay + t * vy
        dx = wx - proj_x
        dy = wy - proj_y
        dist = dx * dx + dy * dy
        if dist < best_dist or (math.isclose(dist, best_dist) and i < best_idx):
            best_dist = dist
            best_idx = i
            best_proj = (proj_x, proj_y)
    insert_index = best_idx + 1
    if insert_index < 0:
        insert_index = 0
    if insert_index > len(points):
        insert_index = len(points)
    return insert_index, best_proj


def snap_world_point(
    point: tuple[float, float],
    mode: str,
    tile_size_px: int | None,
) -> tuple[float, float]:
    x = float(point[0])
    y = float(point[1])
    mode = str(mode or "").lower()
    if mode == "grid8":
        step = 8.0
    elif mode == "grid16":
        step = 16.0
    elif mode == "tile_center":
        if tile_size_px is None or tile_size_px <= 0:
            step = 16.0
            return (round(x / step) * step, round(y / step) * step)
        size = float(tile_size_px)
        cx = round(x / size - 0.5) + 0.5
        cy = round(y / size - 0.5) + 0.5
        return (cx * size, cy * size)
    else:
        return (x, y)
    return (round(x / step) * step, round(y / step) * step)


def update_light_property(
    scene: dict[str, Any],
    light_id: int | str,
    prop_name: str,
    new_value: Any,
) -> bool:
    lights = ensure_scene_lights(scene)
    index: int | None = None
    if isinstance(light_id, int):
        if 0 <= light_id < len(lights):
            index = light_id
    elif isinstance(light_id, str):
        for idx, light in enumerate(lights):
            if isinstance(light, dict) and light.get("id") == light_id:
                index = idx
                break
    if index is None:
        return False
    light = lights[index]
    if not isinstance(light, dict):
        return False

    prop_name = str(prop_name or "")
    key = "radius" if prop_name == "radius_px" else prop_name

    try:
        value = float(new_value)
    except Exception:  # noqa: BLE001
        return False

    if key == "radius":
        value = max(8.0, value)
    elif key == "flicker_amount":
        value = max(0.0, min(1.0, value))
    elif key == "flicker_speed":
        value = max(0.0, value)
    elif key == "cookie_scale":
        value = max(0.0, value)
    elif key == "cookie_rotation_deg":
        value = value % 360.0

    light[key] = value
    return True


def apply_lighting_preset(scene: dict[str, Any], preset_id: str) -> dict[str, Any]:
    preset_id = str(preset_id or "")
    preset = LIGHTING_PRESETS.get(preset_id)
    if preset is None:
        settings = scene.get("settings")
        if isinstance(settings, dict):
            custom = settings.get("custom_lighting_presets")
            if isinstance(custom, dict):
                candidate = custom.get(preset_id)
                if isinstance(candidate, dict):
                    preset = candidate
    if preset is None:
        return scene
    settings = scene.get("settings")
    if not isinstance(settings, dict):
        settings = {}
        scene["settings"] = settings
    if "ambient_light_rgba" in preset:
        settings["ambient_light_rgba"] = list(preset["ambient_light_rgba"])
    if "ambient_darkness_alpha" in preset:
        settings["ambient_darkness_alpha"] = int(preset["ambient_darkness_alpha"])
    if "default_light_color_rgba" in preset:
        settings["default_light_color_rgba"] = list(preset["default_light_color_rgba"])
    if "default_flicker_enabled" in preset:
        settings["default_flicker_enabled"] = bool(preset["default_flicker_enabled"])
    return scene


def capture_lighting_preset(scene: dict[str, Any], slot: str) -> dict[str, Any]:
    slot = str(slot or "")
    if slot not in ("custom_1", "custom_2"):
        return scene
    settings = scene.get("settings")
    if not isinstance(settings, dict):
        settings = {}
        scene["settings"] = settings
    preset: dict[str, Any] = {}
    if "ambient_light_rgba" in settings:
        preset["ambient_light_rgba"] = list(settings["ambient_light_rgba"])
    if "ambient_darkness_alpha" in settings:
        preset["ambient_darkness_alpha"] = int(settings["ambient_darkness_alpha"])
    if "default_light_color_rgba" in settings:
        preset["default_light_color_rgba"] = list(settings["default_light_color_rgba"])
    if "default_flicker_enabled" in settings:
        preset["default_flicker_enabled"] = bool(settings["default_flicker_enabled"])
    custom = settings.get("custom_lighting_presets")
    if not isinstance(custom, dict):
        custom = {}
        settings["custom_lighting_presets"] = custom
    custom[slot] = preset
    return scene
