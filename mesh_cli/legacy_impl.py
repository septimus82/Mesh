"""Command-line interface for Mesh Engine."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .legacy.dispatch import build_parser as _build_parser
from .legacy.dispatch import dispatch as _dispatch
from .legacy.dispatch import main as _dispatch_main
from .legacy.registry import TOOLING_EXPORT_NAMES, get_tooling_export
from engine.logging_tools import get_logger

if TYPE_CHECKING:
    from engine.config import load_config as load_config
    from engine.encounter_report import generate_encounter_report as generate_encounter_report
    from engine.tooling_runtime.macro_apply_report import MacroReportPayload
    from engine.tooling import (
        plan_linter as plan_linter,
        replay_script as replay_script,
        replay_suite as replay_suite,
        state_dump as state_dump,
        validate_all as validate_all,
        verify_demo as verify_demo,
    )
    from engine.tooling.content_inventory import list_scenes as _inventory_list_scenes
    from engine.tooling.content_inventory import list_worlds as _inventory_list_worlds

_JSON_COMMANDS: set[str] = {
    "verify-demo",
    "verify-replays",
    "verify-strict",
    "verify-all",
    "list-worlds",
    "list-encounter-presets",
    "lint-presets",
    "doctor-assets",
    "dump-state",
    "replay-script",
    "replay-suite",
}

from .headless_arcade import install_arcade_stub_if_missing as _install_arcade_stub_if_missing

_install_arcade_stub_if_missing()

logger = get_logger(__name__)

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    logger.debug("SWALLOW[%s] %s", tag, context, exc_info=True)


GameWindow = None

def get_game_window():
    """Patchable seam for importing the real GameWindow only when needed."""
    window_cls = GameWindow
    if window_cls is None:
        from engine.game import GameWindow as window_cls
    return window_cls


def _configure_stdout_newline_for_json() -> None:
    """Force LF newlines on stdout for byte-stable JSON output across platforms."""
    try:
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(newline="\n")
    except Exception:
        _log_swallow("LEGI-001", "mesh_cli.legacy_impl blanket exception fallback")
        return


def _single_line_error(text: str) -> str:
    raw = str(text or "")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = " ".join(raw.split())
    return raw


def _normalize_path_for_json(path: Path | str, *, repo_root: Path | None = None) -> str:
    p = Path(path) if not isinstance(path, Path) else path
    if repo_root is not None and not p.is_absolute():
        p = Path(repo_root) / p
    try:
        p = p.resolve()
    except Exception:
        _log_swallow("LEGI-002", "mesh_cli.legacy_impl blanket exception fallback")
        pass

    root = repo_root
    if root is not None:
        try:
            root = Path(root).resolve()
        except Exception:
            _log_swallow("LEGI-003", "mesh_cli.legacy_impl blanket exception fallback")
            root = Path(root)
        try:
            return p.relative_to(root).as_posix()
        except Exception:
            _log_swallow("LEGI-004", "mesh_cli.legacy_impl blanket exception fallback")
            pass
    return p.as_posix()


def _maybe_run_content_inventory_early() -> None:
    """Fast-path inventory commands before importing engine modules with side effects.

    This keeps `list-scenes` / `list-worlds` free of import-time engine/editor behavior.
    """
    if len(sys.argv) < 2:
        return
    command = sys.argv[1]
    if command not in {"list-worlds", "list-encounter-presets", "lint-presets"}:
        return

    parser = argparse.ArgumentParser(prog=f"python -m mesh_cli {command}")
    parser.add_argument("--out", help="Optional path to write JSON output")
    args = parser.parse_args(sys.argv[2:])

    from engine.persistence_io import dumps_json_deterministic, write_json_atomic
    from engine.logging_tools import configure_logging, suppress_stdout
    from engine.repo_root import get_repo_root
    from engine.tooling.content_inventory import list_encounter_presets, list_scenes, list_worlds
    from engine.tooling.preset_lint import lint_encounter_preset_references

    configure_logging(json_mode=True)
    try:
        with suppress_stdout():
            repo_root = get_repo_root(start=Path.cwd(), strict=True)
            if command == "list-worlds":
                payload = list_worlds(repo_root=repo_root)
            elif command == "lint-presets":
                payload = lint_encounter_preset_references(repo_root=repo_root)
            else:
                payload = list_encounter_presets(repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("LEGI-005", "mesh_cli.legacy_impl blanket exception fallback")
        payload = {"ok": False, "error": _single_line_error(f"{type(exc).__name__}: {exc}")}
        text = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)
        _configure_stdout_newline_for_json()
        sys.stdout.write(text)
        raise SystemExit(2)
    text = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)

    out_path = str(getattr(args, "out", "") or "").strip() or None
    if out_path:
        with suppress_stdout():
            write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)

    _configure_stdout_newline_for_json()
    sys.stdout.write(text)
    raise SystemExit(0 if payload.get("ok") is True else 1)


_maybe_run_content_inventory_early()

_json_mode = len(sys.argv) >= 2 and sys.argv[1] in _JSON_COMMANDS
from engine.logging_tools import configure_logging, suppress_stdout  # noqa: E402

if _json_mode:
    _configure_stdout_newline_for_json()
    configure_logging(json_mode=True)
else:
    configure_logging()


def __getattr__(name: str) -> Any:
    if name in TOOLING_EXPORT_NAMES:
        return get_tooling_export(name)
    raise AttributeError(name)



def _handle_ai_bundle(args: argparse.Namespace) -> int:
    from . import ai as ai_commands
    return ai_commands.handle(args)


def _handle_ai_history(args: argparse.Namespace) -> int:
    from . import ai as ai_commands
    return ai_commands.handle(args)


def _handle_ai_export_context(args: argparse.Namespace) -> int:
    from . import ai as ai_commands
    return ai_commands.handle(args)

def _handle_play(args: argparse.Namespace) -> int:
    from . import misc as misc_commands
    return misc_commands.handle(args)

def _emit_inventory(payload: dict, out_path: str | None) -> int:
    from engine.persistence_io import dumps_json_deterministic, write_json_atomic

    text = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)
    if out_path:
        write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(text.encode("utf-8"))
    else:
        sys.stdout.write(text)
    return 0


def _handle_list_scenes(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_list_scenes(args))


def _resolve_scene_paths(path: str) -> list[str]:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import reports as report_commands

    return report_commands._resolve_scene_paths(path)


def load_report(path: str):  # noqa: ANN201 - legacy wrapper
    # Delegation-only wrapper kept for monkeypatch seams.
    from engine.encounter_report_diff import load_report as _load_report

    return _load_report(path)


def diff_reports(old_report, new_report):  # noqa: ANN201 - legacy wrapper
    # Delegation-only wrapper kept for monkeypatch seams.
    from engine.encounter_report_diff import diff_reports as _diff_reports

    return _diff_reports(old_report, new_report)


def _process_diff_result(diff, args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import reports as report_commands

    return report_commands._process_diff_result(diff, args)


def _handle_list_worlds(args: argparse.Namespace) -> int:
    try:
        from engine.repo_root import get_repo_root
        from engine.tooling.content_inventory import list_worlds as _inventory_list_worlds

        with suppress_stdout():
            repo_root = get_repo_root(start=Path.cwd(), strict=True)
            payload = _inventory_list_worlds(repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("LEGI-006", "mesh_cli.legacy_impl blanket exception fallback")
        payload = {"ok": False, "error": _single_line_error(f"{type(exc).__name__}: {exc}")}
    out_path = str(getattr(args, "out", "") or "").strip() or None
    return _emit_inventory(payload, out_path)


def _handle_list_encounter_presets(args: argparse.Namespace) -> int:
    try:
        from engine.repo_root import get_repo_root
        from engine.tooling.content_inventory import list_encounter_presets

        with suppress_stdout():
            repo_root = get_repo_root(start=Path.cwd(), strict=True)
            payload = list_encounter_presets(repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("LEGI-007", "mesh_cli.legacy_impl blanket exception fallback")
        payload = {"ok": False, "error": _single_line_error(f"{type(exc).__name__}: {exc}")}
    out_path = str(getattr(args, "out", "") or "").strip() or None
    return _emit_inventory(payload, out_path)


def _handle_lint_presets(args: argparse.Namespace) -> int:
    from engine.persistence_io import dumps_json_deterministic, write_json_atomic

    out_path = str(getattr(args, "out", "") or "").strip() or None
    try:
        from engine.repo_root import get_repo_root
        from engine.tooling.preset_lint import lint_encounter_preset_references

        with suppress_stdout():
            repo_root = get_repo_root(start=Path.cwd(), strict=True)
            payload = lint_encounter_preset_references(repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("LEGI-008", "mesh_cli.legacy_impl blanket exception fallback")
        payload = {"ok": False, "error": _single_line_error(f"{type(exc).__name__}: {exc}")}

    if out_path:
        with suppress_stdout():
            write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)

    sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
    return 0 if payload.get("ok") is True else 1


def _handle_doctor_assets(args: argparse.Namespace) -> int:
    from . import assets as asset_commands

    return asset_commands.handle(args)


@contextlib.contextmanager
def _pushd(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _verify_all_invalid_args() -> int:
    from . import verify as verify_commands

    return int(verify_commands._verify_all_invalid_args())


def _artifact_base_dir(repo_root: Path, dir_arg: str) -> Path:
    from . import verify as verify_commands

    return Path(verify_commands._artifact_base_dir(repo_root, dir_arg))


def _write_verify_all_summary_artifact(artifact_dir: Path, payload: dict) -> None:
    from . import verify as verify_commands

    verify_commands._write_verify_all_summary_artifact(artifact_dir, payload)


def _verify_all_scene_index_out_paths(repo_root: Path, out_dir: str) -> tuple[Path, str, Path, str]:
    from . import verify as verify_commands

    scenes_write, scenes_report, worlds_write, worlds_report = verify_commands._verify_all_scene_index_out_paths(
        repo_root, out_dir
    )
    return Path(scenes_write), scenes_report, Path(worlds_write), worlds_report


def _run_verify_replays_summary(folder_path: Path) -> tuple[int, dict]:
    from . import verify as verify_commands

    code, payload = verify_commands._run_verify_replays_summary(folder_path)
    return int(code), payload


def _handle_verify_all(args: argparse.Namespace) -> int:
    from . import verify as verify_commands

    return int(verify_commands._handle_verify_all(args))


def _handle_validate(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_validate_scene_file(args))


def _handle_index(args: argparse.Namespace) -> int:
    """Run the project indexer."""
    from . import assets as asset_commands

    return asset_commands.handle(args)


def _handle_docs(args: argparse.Namespace) -> int:
    from . import misc as misc_commands
    return misc_commands.handle(args)


def _handle_wizard(args: argparse.Namespace) -> int:
    from . import misc as misc_commands
    return misc_commands.handle(args)


def _handle_new_scene(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_new_scene(args))


def _handle_new_behaviour(args: argparse.Namespace) -> int:
    from . import authoring as authoring_commands
    return authoring_commands.handle(args)


def _handle_selftest(_args: argparse.Namespace) -> int:
    """Run lightweight engine self-checks."""
    from engine.self_test import SelfTestManager

    mgr = SelfTestManager(window=None)
    results = mgr.run_all()
    print(mgr.summary(results))
    failed = any(not r.ok for r in results)
    return 1 if failed else 0


def _handle_tidy_scene(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_tidy_scene(args))


def _default_spawn_entity_id(scene_path: str, spawn_id: str, x: float, y: float) -> str:
    stem = Path(str(scene_path)).stem
    stem = _sanitize_entity_id_token(stem)
    sid = _sanitize_entity_id_token(spawn_id)
    return f"{stem}_spawn_{sid}_{_format_placeholder_id_number(x)}_{_format_placeholder_id_number(y)}_0_0"


def _format_placeholder_id_number(value: float) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return str(scene_commands._format_placeholder_id_number(value))


def _sanitize_entity_id_token(value: str) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return str(scene_commands._sanitize_entity_id_token(value))


def _default_placeholder_entity_id(scene_path: str, x: float, y: float) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return str(scene_commands._default_placeholder_entity_id(scene_path, x, y))


def _default_prefab_entity_id(scene_path: str, prefab_id: str, x: float, y: float) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return str(scene_commands._default_prefab_entity_id(scene_path, prefab_id, x, y))


def _default_transition_entity_id(scene_path: str, to_key: str, x: float, y: float) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return str(scene_commands._default_transition_entity_id(scene_path, to_key, x, y))


def _handle_scene_create(args: argparse.Namespace) -> int:
    """Create (or update) a scene JSON with a multi-layer tilemap and optional backgrounds/spawns."""
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_create(args))

def _handle_tilemap_validate(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][Tilemap] ERROR: missing scene_path")
        return 2

    path = Path(scene_path)
    if not path.exists():
        from engine.path_norm import normalize_scene_path

        print(f"[Mesh][Tilemap] ERROR: scene '{normalize_scene_path(scene_path)}' does not exist")
        return 2

    try:
        scene = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("LEGI-009", "mesh_cli.legacy_impl blanket exception fallback")
        from engine.path_norm import normalize_scene_path

        print(f"[Mesh][Tilemap] ERROR: failed to parse '{normalize_scene_path(scene_path)}': {exc}")
        return 2

    normalized_scene_path, errors = _tilemap_validate_scene_payload(scene_path, path, scene)
    if not errors:
        print(f"[Mesh][Tilemap] OK: '{normalized_scene_path}' tilemap validated")
        return 0

    for scene_id, layer_id, field, message in errors:
        layer_label = layer_id or "-"
        print(f"[Mesh][Tilemap] ERROR: {scene_id} :: {layer_label} :: {field} :: {message}")
    return 1


def _tilemap_validate_scene_payload(
    scene_path_display: str,
    scene_path: Path,
    scene: dict,
) -> tuple[str, list[tuple[str, str, str, str]]]:
    # Delegation-only wrapper: share implementation with mesh_cli.scene.
    from . import scene as scene_commands

    return cast(
        tuple[str, list[tuple[str, str, str, str]]],
        scene_commands._tilemap_validate_scene_payload(scene_path_display, scene_path, scene),
    )


def _handle_scene_tilemap_add_layer(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_add_layer(args))


def _handle_scene_tilemap_remove_layer(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_remove_layer(args))


def _tilemap_resolve_dims_for_edit(
    *,
    scene_path_display: str,
    scene_path: Path,
    tilemap: dict,
) -> tuple[int, int] | None:
    map_path_value = tilemap.get("resolved_path") or tilemap.get("path")
    if isinstance(map_path_value, str) and map_path_value.strip():
        raw_map_path = map_path_value.strip()
        candidate_path = Path(raw_map_path)
        map_candidates: list[Path] = []
        if candidate_path.is_absolute():
            map_candidates.append(candidate_path)
        else:
            map_candidates.append((scene_path.parent / candidate_path).resolve())
            map_candidates.append((Path.cwd() / candidate_path).resolve())

        chosen_map_path = map_candidates[-1] if map_candidates else candidate_path
        for candidate in map_candidates:
            if candidate.exists():
                chosen_map_path = candidate
                break

        try:
            tiled = json.loads(chosen_map_path.read_text(encoding="utf-8"))
            w = int(tiled.get("width", 0))
            h = int(tiled.get("height", 0))
            if w > 0 and h > 0:
                return w, h
        except Exception:
            _log_swallow("LEGI-010", "mesh_cli.legacy_impl blanket exception fallback")
            pass

    w_value = tilemap.get("width")
    h_value = tilemap.get("height")
    if w_value is None or h_value is None:
        print(f"[Mesh][CLI] Error: cannot determine tilemap dimensions for {scene_path_display}")
        print("[Mesh][CLI] Provide a valid tilemap.path (with width/height) or scene.tilemap.width/height.")
        return None
    try:
        w = int(w_value)
        h = int(h_value)
    except Exception:
        _log_swallow("LEGI-011", "mesh_cli.legacy_impl blanket exception fallback")
        print(f"[Mesh][CLI] Error: cannot determine tilemap dimensions for {scene_path_display}")
        print("[Mesh][CLI] Provide a valid tilemap.path (with width/height) or scene.tilemap.width/height.")
        return None
    if w <= 0 or h <= 0:
        print(f"[Mesh][CLI] Error: invalid tilemap.width/height for {scene_path_display}: {w}x{h}")
        return None
    return w, h


def _handle_scene_tilemap_fill_rect(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_fill_rect(args))


def _handle_scene_tilemap_clear_rect(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_clear_rect(args))


def _handle_scene_tilemap_paint(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_paint(args))


def _handle_scene_tilemap_brush(args: argparse.Namespace) -> int:
    from engine.paths import resolve_path
    from engine.persistence_io import write_json_atomic
    from engine.scene_loader import SceneLoader
    from engine.scene_serializer import compact_scene_payload
    from engine.tilemap_brush import apply_brush, validate_brush
    from engine.tilemap_edit import TilemapDims, ensure_tiles_array, get_layer_by_id
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_brush(args))

def _parse_tilemap_init_layer_spec(raw: str) -> tuple[str, int, float | None] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) < 2 or len(parts) > 3:
        return None
    layer_id = parts[0].strip()
    if not layer_id:
        return None
    try:
        z = int(parts[1])
    except Exception:
        _log_swallow("LEGI-012", "mesh_cli.legacy_impl blanket exception fallback")
        return None
    parallax: float | None = None
    if len(parts) == 3:
        try:
            parallax = float(parts[2])
        except Exception:
            _log_swallow("LEGI-013", "mesh_cli.legacy_impl blanket exception fallback")
            return None
    return layer_id, z, parallax


def _parse_tilemap_init_fill_spec(raw: str) -> tuple[str, int] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if ":" not in text:
        return None
    layer_id, tile_str = text.split(":", 1)
    layer_id = layer_id.strip()
    if not layer_id:
        return None
    try:
        tile = int(tile_str.strip())
    except Exception:
        _log_swallow("LEGI-014", "mesh_cli.legacy_impl blanket exception fallback")
        return None
    return layer_id, tile


def _parse_scene_create_spawn_spec(raw: str) -> tuple[str, float, float] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) != 3:
        return None
    spawn_id = parts[0].strip()
    if not spawn_id:
        return None
    try:
        x = float(parts[1])
        y = float(parts[2])
    except Exception:
        _log_swallow("LEGI-015", "mesh_cli.legacy_impl blanket exception fallback")
        return None
    return spawn_id, x, y


def _parse_scene_create_bg_spec(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) < 4 or len(parts) > 6:
        return None
    layer_id = parts[0].strip()
    layer_path = parts[1].strip()
    if not layer_id or not layer_path:
        return None
    try:
        z = int(parts[2])
        parallax = float(parts[3])
    except Exception:
        _log_swallow("LEGI-016", "mesh_cli.legacy_impl blanket exception fallback")
        return None

    def parse_bool(value: str) -> bool:
        v = str(value or "").strip().lower()
        if not v:
            return False
        if v in {"1", "true", "yes", "y", "on", "repeatx", "repeat_x"}:
            return True
        if v in {"0", "false", "no", "n", "off"}:
            return False
        return False

    repeat_x = parse_bool(parts[4]) if len(parts) >= 5 else False
    repeat_y = parse_bool(parts[5]) if len(parts) >= 6 else False
    return {
        "id": layer_id,
        "path": layer_path,
        "z": z,
        "parallax": parallax,
        "repeat_x": repeat_x,
        "repeat_y": repeat_y,
    }


def _validate_background_layers_payload(scene_path: str, scene: dict) -> list[tuple[str, str, str, str]]:
    from engine.path_norm import normalize_scene_path

    normalized_scene_path = normalize_scene_path(scene_path)
    raw_layers = scene.get("background_layers")
    if raw_layers is None:
        return []

    errors: list[tuple[str, str, str, str]] = []

    def add_error(layer_id: str, field: str, message: str) -> None:
        errors.append((normalized_scene_path, str(layer_id or ""), str(field), str(message)))

    if not isinstance(raw_layers, list):
        add_error("", "background_layers", "must be an array")
        errors.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
        return errors

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

    errors.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return errors


def _handle_scene_tilemap_init(args: argparse.Namespace) -> int:
    """Initialize tilemap.tile_layers grids with in-scene dimensions (idempotent)."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_init(args))

def _handle_scene_tilemap_resize(args: argparse.Namespace) -> int:
    """Resize tilemap.tile_layers grids, preserving content by anchor (idempotent)."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_resize(args))

def _handle_scene_tilemap_flood_fill(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_tilemap_flood_fill(args))

def _tilemap_try_resolve_tile_size_for_stamp(
    *,
    scene_path: Path,
    tilemap: dict,
) -> tuple[int, int] | None:
    tw_scene = tilemap.get("tilewidth")
    th_scene = tilemap.get("tileheight")
    if isinstance(tw_scene, int) and isinstance(th_scene, int) and int(tw_scene) > 0 and int(th_scene) > 0:
        return int(tw_scene), int(th_scene)

    map_path_value = tilemap.get("resolved_path") or tilemap.get("path")
    if not isinstance(map_path_value, str) or not map_path_value.strip():
        return None

    raw_map_path = map_path_value.strip()
    candidate_path = Path(raw_map_path)
    map_candidates: list[Path] = []
    if candidate_path.is_absolute():
        map_candidates.append(candidate_path)
    else:
        map_candidates.append((scene_path.parent / candidate_path).resolve())
        map_candidates.append((Path.cwd() / candidate_path).resolve())

    chosen_map_path = map_candidates[-1] if map_candidates else candidate_path
    for candidate in map_candidates:
        if candidate.exists():
            chosen_map_path = candidate
            break

    try:
        tiled = json.loads(chosen_map_path.read_text(encoding="utf-8"))
    except Exception:
        _log_swallow("LEGI-017", "mesh_cli.legacy_impl blanket exception fallback")
        return None
    try:
        tw = int(tiled.get("tilewidth", 0))
        th = int(tiled.get("tileheight", 0))
    except Exception:
        _log_swallow("LEGI-018", "mesh_cli.legacy_impl blanket exception fallback")
        return None
    if tw > 0 and th > 0:
        return tw, th
    return None


def _default_stamp_entity_id(
    scene_path: str,
    *,
    id_prefix: str,
    id_suffix: str,
    origin_x: int,
    origin_y: int,
) -> str:
    stem = Path(str(scene_path)).stem
    stem = _sanitize_entity_id_token(stem)
    prefix = _sanitize_entity_id_token(id_prefix)
    suffix = _sanitize_entity_id_token(id_suffix)
    return f"{stem}_{prefix}_{suffix}_{origin_x}_{origin_y}_0_0"


def _handle_scene_stamp(args: argparse.Namespace) -> int:
    """Apply a stamp JSON: tile edits + optional prefab entity placements (idempotent)."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_stamp(args))

def _handle_scene_stamp_report_legacy(args: argparse.Namespace) -> int:
    """Compute a dry-run report of what `scene stamp` would change (no writes)."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_stamp_report_legacy(args))

def _handle_scene_stamp_report(args: argparse.Namespace) -> int:
    """Compute a dry-run report of what `scene stamp` would change (no writes)."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_stamp_report(args))

def _handle_scene_macro_report(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_macro_report(args))

def _compute_scene_macro_apply(
    *,
    scene_payload: dict[str, Any],
    scene_path: str,
    macro_path: str,
    raw_args: list[str],
    anchor_override: str | None,
    primary_entity_id: str | None = None,
    cursor_world_pos: tuple[float, float] | None = None,
) -> tuple[dict[str, Any], MacroReportPayload]:
    from engine.tooling_runtime.macro_apply_report import compute_scene_macro_report

    typed_result: tuple[dict[str, Any], MacroReportPayload]

    result = compute_scene_macro_report(
        scene_payload=scene_payload,
        scene_path=scene_path,
        macro_path=macro_path,
        raw_args=raw_args,
        anchor_override=anchor_override,
        cursor_world_pos=cursor_world_pos,
        primary_entity_id=primary_entity_id,
    )
    typed_result = (result.after_payload, result.report)
    return typed_result


def _handle_scene_macro_apply(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_macro_apply(args))

def _dict_diffs(expected: dict, actual: dict, *, prefix: str = "") -> list[str]:
    diffs: list[str] = []
    for key in sorted(expected.keys()):
        path = f"{prefix}{key}"
        if key not in actual:
            diffs.append(f"missing {path}")
            continue
        exp = expected[key]
        act = actual[key]
        if isinstance(exp, dict) and isinstance(act, dict):
            diffs.extend(_dict_diffs(exp, act, prefix=f"{path}."))
            continue
        if exp != act:
            diffs.append(f"mismatch {path}: expected={exp!r} actual={act!r}")
    return diffs


def _handle_scene_add_placeholder(args: argparse.Namespace) -> int:
    """Append a theme_enemy_placeholder entity into an existing scene JSON."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_add_placeholder(args))

def _handle_scene_add_entity(args: argparse.Namespace) -> int:
    """Insert or update a prefab-backed entity in a scene (idempotent)."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_add_entity(args))

def _handle_scene_add_triggerzone_objective(args: argparse.Namespace) -> int:
    """Insert a TriggerZone + SetGameStateOnEvent pair for objective beats."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_add_triggerzone_objective(args))

def _handle_scene_add_dialogue_choice_flag(args: argparse.Namespace) -> int:
    """Wire a Dialogue choice to a SetGameStateOnEvent flag setter."""
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_add_dialogue_choice_flag(args))

def _handle_validate_world(args: argparse.Namespace) -> int:
    """Validate world structure and links."""
    from . import world as world_commands

    return world_commands._handle_validate_world(args)


def _handle_world_add_scene(args: argparse.Namespace) -> int:
    """Add or update a scene entry in a world file (idempotent)."""
    from . import world as world_commands

    return world_commands._handle_world_add_scene(args)


def _scene_transition_config(
    *,
    target_scene: str,
    spawn_id: str,
    x: float,
    y: float,
    name: str,
    entity_id: str,
) -> dict[str, Any]:
    from . import world as world_commands

    return world_commands._scene_transition_config(
        target_scene=target_scene,
        spawn_id=spawn_id,
        x=x,
        y=y,
        name=name,
        entity_id=entity_id,
    )


def _ensure_scene_transition_entity(
    *,
    entities: list,
    entity_id: str,
    target_scene: str,
    spawn_id: str,
    x: float,
    y: float,
    name: str,
) -> tuple[bool, str | None]:
    """Return (changed, error_message)."""
    from . import world as world_commands

    return world_commands._ensure_scene_transition_entity(
        entities=entities,
        entity_id=entity_id,
        target_scene=target_scene,
        spawn_id=spawn_id,
        x=x,
        y=y,
        name=name,
    )


def _handle_world_link_scenes(args: argparse.Namespace) -> int:
    """Insert SceneTransition entities into scenes for a world link (idempotent)."""
    from . import world as world_commands

    return world_commands._handle_world_link_scenes(args)



def _handle_room_scaffold(args: argparse.Namespace) -> int:
    """Create a new room scene and wire it into a world using existing authoring primitives."""
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import room as room_commands

    return room_commands._handle_room_scaffold(args)


def _handle_validate_events(args: argparse.Namespace) -> int:
    """Run the event validator."""
    from . import qa as qa_commands

    return qa_commands._handle_validate_events(args)


def _handle_validate_all(args: argparse.Namespace) -> int:
    """Run the unified validator."""
    from . import qa as qa_commands

    return qa_commands._handle_validate_all(args)


def _handle_new_quest(args: argparse.Namespace) -> int:
    from . import authoring as authoring_commands
    return authoring_commands.handle(args)


def _handle_world_graph(args: argparse.Namespace) -> int:
    """Export world graph to DOT format."""
    from . import world as world_commands

    return world_commands._handle_world_graph(args)


def _handle_polish(args: argparse.Namespace) -> int:
    """Run the polish command."""
    from . import assets as asset_commands

    return asset_commands.handle(args)


def _handle_new_npc(args: argparse.Namespace) -> int:
    from . import authoring as authoring_commands
    return authoring_commands.handle(args)


def _handle_check(args: argparse.Namespace) -> int:
    """Run the quality gate check."""
    from . import qa as qa_commands

    return qa_commands._handle_check(args)


def _handle_demo(args: argparse.Namespace) -> int:
    from . import misc as misc_commands

    return misc_commands._handle_demo(args)


def _handle_dump_state(args: argparse.Namespace) -> int:
    """Dump deterministic state snapshot."""
    from engine.logging_tools import suppress_stdout
    from engine.persistence_io import dumps_json_deterministic, write_json_atomic
    load_config = globals().get("load_config") or get_tooling_export("load_config")
    state_dump = globals().get("state_dump") or get_tooling_export("state_dump")

    config = load_config()
    window = get_game_window()(
        width=config.width,
        height=config.height,
        title=config.title,
        fullscreen=config.fullscreen,
        vsync=config.vsync,
        config=config,
        config_path="config.json",
    )

    try:
        with suppress_stdout():
            window.load_scene(config.start_scene)
            payload = state_dump.dump_state(window)

        out_path = getattr(args, "out", None)
        if out_path:
            with suppress_stdout():
                write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)

        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 0
    except Exception:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("LEGI-019", "mesh_cli.legacy_impl blanket exception fallback")
        payload = {"ok": False, "code": 1, "error": "dump_state.failed"}
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    finally:
        try:
            window.close()
        except Exception:
            _log_swallow("LEGI-020", "mesh_cli.legacy_impl blanket exception fallback")
            pass


def _handle_demo_scaffold_objective(args: argparse.Namespace) -> int:
    """Scaffold a 2–3 beat objective path across multiple scenes.

    Composes existing scene authoring handlers (no JSON mutation duplicated here).
    """
    started_toast = "Objective: Enter the cellar"
    mid_toast = "Objective: Find the cellar"
    done_toast = "Objective complete!"

    start_scene = str(getattr(args, "start_scene", "") or "").strip()
    speaker_id = str(getattr(args, "speaker_id", "") or "").strip()
    choice_id = str(getattr(args, "choice_id", "") or "").strip()
    choice_text = str(getattr(args, "choice_text", "") or "").strip()

    interior_scene = str(getattr(args, "interior_scene", "") or "").strip()
    interior_x = float(getattr(args, "interior_x", 0.0))
    interior_y = float(getattr(args, "interior_y", 0.0))
    interior_radius = float(getattr(args, "interior_radius", 0.0))

    cellar_scene = str(getattr(args, "cellar_scene", "") or "").strip()
    cellar_x = float(getattr(args, "cellar_x", 0.0))
    cellar_y = float(getattr(args, "cellar_y", 0.0))
    cellar_radius = float(getattr(args, "cellar_radius", 0.0))

    flag_started = str(getattr(args, "flag_started", "") or "").strip()
    flag_mid = str(getattr(args, "flag_mid", "") or "").strip()
    flag_done = str(getattr(args, "flag_done", "") or "").strip()

    if not (start_scene and speaker_id and choice_id and choice_text and interior_scene and cellar_scene):
        print("[Mesh][CLI] Error: missing required scaffold arguments")
        return 2
    if not (flag_started and flag_mid and flag_done):
        print("[Mesh][CLI] Error: missing --flag-started/--flag-mid/--flag-done")
        return 2

    # Beat 1: dialogue choice -> started flag
    started_args = argparse.Namespace(
        scene_path=start_scene,
        speaker_id=speaker_id,
        choice_id=choice_id,
        choice_text=choice_text,
        set_flag=flag_started,
        require=[],
        forbid=[flag_started],
        toast=started_toast,
        toast_seconds=3.0,
    )
    code = _handle_scene_add_dialogue_choice_flag(started_args)
    if code != 0:
        return int(code)

    # Beat 2: interior trigger -> mid flag
    mid_zone_id = f"ObjectiveZone_{_sanitize_entity_id_token(flag_mid)}"
    mid_args = argparse.Namespace(
        scene_path=interior_scene,
        x=interior_x,
        y=interior_y,
        radius=interior_radius,
        zone_id=mid_zone_id,
        set_flag=flag_mid,
        require=[flag_started],
        forbid=[flag_mid],
        toast=mid_toast,
        toast_seconds=3.0,
    )
    code = _handle_scene_add_triggerzone_objective(mid_args)
    if code != 0:
        return int(code)

    # Beat 3: cellar trigger -> done flag (requires started + mid for sequencing)
    done_zone_id = f"ObjectiveZone_{_sanitize_entity_id_token(flag_done)}"
    done_args = argparse.Namespace(
        scene_path=cellar_scene,
        x=cellar_x,
        y=cellar_y,
        radius=cellar_radius,
        zone_id=done_zone_id,
        set_flag=flag_done,
        require=[flag_started, flag_mid],
        forbid=[flag_done],
        toast=done_toast,
        toast_seconds=3.0,
    )
    code = _handle_scene_add_triggerzone_objective(done_args)
    return int(code)


def _handle_explain(args: argparse.Namespace) -> int:
    from . import qa as qa_commands

    return qa_commands._handle_explain(args)

def _handle_place_npc(args: argparse.Namespace) -> int:
    from . import authoring as authoring_commands
    return authoring_commands.handle(args)


def _handle_apply_plan(args: argparse.Namespace) -> int:
    from . import ai as ai_commands
    return ai_commands.handle(args)

def _handle_plan_lint(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import plan as plan_commands

    return plan_commands._handle_plan_lint(args)


def _handle_plan_lint_ai(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import plan as plan_commands

    return plan_commands._handle_plan_lint_ai(args)

def _handle_plan_test_ai(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import plan as plan_commands

    return plan_commands._handle_plan_test_ai(args)


def _handle_plan_diff(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import plan as plan_commands

    return plan_commands._handle_plan_diff(args)

def _handle_plan_test(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import plan as plan_commands

    return plan_commands._handle_plan_test(args)

def _handle_plan_history(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import plan as plan_commands

    return plan_commands._handle_plan_history(args)

def _handle_plan_show(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import plan as plan_commands

    return plan_commands._handle_plan_show(args)

def _handle_plan_summarize(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import plan as plan_commands

    return plan_commands._handle_plan_summarize(args)

def _handle_ai_generate_plan(args: argparse.Namespace) -> int:
    from . import ai as ai_commands
    return ai_commands.handle(args)


def _handle_undo_last_plan(args: argparse.Namespace) -> int:
    from . import ai as ai_commands
    return ai_commands.handle(args)


def _handle_auto_wire_transitions(args: argparse.Namespace) -> int:
    """Run the auto-wire transitions tool."""
    from . import world as world_commands

    return world_commands._handle_auto_wire_transitions(args)

def _handle_cli_smoke(args: argparse.Namespace) -> int:
    """Run a quick smoke test of the CLI tools."""
    from . import qa as qa_commands

    return qa_commands._handle_cli_smoke(args)


def _handle_scene_validate_backgrounds(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_validate_backgrounds(args))

def _handle_scene_backgrounds_add_layer(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_backgrounds_add_layer(args))

def _handle_scene_backgrounds_remove_layer(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_scene_backgrounds_remove_layer(args))


def build_parser() -> argparse.ArgumentParser:
    return _build_parser()


def create_parser() -> argparse.ArgumentParser:
    return build_parser()


def _handle_edit_scene(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_edit_scene(args))


def _handle_add_puzzle(args: argparse.Namespace) -> int:
    from . import authoring as authoring_commands
    return authoring_commands.handle(args)


def dispatch(args: argparse.Namespace, *, parser: argparse.ArgumentParser | None = None) -> int:
    return int(_dispatch(args, parser=parser, impl_module=sys.modules[__name__]))


def main(argv: list[str] | None = None) -> int:
    return int(_dispatch_main(argv, impl_module=sys.modules[__name__]))


if __name__ == "__main__":
    sys.exit(main())
