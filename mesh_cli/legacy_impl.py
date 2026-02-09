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
from typing import Any

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

from .verify import VERIFY_ALL_STEPS
from engine.tooling_runtime.brush_report import _scene_tilemap_maybe_migrate_layers

from .headless_arcade import install_arcade_stub_if_missing as _install_arcade_stub_if_missing

_install_arcade_stub_if_missing()

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
        pass

    root = repo_root
    if root is not None:
        try:
            root = Path(root).resolve()
        except Exception:
            root = Path(root)
        try:
            return p.relative_to(root).as_posix()
        except Exception:
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
    except Exception as exc:  # noqa: BLE001
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
    with suppress_stdout():
        from engine.config import load_config
        from engine.version import ENGINE_VERSION
        from engine.encounter_report import generate_encounter_report
        from engine.encounter_report_diff import diff_reports, load_report
        from engine.tooling import (
            ai_plan_command,
            build_demo_command,
            check,
            cli_snapshot_command,
            content_commands,
            dist_command,
            docs_command,
            doctor_command,
            explain,
            event_validator,
            golden_slice_scaffold,
            graph,
            migrate_command,
            pack_commands,
            plan_cli,
            plan_diff,
            plan_fix_command,
            plan_history,
            plan_linter,
            polish,
            pipeline_runner,
            prefab_cli,
            preset_commands,
            project_index,
            recipes_command,
            release_command,
            replay_goldens_command,
            scaffold,
            scene_validate,
            trace_command,
            triage_command,
            validate_all,
            verify_demo,
            wizard_command,
            state_dump,
            replay_script,
            replay_suite,
            replay_suite,
        )
        from engine.tooling.auto_wire import AutoWireController
        from engine.tooling.plan_executor import PlanExecutor
        from engine.tooling.plan_types import Action, Plan
        from engine.tooling.content_inventory import list_scenes as _inventory_list_scenes
        from engine.tooling.content_inventory import list_worlds as _inventory_list_worlds
else:
    configure_logging()
    from engine.config import load_config
    from engine.version import ENGINE_VERSION
    from engine.encounter_report import generate_encounter_report
    from engine.encounter_report_diff import diff_reports, load_report
    from engine.tooling import (
        ai_plan_command,
        build_demo_command,
        check,
        cli_snapshot_command,
        content_commands,
        dist_command,
        docs_command,
        doctor_command,
        explain,
        event_validator,
        golden_slice_scaffold,
        graph,
        migrate_command,
        pack_commands,
        plan_cli,
        plan_diff,
        plan_fix_command,
        plan_history,
        plan_linter,
        polish,
        pipeline_runner,
        prefab_cli,
        preset_commands,
        project_index,
        recipes_command,
        release_command,
        replay_goldens_command,
        scaffold,
        scene_validate,
        trace_command,
        triage_command,
        validate_all,
        verify_demo,
        wizard_command,
        state_dump,
        replay_script,
        replay_suite,
        replay_suite,
    )
    from engine.tooling.auto_wire import AutoWireController
    from engine.tooling.plan_executor import PlanExecutor
    from engine.tooling.plan_types import Action, Plan
    from engine.tooling.content_inventory import list_scenes as _inventory_list_scenes
    from engine.tooling.content_inventory import list_worlds as _inventory_list_worlds



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

    return scene_commands._handle_list_scenes(args)


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

        with suppress_stdout():
            repo_root = get_repo_root(start=Path.cwd(), strict=True)
            payload = _inventory_list_worlds(repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
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

    return scene_commands._handle_validate_scene_file(args)


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

    return scene_commands._handle_new_scene(args)


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

    return scene_commands._handle_tidy_scene(args)


def _default_spawn_entity_id(scene_path: str, spawn_id: str, x: float, y: float) -> str:
    stem = Path(str(scene_path)).stem
    stem = _sanitize_entity_id_token(stem)
    sid = _sanitize_entity_id_token(spawn_id)
    return f"{stem}_spawn_{sid}_{_format_placeholder_id_number(x)}_{_format_placeholder_id_number(y)}_0_0"


def _format_placeholder_id_number(value: float) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return scene_commands._format_placeholder_id_number(value)


def _sanitize_entity_id_token(value: str) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return scene_commands._sanitize_entity_id_token(value)


def _default_placeholder_entity_id(scene_path: str, x: float, y: float) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return scene_commands._default_placeholder_entity_id(scene_path, x, y)


def _default_prefab_entity_id(scene_path: str, prefab_id: str, x: float, y: float) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return scene_commands._default_prefab_entity_id(scene_path, prefab_id, x, y)


def _default_transition_entity_id(scene_path: str, to_key: str, x: float, y: float) -> str:
    # Delegation-only wrapper kept for compatibility.
    from . import scene as scene_commands

    return scene_commands._default_transition_entity_id(scene_path, to_key, x, y)


def _handle_scene_create(args: argparse.Namespace) -> int:
    """Create (or update) a scene JSON with a multi-layer tilemap and optional backgrounds/spawns."""
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import scene as scene_commands

    return scene_commands._handle_scene_create(args)

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
    except Exception as exc:  # noqa: BLE001
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

    return scene_commands._tilemap_validate_scene_payload(scene_path_display, scene_path, scene)


def _handle_scene_tilemap_add_layer(args: argparse.Namespace) -> int:
    # Delegation-only wrapper kept for monkeypatch seams.
    from . import scene as scene_commands

    return scene_commands._handle_scene_tilemap_add_layer(args)


def _handle_scene_tilemap_remove_layer(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_tilemap_remove_layer(args)


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
        print(f"[Mesh][CLI] Error: cannot determine tilemap dimensions for {scene_path_display}")
        print("[Mesh][CLI] Provide a valid tilemap.path (with width/height) or scene.tilemap.width/height.")
        return None
    if w <= 0 or h <= 0:
        print(f"[Mesh][CLI] Error: invalid tilemap.width/height for {scene_path_display}: {w}x{h}")
        return None
    return w, h


def _handle_scene_tilemap_fill_rect(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_tilemap_fill_rect(args)


def _handle_scene_tilemap_clear_rect(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_tilemap_clear_rect(args)


def _handle_scene_tilemap_paint(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_tilemap_paint(args)


def _handle_scene_tilemap_brush(args: argparse.Namespace) -> int:
    from engine.paths import resolve_path
    from engine.persistence_io import write_json_atomic
    from engine.scene_loader import SceneLoader
    from engine.scene_serializer import compact_scene_payload
    from engine.tilemap_brush import apply_brush, validate_brush
    from engine.tilemap_edit import TilemapDims, ensure_tiles_array, get_layer_by_id
    from . import scene as scene_commands

    return scene_commands._handle_scene_tilemap_brush(args)

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
        return None
    parallax: float | None = None
    if len(parts) == 3:
        try:
            parallax = float(parts[2])
        except Exception:
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

    return scene_commands._handle_scene_tilemap_init(args)

def _handle_scene_tilemap_resize(args: argparse.Namespace) -> int:
    """Resize tilemap.tile_layers grids, preserving content by anchor (idempotent)."""
    from . import scene as scene_commands

    return scene_commands._handle_scene_tilemap_resize(args)

def _handle_scene_tilemap_flood_fill(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_tilemap_flood_fill(args)

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
        return None
    try:
        tw = int(tiled.get("tilewidth", 0))
        th = int(tiled.get("tileheight", 0))
    except Exception:
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

    return scene_commands._handle_scene_stamp(args)

def _handle_scene_stamp_report_legacy(args: argparse.Namespace) -> int:
    """Compute a dry-run report of what `scene stamp` would change (no writes)."""
    from . import scene as scene_commands

    return scene_commands._handle_scene_stamp_report_legacy(args)

def _handle_scene_stamp_report(args: argparse.Namespace) -> int:
    """Compute a dry-run report of what `scene stamp` would change (no writes)."""
    from . import scene as scene_commands

    return scene_commands._handle_scene_stamp_report(args)

def _handle_scene_macro_report(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_macro_report(args)

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
    from engine.tooling_runtime.macro_apply_report import compute_scene_macro_report

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


def _handle_scene_macro_apply(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_macro_apply(args)

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

    return scene_commands._handle_scene_add_placeholder(args)

def _handle_scene_add_entity(args: argparse.Namespace) -> int:
    """Insert or update a prefab-backed entity in a scene (idempotent)."""
    from . import scene as scene_commands

    return scene_commands._handle_scene_add_entity(args)

def _handle_scene_add_triggerzone_objective(args: argparse.Namespace) -> int:
    """Insert a TriggerZone + SetGameStateOnEvent pair for objective beats."""
    from . import scene as scene_commands

    return scene_commands._handle_scene_add_triggerzone_objective(args)

def _handle_scene_add_dialogue_choice_flag(args: argparse.Namespace) -> int:
    """Wire a Dialogue choice to a SetGameStateOnEvent flag setter."""
    from . import scene as scene_commands

    return scene_commands._handle_scene_add_dialogue_choice_flag(args)

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
    from engine.tooling import state_dump

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
    except Exception:  # noqa: BLE001
        payload = {"ok": False, "code": 1, "error": "dump_state.failed"}
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    finally:
        try:
            window.close()
        except Exception:
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

    return scene_commands._handle_scene_validate_backgrounds(args)

def _handle_scene_backgrounds_add_layer(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_backgrounds_add_layer(args)

def _handle_scene_backgrounds_remove_layer(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return scene_commands._handle_scene_backgrounds_remove_layer(args)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mesh Engine CLI")
    parser.add_argument("--version", action="store_true", help="Show engine version")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # --- Core Commands ---

    # Play
    from . import misc as misc_commands
    misc_commands.register(subparsers)

    # Debug bundle
    from . import debug as debug_commands
    debug_commands.register(subparsers)

    # Check (Moved to qa.py)

    # Verify commands (verify-demo/verify-strict/verify-replays/verify-all)
    from . import verify as verify_commands

    verify_commands.register(subparsers)

    # Pack manifests/registry
    from . import pack as pack_commands
    pack_commands.register(subparsers)

    # FX tooling
    from . import fx as fx_commands
    fx_commands.register(subparsers)

    # Release contract
    from . import release_contract as release_contract_commands
    release_contract_commands.register(subparsers)

    # Release pipeline
    from . import release as release_commands
    release_commands.register(subparsers)

    # Perf Run
    from engine.tooling import perf_command
    perf_command.add_perf_run_command(subparsers)

    # Inventory
    list_worlds_parser = subparsers.add_parser("list-worlds", help="List and analyze world JSON files (no engine load)")
    list_worlds_parser.add_argument("--out", help="Optional path to write JSON output")

    list_presets_parser = subparsers.add_parser(
        "list-encounter-presets", help="List available encounter preset ids (no engine load)"
    )
    list_presets_parser.add_argument("--out", help="Optional path to write JSON output")

    lint_presets_parser = subparsers.add_parser(
        "lint-presets",
        help="Check that all scene encounter_preset_id values exist (no engine load)",
    )
    lint_presets_parser.add_argument("--out", help="Optional path to write JSON output")

    # Asset doctor (Moved to assets.py)

    # Dump state (Moved to misc.py)

    # Replay script (Moved to replay.py)

    # Replay suite (Moved to replay.py)

    # Docs (Moved to misc.py)

    # Wizard (Moved to misc.py)

    # --- Content Management ---

    from . import assets as asset_commands
    asset_commands.register(subparsers)

    # AI Audit (Moved to ai.py)

    # Authoring Commands
    from . import authoring as authoring_commands
    authoring_commands.register(subparsers)

    # New Prefab (Moved to prefabs.py)

    # Place Prefab (Moved to prefabs.py)

    # Add Puzzle (Moved to authoring.py)

    # Scene utilities
    from . import scene as scene_commands

    scene_commands.register(subparsers)

    # World authoring
    from . import world as world_commands

    world_commands.register(subparsers)

    # Room scaffolding
    from . import room as room_commands

    room_commands.register(subparsers)

    # Tilemap utilities
    tilemap_parser = subparsers.add_parser("tilemap", help="Tilemap utilities")
    tilemap_subparsers = tilemap_parser.add_subparsers(dest="tilemap_command", help="Tilemap subcommand")
    tilemap_validate_parser = tilemap_subparsers.add_parser(
        "validate",
        help="Validate tilemap multi-layer configuration in a scene",
    )
    tilemap_validate_parser.add_argument("scene_path", help="Path to scene file")

    # Stamp utilities (Moved to stamps.py)

    # Brush utilities (Moved to stamps.py)

    # Macro asset utilities
    from . import macro as macro_commands

    macro_commands.register(subparsers)

    # Capture catalog utilities (Moved to stamps.py)

    # Sprite utilities (Moved to assets.py)

    # Schema Fix IDs (Moved to assets.py)

    # Polish (Moved to assets.py)

    # Migrate (Moved to assets.py)

    # --- Validation ---

    from . import qa as qa_commands
    qa_commands.register(subparsers)

    # Validate World (Moved to world.py)

    # Validate Events (Moved to qa.py)

    # Validate All (Moved to qa.py)

    # Selftest
    subparsers.add_parser("selftest", help="Run engine self-tests")

    # Doctor (Moved to qa.py)

    # Explain (Moved to qa.py)

    from . import pipeline as pipeline_commands
    pipeline_commands.register(subparsers)

    # CLI Smoke (Moved to qa.py)



    # Triage
    triage_command.add_triage_command(subparsers)

    # Assist
    from engine.tooling import assist_command
    assist_command.add_assist_command(subparsers)

    # --- Planning & AI ---

    # Plan
    from . import plan as plan_commands

    plan_commands.register(subparsers)


    # AI & Planning
    from . import ai as ai_commands
    ai_commands.register(subparsers)

    # Auto Wire (Moved to world.py)

    # World Graph (Moved to world.py)

    # Trace (Moved to replay.py)

    from . import reports as report_commands
    report_commands.register(subparsers)

    from . import stamps as stamp_commands
    stamp_commands.register(subparsers)

    from . import prefabs as prefab_commands
    prefab_commands.register(subparsers)

    # --- Tooling Modules ---

    from . import replay as replay_commands
    replay_commands.register(subparsers)

    from . import cutscene as cutscene_commands
    cutscene_commands.register(subparsers)

    from . import build as build_commands
    build_commands.register(subparsers)

    from . import export as export_commands
    export_commands.register(subparsers)

    # Prefab Management (Moved to prefabs.py)

    return parser


def _handle_edit_scene(args: argparse.Namespace) -> int:
    from . import scene as scene_commands

    return int(scene_commands._handle_edit_scene(args))


def _handle_add_puzzle(args: argparse.Namespace) -> int:
    from . import authoring as authoring_commands
    return authoring_commands.handle(args)


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the mesh CLI."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"Mesh Engine {ENGINE_VERSION}")
        return 0

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "play":
        return _handle_play(args)
    if args.command == "demo":
        if getattr(args, "demo_command", None) in (None, "", "run"):
            return _handle_demo(args)
        if getattr(args, "demo_command", None) == "scaffold-objective":
            return _handle_demo_scaffold_objective(args)
        print("[Mesh][CLI] Error: missing demo subcommand")
        return 2
    if args.command == "validate":
        from . import scene as scene_commands

        return scene_commands.handle(args)
    if args.command == "index":
        return _handle_index(args)
    if args.command == "docs":
        return _handle_docs(args)
    if args.command == "wizard":
        return _handle_wizard(args)
    if args.command == "new-scene":
        from . import scene as scene_commands

        return scene_commands.handle(args)
    if args.command == "new-behaviour":
        return _handle_new_behaviour(args)
    if args.command == "selftest":
        return _handle_selftest(args)
    if args.command == "ai-audit":
        from . import ai as ai_commands
        return ai_commands.handle(args)
    if args.command == "tidy-scene":
        from . import scene as scene_commands

        return scene_commands.handle(args)
    if args.command == "scene":
        from . import scene as scene_commands

        return scene_commands.handle(args)
    if args.command == "world":
        from . import world as world_commands

        return world_commands.handle(args)
    if args.command == "room":
        from . import room as room_commands

        return room_commands.handle(args)
    if args.command == "tilemap":
        if getattr(args, "tilemap_command", None) == "validate":
            return _handle_tilemap_validate(args)
        print("[Mesh][CLI] Error: missing tilemap subcommand")
        return 2
    if args.command == "stamp":
        from . import stamps as stamp_commands

        return stamp_commands.handle(args)

    if args.command == "brush":
        from . import stamps as stamp_commands

        return stamp_commands.handle(args)

    if args.command == "macro":
        from . import macro as macro_commands

        return macro_commands.handle(args)

    if args.command == "pack":
        from . import pack as pack_commands

        return pack_commands.handle(args)

    if args.command == "fx":
        from . import fx as fx_commands

        return fx_commands.handle(args)

    if args.command == "capture":
        from . import stamps as stamp_commands

        return stamp_commands.handle(args)

    if args.command == "sprite":
        from . import assets as asset_commands

        return asset_commands.handle(args)
    if args.command == "validate-world":
        from . import world as world_commands

        return world_commands.handle(args)
    if args.command == "validate-events":
        from . import qa as qa_commands

        return qa_commands.handle(args)
    if args.command == "validate-all":
        from . import qa as qa_commands

        return qa_commands.handle(args)
    if args.command == "doctor":
        from . import qa as qa_commands

        return qa_commands.handle(args)
    if args.command == "explain":
        from . import qa as qa_commands

        return qa_commands.handle(args)
    if args.command == "schema-fix-ids":
        from engine.tooling import schema_fix_ids

        argv2: list[str] = []
        if getattr(args, "dry_run", False):
            argv2.append("--dry-run")
        schema_fix_paths = getattr(args, "paths", None)
        if schema_fix_paths:
            argv2.append("--paths")
            argv2.extend(list(schema_fix_paths))
        return schema_fix_ids.main(argv2)
    if args.command == "new-quest":
        return _handle_new_quest(args)
    if args.command == "world-graph":
        from . import world as world_commands

        return world_commands.handle(args)
    if args.command == "polish":
        return _handle_polish(args)
    if args.command == "new-npc":
        return _handle_new_npc(args)
    if args.command in {"new-prefab", "place-prefab", "prefab"}:
        from . import prefabs as prefab_commands

        return prefab_commands.handle(args)
    if args.command == "check":
        from . import qa as qa_commands

        return qa_commands.handle(args)
    if args.command in {"verify-demo", "verify-strict", "verify-replays", "verify-all"}:
        from . import verify as verify_commands

        return verify_commands.handle(args)
    if args.command == "list-scenes":
        from . import scene as scene_commands

        return scene_commands.handle(args)
    if args.command == "list-worlds":
        return _handle_list_worlds(args)
    if args.command == "list-encounter-presets":
        return _handle_list_encounter_presets(args)
    if args.command == "lint-presets":
        return _handle_lint_presets(args)
    if args.command == "doctor-assets":
        return _handle_doctor_assets(args)
    if args.command == "assets":
        from . import assets as asset_commands

        return asset_commands.handle(args)
    if args.command == "release":
        from . import release as release_commands

        return release_commands.handle(args)
    if args.command == "debug":
        from . import debug as debug_commands

        return debug_commands.handle(args)
    if args.command == "dump-state":
        return _handle_dump_state(args)
    if args.command == "replay-script":
        from . import replay as replay_commands

        return replay_commands.handle(args)

    if args.command == "replay-suite":
        from . import replay as replay_commands

        return replay_commands.handle(args)
    if args.command == "replay-hash":
        from . import replay as replay_commands

        return replay_commands.handle(args)
    if args.command == "demo":
        return _handle_demo(args)
    if args.command in {"pipeline", "recipes", "run-preset", "preset"}:
        from . import pipeline as pipeline_commands

        return pipeline_commands.handle(args)
    if args.command == "place-npc":
        return _handle_place_npc(args)
    if args.command == "trace":
        from . import replay as replay_commands

        return replay_commands.handle(args)
    if args.command in {"cutscene-simulate", "cutscene-validate"}:
        from . import cutscene as cutscene_commands

        return cutscene_commands.handle(args)
    if args.command == "migrate":
        return migrate_command.handle_migrate(args)
    if args.command in {"build-demo", "dist", "release", "pack", "cli-snapshot", "replay-goldens", "golden-slice", "content"}:
        from . import build as build_commands

        return build_commands.handle(args)
    if args.command == "apply-plan":
        from . import ai as ai_commands
        return ai_commands.handle(args)
    if args.command == "undo-last-plan":
        from . import ai as ai_commands
        return ai_commands.handle(args)
    if args.command == "plan":
        from . import plan as plan_commands

        return plan_commands.handle(args)
    if args.command == "ai-generate-plan":
        from . import ai as ai_commands
        return ai_commands.handle(args)
    if args.command == "ai-bundle":
        from . import ai as ai_commands
        return ai_commands.handle(args)
    if args.command == "ai-history":
        from . import ai as ai_commands
        return ai_commands.handle(args)
    if args.command == "ai-export-context":
        from . import ai as ai_commands
        return ai_commands.handle(args)
    if args.command == "auto-wire-transitions":
        from . import world as world_commands

        return world_commands.handle(args)
    if args.command == "cli-smoke":
        from . import qa as qa_commands

        return qa_commands._handle_cli_smoke(args)
    if args.command in {"encounter-report", "drift-check"}:
        from . import reports as report_commands

        return report_commands.handle(args)
    # if args.command == "drift-check":
    #     return _handle_drift_check(args)
    if args.command == "edit-scene":
        from . import scene as scene_commands

        return scene_commands.handle(args)
    if args.command == "add-puzzle":
        return _handle_add_puzzle(args)
    if args.command == "export":
        from . import export as export_commands

        return export_commands.handle(args)
    # Handle content commands
    if hasattr(args, "func"):
        result = args.func(args)
        return int(result) if isinstance(result, int) else 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
