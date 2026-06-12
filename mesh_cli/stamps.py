"""Stamp, Brush, and Capture commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engine.brushes import (
    BrushIssue,
    iter_brush_paths,
    load_brush,
    pick_brush_layer_id,
    render_brush_layer_ascii,
    summarize_brush,
    validate_brush,
)
from engine.logging_tools import get_logger
from engine.paths import resolve_path
from engine.stamps import (
    StampIssue,
    iter_stamp_paths,
    load_stamp,
    pick_stamp_layer_id,
    render_stamp_layer_ascii,
    summarize_stamp,
    validate_stamp,
)

_logger = get_logger(__name__)


def handle(args: argparse.Namespace) -> int:
    if args.command == "stamp":
        return _handle_stamp(args)
    if args.command == "brush":
        return _handle_brush(args)
    if args.command == "capture":
        return _handle_capture(args)
    return 1


def register(subparsers: argparse._SubParsersAction) -> None:
    # Stamp utilities
    stamp_parser = subparsers.add_parser("stamp", help="Stamp discovery and validation", description="Stamp discovery and validation")
    stamp_subparsers = stamp_parser.add_subparsers(dest="stamp_command", help="Stamp subcommand")
    stamp_list = stamp_subparsers.add_parser("list", help="List available stamps under packs/*/stamps", description="List available stamps under packs/*/stamps")
    stamp_list.add_argument("--pack", dest="pack", help="Optional pack id filter")
    stamp_list.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    stamp_validate = stamp_subparsers.add_parser("validate-all", help="Validate all stamps (quality gate)", description="Validate all stamps (quality gate)")
    stamp_validate.add_argument("--pack", dest="pack", help="Optional pack id filter")
    stamp_preview = stamp_subparsers.add_parser("preview", help="Render an ASCII preview of a stamp layer", description="Render an ASCII preview of a stamp layer")
    stamp_preview.add_argument("stamp_path", help="Path to stamp JSON")
    stamp_preview.add_argument("--layer", dest="layer", help="Layer id to preview (default: first layer in stamp)")
    stamp_preview.add_argument("--tile", dest="tile", type=int, help="Optional tile filter to highlight")
    stamp_preview.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # Brush utilities
    brush_parser = subparsers.add_parser("brush", help="Brush discovery and validation", description="Brush discovery and validation")
    brush_subparsers = brush_parser.add_subparsers(dest="brush_command", help="Brush subcommand")
    brush_list = brush_subparsers.add_parser("list", help="List available brushes under packs/*/brushes", description="List available brushes under packs/*/brushes")
    brush_list.add_argument("--pack", dest="pack", help="Optional pack id filter")
    brush_list.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    brush_validate = brush_subparsers.add_parser("validate-all", help="Validate all brushes (quality gate)", description="Validate all brushes (quality gate)")
    brush_validate.add_argument("--pack", dest="pack", help="Optional pack id filter")
    brush_preview = brush_subparsers.add_parser("preview", help="Render an ASCII preview of a brush", description="Render an ASCII preview of a brush")
    brush_preview.add_argument("brush_path", help="Path to brush JSON")
    brush_preview.add_argument("--layer", dest="layer", help="Optional layer label for preview output")
    brush_preview.add_argument("--tile", dest="tile", type=int, help="Optional tile filter to highlight")
    brush_preview.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # Capture catalog utilities
    capture_parser = subparsers.add_parser("capture", help="Captured asset discovery and validation", description="Captured asset discovery and validation")
    capture_subparsers = capture_parser.add_subparsers(dest="capture_command", help="Capture subcommand")
    capture_list = capture_subparsers.add_parser("list", help="List captured stamps/brushes under packs/*", description="List captured stamps/brushes under packs/*")
    capture_list.add_argument("--pack", dest="pack", help="Optional pack id filter")
    capture_list.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    capture_validate = capture_subparsers.add_parser("validate-all", help="Validate all captured stamps/brushes (quality gate)", description="Validate all captured stamps/brushes (quality gate)")
    capture_validate.add_argument("--pack", dest="pack", help="Optional pack id filter")


def _handle_stamp(args: argparse.Namespace) -> int:
    stamp_cmd = getattr(args, "stamp_command", None)
    pack = getattr(args, "pack", None)
    format_value = str(getattr(args, "format", "text") or "text").strip().lower()

    if stamp_cmd == "list":
        stamp_summaries = []
        for rel_path in iter_stamp_paths(pack_id=pack):
            full_path = resolve_path(rel_path)
            try:
                stamp = load_stamp(str(full_path))
            except Exception:
                _logger.debug("SWALLOW[STMP-001] load_stamp failed for %s", rel_path, exc_info=True)
                continue
            stamp_summary = summarize_stamp(stamp, rel_path=rel_path)
            if not stamp_summary.id:
                continue
            stamp_summaries.append(stamp_summary)
        stamp_summaries.sort(key=lambda s: (s.pack_id, s.id, s.path))

        if format_value == "json":
            payload = {
                "ok": True,
                "count": len(stamp_summaries),
                "stamps": [
                    {
                        "pack_id": s.pack_id,
                        "id": s.id,
                        "w": int(s.w),
                        "h": int(s.h),
                        "layer_ids": list(s.layer_ids),
                        "entity_count": int(s.entity_count),
                        "path": s.path,
                    }
                    for s in stamp_summaries
                ],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        for stamp_s in stamp_summaries:
            print(
                f"{stamp_s.pack_id} {stamp_s.id} {int(stamp_s.w)}x{int(stamp_s.h)} "
                f"layers={len(stamp_s.layer_ids)} entities={int(stamp_s.entity_count)} path={stamp_s.path}",
            )
        return 0

    if stamp_cmd == "validate-all":
        prefabs_path = resolve_path("assets/prefabs.json")
        try:
            prefabs_payload = json.loads(prefabs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _logger.debug("SWALLOW[STMP-002] prefabs.json parse error", exc_info=True)
            print(f"[Mesh][Stamp] ERROR: assets/prefabs.json :: prefabs.parse_error :: {exc}")
            return 1

        stamp_prefab_ids: set[str] = {
            str(entry.get("id"))
            for entry in prefabs_payload
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }

        stamp_issues: list[StampIssue] = []
        for rel_path in iter_stamp_paths(pack_id=pack):
            full_path = resolve_path(rel_path)
            try:
                stamp = load_stamp(str(full_path))
            except Exception as exc:  # noqa: BLE001  # REASON: cli stamps fallback isolation
                _logger.debug("SWALLOW[STMP-003] stamp parse error for %s", rel_path, exc_info=True)
                stamp_issues.append(StampIssue(path=rel_path, code="stamp.parse_error", detail=str(exc)))
                continue
            stamp_issues.extend(validate_stamp(stamp, rel_path=rel_path, prefab_ids=stamp_prefab_ids))

        stamp_issues.sort(key=lambda issue: (issue.path, issue.code, issue.detail))
        if stamp_issues:
            for stamp_issue in stamp_issues:
                print(f"[Mesh][Stamp] ERROR: {stamp_issue.path} :: {stamp_issue.code} :: {stamp_issue.detail}")
            return 1
        return 0

    if stamp_cmd == "preview":
        stamp_path_raw = str(getattr(args, "stamp_path", "") or "").strip()
        if not stamp_path_raw:
            print("[Mesh][Stamp] ERROR: missing stamp_path")
            return 1

        stamp_path = resolve_path(stamp_path_raw)
        if not stamp_path.exists():
            print(f"[Mesh][Stamp] ERROR: {stamp_path_raw} :: stamp.missing :: stamp not found")
            return 1

        try:
            stamp = load_stamp(str(stamp_path))
        except Exception as exc:  # noqa: BLE001  # REASON: cli stamps fallback isolation
            _logger.debug("SWALLOW[STMP-004] stamp parse error for %s", stamp_path_raw, exc_info=True)
            print(f"[Mesh][Stamp] ERROR: {stamp_path_raw} :: stamp.parse_error :: {exc}")
            return 1

        try:
            layer_id = pick_stamp_layer_id(stamp, getattr(args, "layer", None))
        except KeyError:
            print(f"[Mesh][Stamp] ERROR: {stamp_path_raw} :: stamp.layer_missing :: layer not present")
            return 1

        tile_filter = getattr(args, "tile", None)
        try:
            lines = render_stamp_layer_ascii(stamp, layer_id=layer_id, tile_filter=tile_filter)
        except KeyError:
            print(f"[Mesh][Stamp] ERROR: {stamp_path_raw} :: stamp.layer_missing :: layer not present")
            return 1
        except ValueError as exc:
            code = str(exc) or "stamp.invalid"
            if code == "missing_or_invalid_dims":
                code = "stamp.missing_dims"
            elif code == "tiles_length_mismatch":
                code = "stamp.tiles_length_mismatch"
            elif code == "invalid_tiles":
                code = "stamp.invalid_tiles"
            elif code == "tiles_out_of_bounds":
                code = "stamp.tiles_out_of_bounds"
            print(f"[Mesh][Stamp] ERROR: {stamp_path_raw} :: {code} :: cannot render")
            return 1

        stamp_id = str(stamp.get("id") or "").strip()
        w = stamp.get("w", stamp.get("width"))
        h = stamp.get("h", stamp.get("height"))
        w_int = int(w) if isinstance(w, int) else len(lines[0]) if lines else 0
        h_int = int(h) if isinstance(h, int) else len(lines)

        if format_value == "json":
            payload = {
                "ok": True,
                "id": stamp_id,
                "w": int(w_int),
                "h": int(h_int),
                "layer_id": layer_id,
                "tile_filter": (int(tile_filter) if tile_filter is not None else None),
                "lines": list(lines),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        print(f"{stamp_id} {int(w_int)}x{int(h_int)} layer={layer_id}")
        for line in lines:
            print(line)
        return 0

    print("[Mesh][CLI] Error: missing stamp subcommand")
    return 2


def _handle_brush(args: argparse.Namespace) -> int:
    brush_cmd = getattr(args, "brush_command", None)
    pack = getattr(args, "pack", None)
    format_value = str(getattr(args, "format", "text") or "text").strip().lower()

    if brush_cmd == "list":
        brush_summaries = []
        for rel_path in iter_brush_paths(pack_id=pack):
            full_path = resolve_path(rel_path)
            try:
                brush = load_brush(str(full_path))
            except Exception:
                _logger.debug("SWALLOW[STMP-005] load_brush failed for %s", rel_path, exc_info=True)
                continue
            brush_summary = summarize_brush(brush=brush, rel_path=rel_path)
            if not brush_summary.id:
                continue
            brush_summaries.append(brush_summary)
        brush_summaries.sort(key=lambda s: (s.pack_id, s.id, s.path))

        if format_value == "json":
            payload = {
                "ok": True,
                "count": len(brush_summaries),
                "brushes": [
                    {
                        "pack_id": s.pack_id,
                        "id": s.id,
                        "w": int(s.w),
                        "h": int(s.h),
                        "mask_tile": int(s.mask_tile),
                        "path": s.path,
                    }
                    for s in brush_summaries
                ],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        for brush_s in brush_summaries:
            print(f"{brush_s.pack_id} {brush_s.id} {int(brush_s.w)}x{int(brush_s.h)} path={brush_s.path}")
        return 0

    if brush_cmd == "validate-all":
        brush_issues: list[BrushIssue] = []
        for rel_path in iter_brush_paths(pack_id=pack):
            full_path = resolve_path(rel_path)
            try:
                raw = json.loads(full_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _logger.debug("SWALLOW[STMP-006] brush parse error for %s", rel_path, exc_info=True)
                brush_issues.append(BrushIssue(path=rel_path, code="brush.parse_error", detail=str(exc)))
                continue
            for code in validate_brush(raw):
                brush_issues.append(BrushIssue(path=rel_path, code=code, detail=""))

        brush_issues.sort(key=lambda issue: (issue.path, issue.code, issue.detail))
        if brush_issues:
            for brush_issue in brush_issues:
                detail = f" :: {brush_issue.detail}" if brush_issue.detail else ""
                print(f"[Mesh][Brush] ERROR: {brush_issue.path} :: {brush_issue.code}{detail}")
            return 1
        return 0

    if brush_cmd == "preview":
        brush_path_raw = str(getattr(args, "brush_path", "") or "").strip()
        if not brush_path_raw:
            print("[Mesh][Brush] ERROR: missing brush_path")
            return 1

        brush_path = resolve_path(brush_path_raw)
        if not brush_path.exists():
            print(f"[Mesh][Brush] ERROR: {brush_path_raw} :: brush.missing :: brush not found")
            return 1

        try:
            raw = json.loads(brush_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _logger.debug("SWALLOW[STMP-007] brush parse error for %s", brush_path_raw, exc_info=True)
            print(f"[Mesh][Brush] ERROR: {brush_path_raw} :: brush.parse_error :: {exc}")
            return 1
        if not isinstance(raw, dict):
            print(f"[Mesh][Brush] ERROR: {brush_path_raw} :: brush.root_type :: must be an object")
            return 1

        errors = validate_brush(raw)
        if errors:
            print(f"[Mesh][Brush] ERROR: {brush_path_raw} :: brush.invalid :: {errors[0]}")
            return 1

        layer_id = pick_brush_layer_id(raw, getattr(args, "layer", None))
        tile_filter = getattr(args, "tile", None)
        try:
            lines = render_brush_layer_ascii(raw, layer_id=layer_id, tile_filter=tile_filter)
        except Exception as exc:  # noqa: BLE001  # REASON: cli stamps fallback isolation
            _logger.debug("SWALLOW[STMP-008] brush render failed for %s", brush_path_raw, exc_info=True)
            print(f"[Mesh][Brush] ERROR: {brush_path_raw} :: brush.invalid :: cannot render: {exc}")
            return 1

        brush_id = str(raw.get("id") or "").strip()
        w = int(raw.get("w") or 0)
        h = int(raw.get("h") or 0)

        if format_value == "json":
            payload = {
                "ok": True,
                "id": brush_id,
                "w": int(w),
                "h": int(h),
                "layer_id": layer_id,
                "tile_filter": (int(tile_filter) if tile_filter is not None else None),
                "lines": list(lines),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        print(f"{brush_id} {int(w)}x{int(h)} layer={layer_id}")
        for line in lines:
            print(line)
        return 0

    print("[Mesh][Brush] ERROR: missing brush subcommand")
    return 2


def _handle_capture(args: argparse.Namespace) -> int:
    capture_cmd = getattr(args, "capture_command", None)
    pack = getattr(args, "pack", None)
    format_value = str(getattr(args, "format", "text") or "text").strip().lower()

    def _is_captured(*, rel_path: str, payload: Any) -> bool:
        name = Path(str(rel_path)).stem
        if name.startswith("capture_"):
            return True
        if isinstance(payload, dict):
            meta = payload.get("metadata")
            if isinstance(meta, dict) and str(meta.get("source") or "") == "capture_mode":
                return True
        return False

    if capture_cmd == "list":
        rows: list[dict[str, Any]] = []

        for rel_path in iter_stamp_paths(pack_id=pack):
            try:
                stamp = load_stamp(str(resolve_path(rel_path)))
            except Exception:
                _logger.debug("SWALLOW[STMP-009] capture stamp load failed for %s", rel_path, exc_info=True)
                continue
            if not _is_captured(rel_path=rel_path, payload=stamp):
                continue
            parts = str(rel_path).replace("\\", "/").split("/")
            pack_id = parts[1] if len(parts) >= 4 and parts[0] == "packs" else ""
            asset_id = str(stamp.get("id") or Path(rel_path).stem)
            rows.append({"pack_id": pack_id, "type": "stamp", "id": asset_id, "path": str(rel_path).replace("\\", "/")})

        for rel_path in iter_brush_paths(pack_id=pack):
            full_path = resolve_path(rel_path)
            try:
                brush = json.loads(full_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                _logger.debug("SWALLOW[STMP-010] capture brush parse failed for %s", rel_path, exc_info=True)
                continue
            if not _is_captured(rel_path=rel_path, payload=brush):
                continue
            parts = str(rel_path).replace("\\", "/").split("/")
            pack_id = parts[1] if len(parts) >= 4 and parts[0] == "packs" else ""
            asset_id = str(brush.get("id") or Path(rel_path).stem) if isinstance(brush, dict) else Path(rel_path).stem
            rows.append({"pack_id": pack_id, "type": "brush", "id": asset_id, "path": str(rel_path).replace("\\", "/")})

        rows.sort(key=lambda r: (str(r["pack_id"]), str(r["type"]), str(r["id"]), str(r["path"])))

        if format_value == "json":
            print(json.dumps({"ok": True, "count": len(rows), "assets": rows}, indent=2, sort_keys=True))
            return 0
        for r in rows:
            print(f'{r["pack_id"]} {r["type"]} {r["id"]} path={r["path"]}')
        return 0

    if capture_cmd == "validate-all":
        prefabs_path = resolve_path("assets/prefabs.json")
        try:
            prefabs_payload = json.loads(prefabs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _logger.debug("SWALLOW[STMP-011] capture prefabs.json parse error", exc_info=True)
            print(f"[Mesh][Capture] ERROR: assets/prefabs.json :: prefabs.parse_error :: {exc}")
            return 1
        capture_prefab_ids: set[str] = {
            str(entry.get("id"))
            for entry in prefabs_payload
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }

        capture_stamp_issues: list[StampIssue] = []
        for rel_path in iter_stamp_paths(pack_id=pack):
            try:
                stamp = load_stamp(str(resolve_path(rel_path)))
            except Exception:  # noqa: BLE001  # REASON: cli stamps fallback isolation
                _logger.debug("SWALLOW[STMP-012] capture stamp load failed for %s", rel_path, exc_info=True)
                continue
            if not _is_captured(rel_path=rel_path, payload=stamp):
                continue
            capture_stamp_issues.extend(validate_stamp(stamp, rel_path=rel_path, prefab_ids=capture_prefab_ids))

        capture_brush_issues: list[BrushIssue] = []
        for rel_path in iter_brush_paths(pack_id=pack):
            full_path = resolve_path(rel_path)
            try:
                raw = json.loads(full_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                _logger.debug("SWALLOW[STMP-013] capture brush parse failed for %s", rel_path, exc_info=True)
                continue
            if not _is_captured(rel_path=rel_path, payload=raw):
                continue
            for code in validate_brush(raw):
                capture_brush_issues.append(BrushIssue(path=rel_path, code=code, detail=""))

        errors = []
        for stamp_issue in capture_stamp_issues:
            errors.append(f"[Mesh][Capture] ERROR: {stamp_issue.path} :: {stamp_issue.code} :: {stamp_issue.detail}")
        for brush_issue in capture_brush_issues:
            errors.append(f"[Mesh][Capture] ERROR: {brush_issue.path} :: {brush_issue.code}")
        errors.sort()

        if errors:
            for line in errors:
                print(line)
            return 1
        return 0

    print("[Mesh][Capture] ERROR: missing capture subcommand")
    return 2
