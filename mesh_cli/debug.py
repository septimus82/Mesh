"""Debug bundle commands for Mesh CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.config import load_config
from engine.logging_tools import suppress_stdout
from engine.services import build_replay_service


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

GameWindow = None


def get_game_window():
    """Patchable seam for importing the real GameWindow only when needed."""
    window_cls = GameWindow
    if window_cls is None:
        from engine.game import GameWindow as window_cls
    return window_cls


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register debug commands."""
    debug_parser = subparsers.add_parser(
        "debug",
        help="Debug utilities",
        description="Debug bundle export and diagnostics",
    )
    debug_subparsers = debug_parser.add_subparsers(dest="debug_command", help="Debug subcommand")

    export_parser = debug_subparsers.add_parser(
        "export",
        help="Export debug bundle snapshot",
        description="Capture a debug bundle snapshot (deterministic optional)",
    )
    export_parser.add_argument(
        "--out",
        help="Output JSON path (defaults to artifacts/debug_bundle.json)",
    )
    export_parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Strip timestamps for deterministic diffs",
    )

    diff_parser = debug_subparsers.add_parser(
        "diff",
        help="Diff two debug bundle snapshots",
        description="Compare debug bundle JSON outputs",
    )
    diff_parser.add_argument("--a", required=True, help="Path to bundle A JSON")
    diff_parser.add_argument("--b", required=True, help="Path to bundle B JSON")
    diff_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (text or json)",
    )
    diff_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON diff instead of text",
    )
    diff_parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 even when differences are found",
    )
    diff_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress normal output (exit code still indicates diff unless --no-fail)",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle debug commands."""
    debug_cmd = getattr(args, "debug_command", None)
    if debug_cmd == "export":
        return _handle_export(args)
    if debug_cmd == "diff":
        return _handle_diff(args)
    print("[Mesh][CLI] Error: missing debug subcommand")
    return 2


def _handle_export(args: argparse.Namespace) -> int:
    """Export debug bundle snapshot."""
    from engine.repo_root import get_repo_root  # noqa: PLC0415

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
        repo_root = get_repo_root()
    except Exception:
        repo_root = Path.cwd()

    out_raw = str(getattr(args, "out", "") or "")
    if out_raw:
        out_path = Path(out_raw)
        if not out_path.is_absolute():
            out_path = repo_root / out_path
    else:
        out_path = repo_root / "artifacts" / "debug_bundle.json"

    deterministic = bool(getattr(args, "deterministic", False))
    replay_service = build_replay_service()

    try:
        with suppress_stdout():
            window.load_scene(config.start_scene)
        replay_service.export_debug_bundle(
            window=window,
            out_path=out_path,
            deterministic=deterministic,
        )
        print(f"[Mesh][Debug] wrote bundle to {out_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][Debug] export failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        try:
            window.close()
        except Exception:
            _log_swallow("DEBU-001", "mesh_cli/debug.py pass-only blanket swallow")
            pass


def _handle_diff(args: argparse.Namespace) -> int:
    """Diff two debug bundle snapshots."""
    from engine.persistence_io import dumps_json_deterministic, read_json  # noqa: PLC0415
    from engine.editor.debug_bundle_diff_model import (  # noqa: PLC0415
        diff_debug_bundles,
        format_debug_bundle_diff_text,
    )

    path_a = Path(str(getattr(args, "a", "") or ""))
    path_b = Path(str(getattr(args, "b", "") or ""))
    if not path_a.exists():
        print(f"[Mesh][Debug] diff failed: missing --a {path_a}")
        return 2
    if not path_b.exists():
        print(f"[Mesh][Debug] diff failed: missing --b {path_b}")
        return 2

    payload_a = read_json(path_a)
    payload_b = read_json(path_b)
    diff = diff_debug_bundles(payload_a, payload_b)

    output_format = str(getattr(args, "format", "text") or "text")
    if getattr(args, "json", False) and output_format == "text":
        output_format = "json"

    quiet = bool(getattr(args, "quiet", False))
    if not quiet:
        if output_format == "json":
            text = dumps_json_deterministic(diff.to_dict(), indent=2, sort_keys=True, trailing_newline=True)
            print(text, end="")
        else:
            print(format_debug_bundle_diff_text(diff))

    if getattr(args, "no_fail", False):
        return 0
    return 0 if diff.changed is False else 1
