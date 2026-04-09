from __future__ import annotations

import logging
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


DEFAULT_SMOKE_SCENE = "scenes/runtime_smoke_scene.json"
DEFAULT_SMOKE_TICKS = 3


@dataclass(slots=True)
class _RuntimeSmokeWindow:
    engine_config: Any


def _build_diagnostics_artifact_payload(
    *,
    explicit_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from engine.diagnostics import get_diagnostics_payload  # noqa: PLC0415

    diagnostics = get_diagnostics_payload()
    errors = sum(1 for item in diagnostics if isinstance(item, dict) and str(item.get("severity", "")) == "error")
    warnings = sum(1 for item in diagnostics if isinstance(item, dict) and str(item.get("severity", "")) == "warning")
    infos = sum(1 for item in diagnostics if isinstance(item, dict) and str(item.get("severity", "")) == "info")

    context: dict[str, Any] = {}
    if isinstance(explicit_context, dict):
        for key in sorted(explicit_context.keys()):
            value = explicit_context[key]
            if value is None:
                continue
            text = str(value).strip() if isinstance(value, str) else value
            if text == "":
                continue
            context[str(key)] = value

    for entry in diagnostics:
        if not isinstance(entry, dict):
            continue
        item_context = entry.get("context")
        if not isinstance(item_context, dict):
            continue
        for key in ("slot", "save_path"):
            if key in context:
                continue
            if key not in item_context:
                continue
            value = item_context.get(key)
            if value is None:
                continue
            text = str(value).strip() if isinstance(value, str) else value
            if text == "":
                continue
            context[key] = value

    return {
        "schema_version": 1,
        "ok": int(errors) == 0,
        "counts": {
            "errors": int(errors),
            "warnings": int(warnings),
            "info": int(infos),
        },
        "diagnostics": diagnostics,
        "context": context,
    }


def _write_diagnostics_artifact(
    *,
    path: str | None,
    context: dict[str, Any] | None = None,
) -> None:
    artifact = str(path or "").strip()
    if not artifact:
        return

    from engine.diagnostics import add_exception as diag_add_exception  # noqa: PLC0415
    from engine.log_utils import log_once  # noqa: PLC0415
    from engine.logging_tools import get_logger  # noqa: PLC0415
    from engine.persistence_io import write_json_atomic  # noqa: PLC0415
    from engine.save_runtime.ux_codes import SAVE_WRITE_FAILED  # noqa: PLC0415

    payload = _build_diagnostics_artifact_payload(explicit_context=context)
    try:
        write_json_atomic(Path(artifact), payload, indent=2, sort_keys=True, trailing_newline=True)
    except Exception as exc:
        logger = get_logger(__name__)
        tag = str(artifact or "<empty>")
        if log_once(
            f"runtime_only.diag_artifact_write.{tag}",
            f"SWALLOW[RTEN-DIAG-001] diagnostics artifact write failure path={tag}",
            logger=logger,
            level=logging.DEBUG,
        ):
            logger.debug(
                "SWALLOW[%s] diagnostics artifact write failure path=%s",
                "RTEN-DIAG-001",
                tag,
                exc_info=True,
            )
        diag_add_exception(
            SAVE_WRITE_FAILED,
            exc,
            "engine.runtime_only.entry",
            location=artifact,
            context={"operation": "write_diagnostics_artifact", "save_path": artifact, "pointer": "$"},
            severity="warning",
            hint="Check write permissions and free disk space for diagnostics artifact output.",
        )


def _emit_save_runtime_snapshot_diagnostics() -> None:
    from engine.diagnostics import get_sink  # noqa: PLC0415
    from engine.save_runtime.io import get_save_runtime_diagnostics_snapshot  # noqa: PLC0415

    snapshot = get_save_runtime_diagnostics_snapshot()
    sink = get_sink()
    for key in ("last_load_attempt", "last_save_attempt"):
        attempt = snapshot.get(key, {})
        if not isinstance(attempt, dict):
            continue
        ok = attempt.get("ok")
        if ok is True or ok is None:
            continue
        attempt_kind = str(attempt.get("kind", "") or "")
        attempt_path = str(attempt.get("path", "") or "")
        diagnostics = attempt.get("diagnostics", {})
        rows: list[dict[str, Any]] = []
        if isinstance(diagnostics, dict):
            raw_rows = diagnostics.get("diagnostics", [])
            if isinstance(raw_rows, list):
                rows = [item for item in raw_rows if isinstance(item, dict)]
        if not rows:
            sink.warn(
                "SAVE_RUNTIME_FAILED_ATTEMPT",
                f"save runtime attempt failed ({key})",
                "engine.runtime_only.entry",
                context={"attempt": key, "kind": attempt_kind, "path": attempt_path},
            )
            continue
        for row in rows:
            level = str(row.get("severity", row.get("level", "warning")) or "warning")
            code = str(row.get("code", "SAVE_RUNTIME_DIAGNOSTIC") or "SAVE_RUNTIME_DIAGNOSTIC")
            message = str(row.get("message", "save runtime diagnostic") or "save runtime diagnostic")
            source = str(row.get("source", "engine.save_runtime") or "engine.save_runtime")
            location = row.get("location")
            location_text = None if location is None else str(location)
            context = row.get("context")
            base_context: dict[str, Any] = {
                "attempt": key,
                "kind": attempt_kind,
                "path": attempt_path,
            }
            if isinstance(context, dict):
                for context_key in sorted(context.keys()):
                    base_context[str(context_key)] = context[context_key]
            sink.add(
                level,
                code,
                message,
                source,
                location=location_text,
                context=base_context,
                hint=(None if row.get("hint") is None else str(row.get("hint"))),
            )


def _diagnostics_exit_summary_lines(*, max_items: int = 5) -> list[str]:
    from engine.diagnostics import get_diagnostics_payload  # noqa: PLC0415

    payload = get_diagnostics_payload()
    errors = sum(1 for item in payload if isinstance(item, dict) and str(item.get("severity", "")) == "error")
    warnings = sum(1 for item in payload if isinstance(item, dict) and str(item.get("severity", "")) == "warning")
    infos = sum(1 for item in payload if isinstance(item, dict) and str(item.get("severity", "")) == "info")
    lines = [f"DIAGNOSTICS: E:{errors} W:{warnings} I:{infos}"]
    for index, item in enumerate(payload[: max(0, int(max_items))], start=1):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "diagnostic.unknown") or "diagnostic.unknown")
        message = str(item.get("message", "") or "")
        lines.append(f"DIAGNOSTIC[{index}]: {code} {message}")
    return lines


def _print_diagnostics_exit_summary() -> None:
    for line in _diagnostics_exit_summary_lines():
        print(line)


def _run_headless_smoke(
    *,
    target_scene: str,
    config_path: str,
    ticks: int,
    smoke_artifact: str | None,
    diagnostics_artifact: str | None = None,
    quiet: bool,
    print_diagnostics_on_exit: bool = False,
) -> int:
    from engine.config import load_config  # noqa: PLC0415
    from engine.diagnostics import clear_diagnostics  # noqa: PLC0415
    from engine.diagnostics import error as diag_error  # noqa: PLC0415
    from engine.diagnostics import get_diagnostics_payload  # noqa: PLC0415
    from engine.game_state_controller import GameStateController  # noqa: PLC0415
    from engine.logging_tools import suppress_stdout  # noqa: PLC0415
    from engine.persistence_io import write_json_atomic  # noqa: PLC0415
    from engine.public_api.runtime import load_scene_payload  # noqa: PLC0415
    from engine.runtime_only import is_forbidden_editor_import  # noqa: PLC0415

    clear_diagnostics()
    cfg = load_config(config_path)
    smoke_ticks = max(1, int(ticks))

    def _finish(code: int, *, scene_loaded: str | None = None) -> int:
        _write_diagnostics_artifact(
            path=diagnostics_artifact,
            context={
                "mode": "headless_smoke",
                "scene_requested": target_scene,
                "scene_loaded": scene_loaded,
            },
        )
        if print_diagnostics_on_exit:
            _print_diagnostics_exit_summary()
        return int(code)

    with suppress_stdout():
        payload = load_scene_payload(target_scene)
    if not isinstance(payload, dict):
        diag_error(
            "runtime_smoke.scene_load_failed",
            f"failed to load smoke scene '{target_scene}'",
            "engine.runtime_only.entry",
            location=str(target_scene),
        )
        if not quiet:
            print(f"[Mesh][RuntimeOnly] Error: failed to load smoke scene '{target_scene}'")
        return _finish(1)

    window = _RuntimeSmokeWindow(engine_config=cfg)
    state_controller = GameStateController(cast(Any, window))
    for _ in range(smoke_ticks):
        state_controller.inc_counter("runtime.smoke.tick", 1.0)

    _emit_save_runtime_snapshot_diagnostics()
    forbidden = sorted(name for name in sys.modules if is_forbidden_editor_import(name))
    if forbidden:
        diag_error(
            "runtime_smoke.forbidden_imports_detected",
            f"forbidden editor imports detected ({len(forbidden)})",
            "engine.runtime_only.entry",
            context={"count": int(len(forbidden))},
        )
    smoke_payload = {
        "ok": len(forbidden) == 0,
        "scene_loaded": str(payload.get("name") or target_scene),
        "ticks": int(smoke_ticks),
        "forbidden_imports_found": forbidden,
        "diagnostics": get_diagnostics_payload(),
    }

    artifact = str(smoke_artifact or "").strip()
    if artifact:
        write_json_atomic(Path(artifact), smoke_payload, indent=2, sort_keys=True, trailing_newline=True)

    if not quiet:
        if smoke_payload["ok"]:
            print(
                f"[Mesh][RuntimeOnly] Headless smoke OK "
                f"(scene={smoke_payload['scene_loaded']} ticks={smoke_payload['ticks']})"
            )
        else:
            print(
                f"[Mesh][RuntimeOnly] Headless smoke failed: "
                f"forbidden imports found ({len(forbidden)})"
            )
    return _finish(0 if smoke_payload["ok"] else 1, scene_loaded=str(smoke_payload["scene_loaded"]))


def run_runtime_scene(
    scene_path: str | None = None,
    *,
    config_path: str = "config.json",
    headless_smoke: bool = False,
    smoke_scene: str | None = None,
    smoke_ticks: int = DEFAULT_SMOKE_TICKS,
    smoke_artifact: str | None = None,
    diagnostics_artifact: str | None = None,
    quiet: bool = False,
    print_diagnostics_on_exit: bool = False,
) -> int:
    """Run the runtime-only scene bootstrap without editor wiring.

    The runtime-only path intentionally avoids importing ``engine.game`` and any
    editor overlays/controllers. It validates that runtime scene loading works.
    """
    from engine.config import load_config  # noqa: PLC0415
    from engine.diagnostics import add_exception as diag_add_exception  # noqa: PLC0415
    from engine.diagnostics import clear_diagnostics  # noqa: PLC0415
    from engine.diagnostics import error as diag_error  # noqa: PLC0415
    from engine.logging_tools import suppress_stdout  # noqa: PLC0415
    from engine.public_api.runtime import load_scene_payload  # noqa: PLC0415

    try:
        clear_diagnostics()
        target_scene: str | None = None

        def _finish(code: int, *, scene_loaded: str | None = None) -> int:
            _write_diagnostics_artifact(
                path=diagnostics_artifact,
                context={
                    "mode": ("headless_smoke" if headless_smoke else "runtime"),
                    "scene_requested": target_scene,
                    "scene_loaded": scene_loaded,
                },
            )
            if print_diagnostics_on_exit:
                _print_diagnostics_exit_summary()
            return int(code)
        cfg = load_config(config_path)
        if headless_smoke:
            target_scene = str(scene_path or smoke_scene or DEFAULT_SMOKE_SCENE).strip()
        else:
            target_scene = str(scene_path or cfg.start_scene or "").strip()
        if not target_scene:
            diag_error(
                "runtime_entry.missing_target_scene",
                "missing target scene",
                "engine.runtime_only.entry",
                location=str(config_path),
            )
            if not quiet:
                print("[Mesh][RuntimeOnly] Error: missing target scene")
            return _finish(2)

        if headless_smoke:
            return _run_headless_smoke(
                target_scene=target_scene,
                config_path=config_path,
                ticks=smoke_ticks,
                smoke_artifact=smoke_artifact,
                diagnostics_artifact=diagnostics_artifact,
                quiet=quiet,
                print_diagnostics_on_exit=print_diagnostics_on_exit,
            )

        # SceneLoader emits informational prints by default; keep this command
        # deterministic and CI-friendly.
        with suppress_stdout():
            payload = load_scene_payload(target_scene)
        if not isinstance(payload, dict):
            diag_error(
                "runtime_entry.scene_load_failed",
                f"failed to load scene '{target_scene}'",
                "engine.runtime_only.entry",
                location=str(target_scene),
            )
            if not quiet:
                print(f"[Mesh][RuntimeOnly] Error: failed to load scene '{target_scene}'")
            return _finish(1)

        if not quiet:
            scene_name = str(payload.get("name", "<unnamed>"))
            print(f"[Mesh][RuntimeOnly] Loaded scene '{scene_name}' from {target_scene}")
        return _finish(0, scene_loaded=str(payload.get("name", "<unnamed>")))
    except Exception as exc:  # noqa: BLE001  # REASON: runtime-only entrypoint failures should emit diagnostics and return a controlled exit code
        diag_add_exception(
            "runtime_entry.unhandled_exception",
            exc,
            "engine.runtime_only.entry",
            location=str(config_path),
        )
        if not quiet:
            print(f"[Mesh][RuntimeOnly] Error: {exc}")
        _write_diagnostics_artifact(
            path=diagnostics_artifact,
            context={
                "mode": ("headless_smoke" if headless_smoke else "runtime"),
                "scene_requested": scene_path,
            },
        )
        if print_diagnostics_on_exit:
            _print_diagnostics_exit_summary()
        return 1


__all__ = [
    "DEFAULT_SMOKE_SCENE",
    "DEFAULT_SMOKE_TICKS",
    "run_runtime_scene",
]
