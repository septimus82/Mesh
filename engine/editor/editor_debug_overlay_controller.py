from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import format_swallowed_summary
from engine.swallowed_exceptions import reset as reset_swallowed_exceptions

from engine.ui_overlays.common import draw_panel_bg
from engine.editor.state import TOOL_MODE_PATH, TOOL_MODE_ZONE
from engine.behaviours.utils import describe_zone_behaviour


class EditorDebugOverlayController:
    """Encapsulates editor debug overlay line building + rendering."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def set_verify_artifacts_dir(self, path: str | Path | None) -> None:
        editor = self._editor
        if path is None:
            editor._verify_snapshot_artifacts_dir = None
        else:
            editor._verify_snapshot_artifacts_dir = Path(path)
        editor._verify_snapshot_cached_payload = None
        editor._verify_snapshot_cached_text = None
        editor._verify_snapshot_cached_mtime_map = {}
        editor._verify_snapshot_next_refresh_ts = 0.0

    def draw_debug_overlay(self, text_obj: Any) -> None:
        editor = self._editor
        dirty_flag = bool(editor.dirty_state.is_dirty)
        scene_name = editor.window.scene_controller.current_scene_path or ""
        if scene_name and len(scene_name) > 30:
            scene_name = "..." + scene_name[-27:]

        lines = [
            "EDITOR MODE (F4)",
            f"Scene: {scene_name or 'Unsaved'}" + (" *" if dirty_flag else ""),
            f"Tool: {editor.tool_mode} (R)",
            "----------------",
            "Click: Select Entity",
            "TAB: Toggle Inspector",
            "H: Toggle Hierarchy",
            "Ctrl+S: Save Scene",
            "Ctrl+Z: Undo | Ctrl+Y: Redo",
            "----------------",
        ]

        if editor.shape_edit_mode:
            lines.append(f"Shape Mode: {editor.shape_edit_mode} (Esc to exit)")
            lines.append(f"Shape Snap: {'on' if editor.shape_snap_enabled else 'off'} (G)")
            lines.append("Shift+A: Apply prefab shapes | Shift+R: Reset prefab shapes | Shift+P: Promote shapes")
            lines.append("----------------")
        elif editor.selected_entity:
            lines.append("Shift+A: Apply prefab shapes | Shift+R: Reset prefab shapes | Shift+P: Promote shapes")
            lines.append("----------------")
        if editor._status_message:
            lines.append(editor._status_message)
            lines.append("----------------")

        self._append_swallowed_exceptions_lines(lines)
        self._append_authoring_trace_lines(lines)

        if editor.tool_mode == TOOL_MODE_PATH:
            lines.append("PATH TOOL:")
            lines.append("Click Point: Select")
            lines.append("Shift+Click: Add Point")
            lines.append("Arrows: Move Point")
            lines.append("Del: Remove Point")
            lines.append("----------------")
        elif editor.tool_mode == TOOL_MODE_ZONE:
            lines.append("ZONE TOOL:")
            lines.append("Shift+Arrows: Resize")
            zone_behaviours = editor._get_zone_behaviours(editor.selected_entity)
            if zone_behaviours:
                active_zone = editor._get_zone_behaviour(editor.selected_entity)
                description = describe_zone_behaviour(active_zone)
                if len(zone_behaviours) > 1:
                    lines.append(
                        f"Ctrl+R: Cycle Zone ({editor.zone_behaviour_index + 1}/{len(zone_behaviours)})"
                    )
                trigger, hitbox = editor.shape.split_zone_behaviours(editor.selected_entity)
                if trigger and hitbox:
                    lines.append("T: Toggle Trigger/Hitbox")
                lines.append(f"Active Target: {description}")
            else:
                lines.append("Select entity with TriggerZone/Hitbox")
            lines.append("----------------")

        inspector = getattr(editor, "inspector", None)
        if inspector is not None and callable(getattr(inspector, "build_selection_overlay_lines", None)):
            lines.extend(inspector.build_selection_overlay_lines())
        else:
            lines.append("No selection")

        start_y = editor.window.height - 100
        draw_panel_bg(
            0,
            300,
            start_y - len(lines) * 20 - 10,
            start_y + 20,
        )

        full_text = "\n".join(lines)
        text_obj.text = full_text
        text_obj.y = start_y
        text_obj.draw()

    def reset_swallowed_exceptions(self) -> bool:
        editor = self._editor
        window = getattr(editor, "window", None)
        if not bool(getattr(window, "show_debug", False)):
            return False
        reset_counts = getattr(editor, "reset_swallowed_exceptions_overlay_counts", None)
        if callable(reset_counts):
            reset_counts()
            return True
        reset_swallowed_exceptions()
        editor._swallowed_exceptions_overlay_summary = "no swallowed exceptions recorded"
        editor._swallowed_exceptions_overlay_distinct_sites = 0
        editor._swallowed_exceptions_overlay_total_count = 0
        editor._swallowed_exceptions_overlay_next_refresh_ts = 0.0
        return True

    def build_swallowed_exceptions_copy_text(self, limit: int = 20) -> str:
        editor = self._editor
        window = getattr(editor, "window", None)
        summary, total, distinct = self._resolve_swallowed_summary_snapshot(limit=limit)
        lines = [
            "Swallowed Exceptions",
            f"total={total} distinct={distinct}",
        ]
        if summary:
            lines.extend(summary.splitlines())

        if bool(getattr(window, "show_debug", False)):
            shadow = self._resolve_shadow_backend_snapshot_for_copy()
            if shadow is None:
                lines.append("Shadow Backend: (unavailable)")
            else:
                selected = str(shadow.get("selected", "none"))
                reason = str(shadow.get("reason", ""))
                fallbacks = self._normalize_fallbacks(shadow.get("fallbacks", []))
                lines.append("Shadow Backend")
                lines.append(f"selected: {selected}")
                lines.append(f"reason: {reason}")
                lines.append("fallbacks:")
                if fallbacks:
                    lines.extend(f"  - {entry}" for entry in fallbacks)
                else:
                    lines.append("  - (none)")
            lines.extend(self._build_verify_health_snapshot_lines_for_copy())
        return "\n".join(line.rstrip() for line in lines)

    def copy_swallowed_exceptions_to_clipboard(self, limit: int = 20) -> bool:
        editor = self._editor
        window = getattr(editor, "window", None)
        if not bool(getattr(window, "show_debug", False)):
            return False
        text = self.build_swallowed_exceptions_copy_text(limit=limit)
        try:
            from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415
        except Exception:  # noqa: BLE001  # REASON: clipboard support is optional and should not block debug overlay actions
            return False
        is_web = bool(getattr(window, "is_web", False))
        is_headless = bool(getattr(window, "is_headless", False))
        return bool(try_copy_to_clipboard(text, is_web=is_web, is_headless=is_headless))

    def _append_swallowed_exceptions_lines(self, lines: list[str]) -> None:
        summary, total, distinct = self._resolve_swallowed_summary_snapshot(limit=20)
        if summary is None:
            return

        lines.append("Swallowed Exceptions")
        lines.append(
            f"totals: total_swallowed_count={total} distinct_sites={distinct}"
        )
        if summary:
            lines.extend(str(summary).splitlines())
        lines.append("----------------")
        self._append_shadow_backend_lines(lines)
        self._append_verify_health_snapshot_lines(lines)

    def _append_authoring_trace_lines(self, lines: list[str]) -> None:
        editor = self._editor
        window = getattr(editor, "window", None)
        if not bool(getattr(window, "show_debug", False)):
            return
        sc = getattr(window, "scene_controller", None)
        if sc is None:
            return
        get_snap = getattr(sc, "get_authoring_trace_snapshot", None)
        if not callable(get_snap):
            return
        snapshot = get_snap(limit=10)
        if not isinstance(snapshot, dict):
            return
        enabled = bool(snapshot.get("enabled", False))
        if not enabled:
            return
        total_calls = int(snapshot.get("total_calls", 0))
        lines.append("Authoring Trace")
        lines.append(f"enabled: true  total_calls: {total_calls}")
        functions = snapshot.get("functions")
        if isinstance(functions, list):
            for entry in functions:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "?"))
                count = int(entry.get("count", 0))
                total_ms = int(entry.get("total_ms", 0))
                avg_ms = int(entry.get("avg_ms", 0))
                last_err = entry.get("last_err")
                line = f"  {name}  count={count}  total_ms={total_ms}  avg_ms={avg_ms}"
                if last_err:
                    line += f"  err={last_err}"
                lines.append(line)
        lines.append("----------------")

    def _append_shadow_backend_lines(self, lines: list[str]) -> None:
        diagnostics = self._resolve_shadow_backend_snapshot()
        if diagnostics is None:
            return

        selected = str(diagnostics.get("selected", "none"))
        reason = str(diagnostics.get("reason", ""))
        fallbacks = self._normalize_fallbacks(diagnostics.get("fallbacks", []))
        fallbacks_text = ", ".join(fallbacks) if fallbacks else "(none)"

        lines.append("Shadow Backend")
        lines.append(f"selected: {selected}")
        lines.append(f"reason: {reason}")
        lines.append(f"fallbacks: {fallbacks_text}")
        lines.append("----------------")

    def _resolve_shadow_backend_snapshot(self) -> dict[str, object] | None:
        editor = self._editor
        window = getattr(editor, "window", None)
        if not bool(getattr(editor, "_show_swallowed_exceptions_overlay", False)):
            return None
        if not bool(getattr(window, "show_debug", False)):
            return None

        now = float(time.time())
        next_refresh_ts = float(getattr(editor, "_shadow_backend_overlay_next_refresh_ts", 0.0))
        cached = getattr(editor, "_shadow_backend_overlay_diagnostics", None)
        if (
            isinstance(cached, dict)
            and cached
            and now < next_refresh_ts
        ):
            return {
                "schema_version": 1,
                "selected": str(cached.get("selected", "none")),
                "reason": str(cached.get("reason", "")),
                "fallbacks": self._normalize_fallbacks(cached.get("fallbacks", [])),
            }

        diagnostics: dict[str, object]
        try:
            from engine.lighting.shadows import get_shadow_backend_diagnostics  # noqa: PLC0415

            raw = get_shadow_backend_diagnostics()
            diagnostics = raw if isinstance(raw, dict) else {}
        except Exception:  # noqa: BLE001  # REASON: shadow backend diagnostics are optional and should not break the debug overlay refresh
            diagnostics = {}

        normalized = {
            "schema_version": 1,
            "selected": str(diagnostics.get("selected", "none")),
            "reason": str(diagnostics.get("reason", "")),
            "fallbacks": self._normalize_fallbacks(diagnostics.get("fallbacks", [])),
        }
        editor._shadow_backend_overlay_diagnostics = normalized
        editor._shadow_backend_overlay_next_refresh_ts = now + 0.5
        return normalized

    def _resolve_shadow_backend_snapshot_for_copy(self) -> dict[str, object] | None:
        editor = self._editor
        window = getattr(editor, "window", None)
        if not bool(getattr(window, "show_debug", False)):
            return None

        # Reuse existing throttled overlay refresh path when the panel is visible.
        if bool(getattr(editor, "_show_swallowed_exceptions_overlay", False)):
            return self._resolve_shadow_backend_snapshot()

        # Do not force refresh when the panel is hidden; only return cached value.
        cached = getattr(editor, "_shadow_backend_overlay_diagnostics", None)
        if not isinstance(cached, dict) or not cached:
            return None
        return {
            "schema_version": 1,
            "selected": str(cached.get("selected", "none")),
            "reason": str(cached.get("reason", "")),
            "fallbacks": self._normalize_fallbacks(cached.get("fallbacks", [])),
        }

    def _normalize_fallbacks(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    def _append_verify_health_snapshot_lines(self, lines: list[str]) -> None:
        snapshot = self._resolve_verify_health_snapshot_for_overlay()
        if snapshot is None:
            return
        lines.extend(self._format_verify_health_snapshot_lines(snapshot))
        lines.append("----------------")

    def _build_verify_health_snapshot_lines_for_copy(self) -> list[str]:
        editor = self._editor
        if bool(getattr(editor, "_show_swallowed_exceptions_overlay", False)):
            snapshot = self._resolve_verify_health_snapshot_for_overlay()
        else:
            snapshot = self._resolve_verify_health_snapshot(refresh_allowed=False)
        if snapshot is None:
            snapshot = self._unavailable_verify_snapshot_payload()
        return self._format_verify_health_snapshot_lines(snapshot)

    def _resolve_verify_health_snapshot_for_overlay(self) -> dict[str, str] | None:
        editor = self._editor
        window = getattr(editor, "window", None)
        if not bool(getattr(editor, "_show_swallowed_exceptions_overlay", False)):
            return None
        if not bool(getattr(window, "show_debug", False)):
            return None
        return self._resolve_verify_health_snapshot(refresh_allowed=True)

    def _resolve_verify_health_snapshot(self, *, refresh_allowed: bool) -> dict[str, str]:
        editor = self._editor
        cached = getattr(editor, "_verify_snapshot_cached_payload", None)
        if not refresh_allowed:
            if isinstance(cached, dict):
                return self._normalize_verify_snapshot_payload(cached)
            return self._unavailable_verify_snapshot_payload()

        now = float(time.time())
        next_refresh_ts = float(getattr(editor, "_verify_snapshot_next_refresh_ts", 0.0))
        if isinstance(cached, dict) and now < next_refresh_ts:
            return self._normalize_verify_snapshot_payload(cached)

        artifacts_dir = self._resolve_verify_artifacts_dir()
        snapshot = self._unavailable_verify_snapshot_payload()
        mtime_map: dict[str, int] = {}
        if artifacts_dir is not None:
            mtime_map = self._build_verify_snapshot_mtime_map(artifacts_dir)
            cached_mtime_map = getattr(editor, "_verify_snapshot_cached_mtime_map", None)
            if (
                isinstance(cached, dict)
                and isinstance(cached_mtime_map, dict)
                and mtime_map == cached_mtime_map
            ):
                snapshot = self._normalize_verify_snapshot_payload(cached)
            else:
                snapshot = self._load_verify_health_snapshot(artifacts_dir)

        editor._verify_snapshot_cached_payload = snapshot
        editor._verify_snapshot_cached_text = "\n".join(self._format_verify_health_snapshot_lines(snapshot))
        editor._verify_snapshot_cached_mtime_map = mtime_map
        editor._verify_snapshot_next_refresh_ts = now + 0.5
        problems = getattr(editor, "problems", None)
        if problems is not None:
            refresher = getattr(problems, "refresh_structured_diagnostics", None)
            if callable(refresher):
                refresher()
        return self._normalize_verify_snapshot_payload(snapshot)

    def _resolve_verify_artifacts_dir(self) -> Path | None:
        editor = self._editor
        window = getattr(editor, "window", None)

        explicit = getattr(editor, "_verify_snapshot_artifacts_dir", None)
        if explicit is not None:
            path = Path(explicit)
            return path if path.exists() and path.is_dir() else None

        for candidate in (
            getattr(window, "artifacts_dir", None),
            getattr(editor, "_artifacts_dir", None),
        ):
            if candidate is None:
                continue
            path = Path(candidate)
            if path.exists() and path.is_dir():
                return path
        return None

    def _build_verify_snapshot_mtime_map(self, artifacts_dir: Path) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for name in (
            "exception_budget.json",
            "verify_step_durations.json",
            "verify_step_budget_check.json",
        ):
            path = artifacts_dir / name
            if path.exists() and path.is_file():
                try:
                    mapping[name] = int(path.stat().st_mtime_ns)
                except OSError:
                    mapping[name] = -1
            else:
                mapping[name] = -1
        return mapping

    def _load_verify_health_snapshot(self, artifacts_dir: Path) -> dict[str, str]:
        snapshot = self._unavailable_verify_snapshot_payload()
        exception_payload = self._safe_read_json(artifacts_dir / "exception_budget.json")
        durations_payload = self._safe_read_json(artifacts_dir / "verify_step_durations.json")
        step_budget_payload = self._safe_read_json(artifacts_dir / "verify_step_budget_check.json")

        if isinstance(exception_payload, dict):
            snapshot["exception_current"] = self._as_int_text(exception_payload.get("current_count"))
            snapshot["exception_baseline"] = self._as_int_text(exception_payload.get("baseline_count"))
            snapshot["exception_ok"] = self._as_bool_text(exception_payload.get("ok"))

        if isinstance(durations_payload, dict):
            snapshot["verify_total_ms"] = self._as_int_text(durations_payload.get("total_ms"))

        if isinstance(step_budget_payload, dict):
            snapshot["step_budget_ok"] = self._as_bool_text(step_budget_payload.get("ok"))
            step_ok_raw = step_budget_payload.get("ok")
            if step_ok_raw is True:
                snapshot["worst_step"] = "none"
                snapshot["worst_delta_ms"] = "?"
            elif step_ok_raw is False:
                offenders = step_budget_payload.get("offenders")
                best_name = "?"
                best_delta: int | None = None
                if isinstance(offenders, list):
                    parsed: list[tuple[int, str]] = []
                    for row in offenders:
                        if not isinstance(row, dict):
                            continue
                        name = row.get("name")
                        delta = row.get("delta_ms")
                        if isinstance(name, str) and isinstance(delta, (int, float)):
                            parsed.append((int(delta), name))
                    if parsed:
                        parsed.sort(key=lambda item: (-int(item[0]), item[1]))
                        best_delta, best_name = parsed[0]
                if best_name != "?":
                    snapshot["worst_step"] = best_name
                if best_delta is not None:
                    snapshot["worst_delta_ms"] = str(int(best_delta))
        return snapshot

    def _safe_read_json(self, path: Path) -> dict[str, object] | None:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001  # REASON: verify snapshot JSON reads are best-effort and should not break the debug overlay
            return None

    def _unavailable_verify_snapshot_payload(self) -> dict[str, str]:
        return {
            "exception_current": "?",
            "exception_baseline": "?",
            "exception_ok": "?",
            "verify_total_ms": "?",
            "step_budget_ok": "?",
            "worst_step": "?",
            "worst_delta_ms": "?",
        }

    def _normalize_verify_snapshot_payload(self, payload: object) -> dict[str, str]:
        if not isinstance(payload, dict):
            return self._unavailable_verify_snapshot_payload()
        normalized = self._unavailable_verify_snapshot_payload()
        for key in normalized:
            normalized[key] = str(payload.get(key, "?"))
        return normalized

    def _format_verify_health_snapshot_lines(self, snapshot: dict[str, str]) -> list[str]:
        return [
            "Verify Health Snapshot",
            f"exception_budget: {snapshot['exception_current']}/{snapshot['exception_baseline']} ok={snapshot['exception_ok']}",
            f"verify_total_ms: {snapshot['verify_total_ms']}",
            f"step_budget_ok: {snapshot['step_budget_ok']}",
            f"worst_step: {snapshot['worst_step']} delta_ms={snapshot['worst_delta_ms']}",
        ]

    def _as_int_text(self, value: object) -> str:
        return str(int(value)) if isinstance(value, (int, float)) else "?"

    def _as_bool_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return "?"

    def _resolve_swallowed_summary_snapshot(self, *, limit: int) -> tuple[str | None, int, int]:
        editor = self._editor
        window = getattr(editor, "window", None)
        if not bool(getattr(editor, "_show_swallowed_exceptions_overlay", False)):
            return None, 0, 0
        if not bool(getattr(window, "show_debug", False)):
            return None, 0, 0

        refresh = getattr(editor, "refresh_swallowed_exceptions_overlay_summary", None)
        if callable(refresh):
            refresh(force=False)
        summary = str(getattr(editor, "_swallowed_exceptions_overlay_summary", "")).strip()
        total = int(getattr(editor, "_swallowed_exceptions_overlay_total_count", 0))
        distinct = int(getattr(editor, "_swallowed_exceptions_overlay_distinct_sites", 0))

        # For non-default limits, produce deterministic summary text on demand.
        if int(limit) != 20:
            summary = format_swallowed_summary(limit=int(limit))
        elif not summary:
            summary = "no swallowed exceptions recorded"
        return summary, total, distinct
