import argparse
import json
from typing import Any

from engine.paths import resolve_path
from engine.persistence_io import write_json_atomic
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload
from engine.tooling_runtime.macro_apply_report import compute_scene_macro_report


def _compute_scene_macro_apply(
    *,
    scene_payload: dict[str, Any],
    scene_path: str,
    macro_path: str,
    raw_args: list[str],
    anchor_override: str | None,
    primary_entity_id: str | None = None,
    cursor_world_pos: tuple[float, float] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = compute_scene_macro_report(
        scene_payload=scene_payload,
        scene_path=scene_path,
        macro_path=macro_path,
        raw_args=raw_args,
        anchor_override=anchor_override,
        cursor_world_pos=cursor_world_pos,
        primary_entity_id=primary_entity_id,
    )
    return result.after_payload, result.report


def _handle_scene_macro_report(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    macro_path = str(getattr(args, "macro", "") or "").strip()
    if not macro_path:
        print("[Mesh][CLI] Error: missing --macro")
        return 2

    format_value = str(getattr(args, "format", "json") or "json").strip().lower()
    if format_value not in {"json", "text"}:
        print("[Mesh][CLI] Error: invalid --format")
        return 2

    anchor = getattr(args, "anchor", None)
    anchor_override = str(anchor).strip() if isinstance(anchor, str) and str(anchor).strip() else None

    raw_args = getattr(args, "arg", None)
    raw_args = raw_args if isinstance(raw_args, list) else []

    resolved_scene = resolve_path(scene_path)
    if not resolved_scene.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    resolved_macro = resolve_path(macro_path)
    if not resolved_macro.exists():
        print(f"[Mesh][CLI] Error: macro not found: {macro_path}")
        return 1

    try:
        scene_payload = json.loads(resolved_scene.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # REASON: scene macro CLI should report scene JSON parse failures deterministically before computing a macro report
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1
    if not isinstance(scene_payload, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    try:
        result = compute_scene_macro_report(
            scene_payload=scene_payload,
            scene_path=scene_path,
            macro_path=macro_path,
            raw_args=raw_args,
            anchor_override=anchor_override,
        )
    except Exception as exc:  # noqa: BLE001  # REASON: scene macro CLI should collapse unexpected macro report failures into a deterministic nonzero exit
        print(f"[Mesh][CLI] Error: macro-report failed: {type(exc).__name__}: {exc}")
        return 1

    if format_value == "json":
        print(json.dumps(result.report, indent=2, sort_keys=True))
        return 0

    report = result.report
    print(
        f"macro-report scene={report.get('scene_path')} macro={report.get('macro_path')} "
        f"create={int(report.get('will_create') or 0)} update={int(report.get('will_update') or 0)}",
    )
    for eid in report.get("create_ids") or []:
        print(f"create {eid}")
    for eid in report.get("update_ids") or []:
        print(f"update {eid}")
    return 0


def _handle_scene_macro_apply(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    macro_path = str(getattr(args, "macro", "") or "").strip()
    if not macro_path:
        print("[Mesh][CLI] Error: missing --macro")
        return 2

    anchor = getattr(args, "anchor", None)
    anchor_override = str(anchor).strip() if isinstance(anchor, str) and str(anchor).strip() else None

    raw_args = getattr(args, "arg", None)
    raw_args = raw_args if isinstance(raw_args, list) else []

    resolved_scene = resolve_path(scene_path)
    if not resolved_scene.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    resolved_macro = resolve_path(macro_path)
    if not resolved_macro.exists():
        print(f"[Mesh][CLI] Error: macro not found: {macro_path}")
        return 1

    try:
        scene_payload = json.loads(resolved_scene.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # REASON: scene macro apply CLI should report scene JSON parse failures deterministically before macro application
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1
    if not isinstance(scene_payload, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    try:
        after_payload, report_payload = _compute_scene_macro_apply(
            scene_payload=scene_payload,
            scene_path=scene_path,
            macro_path=macro_path,
            raw_args=raw_args,
            anchor_override=anchor_override,
        )
    except Exception as exc:  # noqa: BLE001  # REASON: scene macro apply CLI should collapse unexpected macro application failures into a deterministic nonzero exit
        print(f"[Mesh][CLI] Error: macro-apply failed: {type(exc).__name__}: {exc}")
        return 1

    if after_payload == scene_payload:
        return 0

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(after_payload)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after macro apply: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved_scene, compacted, indent=2, sort_keys=False, trailing_newline=True)

    created = int(report_payload.get("will_create") or 0)
    updated = int(report_payload.get("will_update") or 0)
    print(f"[Mesh][CLI] OK: macro applied: {scene_path} macro={macro_path} created={created} updated={updated}")
    return 0
