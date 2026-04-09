import argparse
import json
from pathlib import Path

from engine.path_norm import normalize_scene_path
from engine.paths import resolve_path
from engine.persistence_io import write_json_atomic
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload


def _handle_scene_validate_backgrounds(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    normalized_scene_path = normalize_scene_path(scene_path)
    path = Path(scene_path)
    if not path.exists():
        print(f"[Mesh][CLI] Error: scene not found: {normalized_scene_path}")
        return 1

    try:
        scene = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # REASON: scene backgrounds CLI should report scene JSON parse failures deterministically before validation begins
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {normalized_scene_path}: {exc}")
        return 1

    if not isinstance(scene, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {normalized_scene_path}")
        return 1

    errors: list[tuple[str, str, str, str]] = []

    def add_error(layer_id: str, field: str, message: str) -> None:
        errors.append((normalized_scene_path, str(layer_id or ""), str(field), str(message)))

    raw_layers = scene.get("background_layers")
    if raw_layers is None:
        print(f"[Mesh][CLI] OK: {normalized_scene_path} has no background_layers")
        return 0
    if not isinstance(raw_layers, list):
        add_error("", "background_layers", "must be an array")
        raw_layers = []

    seen: set[str] = set()
    for idx, entry in enumerate(raw_layers):
        if not isinstance(entry, dict):
            add_error("", f"background_layers[{idx}]", "must be an object")
            continue
        layer_id = entry.get("id")
        if not isinstance(layer_id, str) or not layer_id.strip():
            add_error("", f"background_layers[{idx}].id", "must be a non-empty string")
            continue
        layer_id = layer_id.strip()
        if layer_id in seen:
            add_error(layer_id, "id", "duplicate id")
        seen.add(layer_id)

        path_value = entry.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            add_error(layer_id, "path", "must be a non-empty string")

        z_value = entry.get("z")
        if not isinstance(z_value, int):
            add_error(layer_id, "z", "must be an int")

        parallax_value = entry.get("parallax")
        if parallax_value is not None:
            try:
                parallax = float(parallax_value)
            except (TypeError, ValueError):
                add_error(layer_id, "parallax", "must be a number")
            else:
                if not (0.0 <= parallax <= 2.0):
                    add_error(layer_id, "parallax", "must be within [0, 2]")

        repeat_x_value = entry.get("repeat_x")
        if repeat_x_value is not None and not isinstance(repeat_x_value, bool):
            add_error(layer_id, "repeat_x", "must be a boolean")

        repeat_y_value = entry.get("repeat_y")
        if repeat_y_value is not None and not isinstance(repeat_y_value, bool):
            add_error(layer_id, "repeat_y", "must be a boolean")

        # Backward compatibility for legacy `repeat` (treated as repeat_x).
        repeat_value = entry.get("repeat")
        if repeat_value is not None and not isinstance(repeat_value, bool):
            add_error(layer_id, "repeat", "must be a boolean")

    errors.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    if errors:
        for scene_id, layer_id, field, message in errors:
            layer_label = layer_id or "-"
            print(f"[Mesh][Backgrounds] ERROR: {scene_id} :: {layer_label} :: {field} :: {message}")
        return 1

    print(f"[Mesh][CLI] OK: {normalized_scene_path} background_layers validated")
    return 0


def _handle_scene_backgrounds_add_layer(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    layer_id = str(getattr(args, "id", "") or "").strip()
    if not layer_id:
        print("[Mesh][CLI] Error: missing --id")
        return 2

    layer_path = str(getattr(args, "path", "") or "").strip()
    if not layer_path:
        print("[Mesh][CLI] Error: missing --path")
        return 2

    z = int(getattr(args, "z"))
    parallax = float(getattr(args, "parallax", 1.0))

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # REASON: background layer list CLI should report scene JSON parse failures deterministically before inspecting layers
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1
    if not isinstance(data, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    layers = data.get("background_layers")
    if layers is None:
        layers = []
        data["background_layers"] = layers
    if not isinstance(layers, list):
        print(f"[Mesh][CLI] Error: background_layers must be a list: {scene_path}")
        return 1

    existing = next((e for e in layers if isinstance(e, dict) and e.get("id") == layer_id), None)
    repeat_x = bool(getattr(args, "repeat_x", False))
    repeat_y = bool(getattr(args, "repeat_y", False))

    desired = {
        "id": layer_id,
        "path": layer_path,
        "z": int(z),
        "parallax": float(parallax),
        "repeat_x": bool(repeat_x),
        "repeat_y": bool(repeat_y),
    }

    changed = False
    if existing is None:
        layers.append(dict(desired))
        changed = True
    else:
        if not isinstance(existing, dict):
            print(f"[Mesh][CLI] Error: background layer must be an object: {scene_path} id={layer_id}")
            return 1
        for key, value in desired.items():
            if existing.get(key) != value:
                existing[key] = value
                changed = True

    if not changed:
        return 0

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(data)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after insert: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_scene_backgrounds_remove_layer(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    layer_id = str(getattr(args, "id", "") or "").strip()
    if not layer_id:
        print("[Mesh][CLI] Error: missing --id")
        return 2

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # REASON: background layer edit CLI should report scene JSON parse failures deterministically before mutating layers
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1
    if not isinstance(data, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    layers = data.get("background_layers")
    if not isinstance(layers, list):
        return 0

    before = len(layers)
    data["background_layers"] = [e for e in layers if not (isinstance(e, dict) and e.get("id") == layer_id)]
    if len(data["background_layers"]) == before:
        return 0

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(data)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after remove: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0
