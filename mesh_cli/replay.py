"""Replay & Trace commands for Mesh Engine."""

import argparse
import json
import logging
import sys
from pathlib import Path

from engine.logging_tools import suppress_stdout
from engine.persistence_io import dumps_json_deterministic, write_json_atomic
from engine.swallowed_exceptions import _log_swallow
from engine.tooling import replay_script, replay_suite, trace_command
from engine.tooling.replay_hash import hash_payload

def register(subparsers: argparse._SubParsersAction) -> None:
    # Replay script (deterministic regression runner)
    replay_parser = subparsers.add_parser(
        "replay-script",
        help="Run a deterministic replay script",
        description="Run a deterministic replay script",
    )
    replay_parser.add_argument("path", help="Path to replay script JSON")
    replay_parser.add_argument("--out", help="Optional path to write final state JSON")

    # Replay suite (deterministic batch runner)
    replay_suite_parser = subparsers.add_parser(
        "replay-suite",
        help="Run all deterministic replay scripts in a folder and print a summary",
        description="Run all deterministic replay scripts in a folder and print a summary",
    )
    replay_suite_parser.add_argument("folder", help="Folder containing replay script JSON files")
    replay_suite_parser.add_argument("--out", help="Optional path to write summary JSON")

    # Trace
    trace_parser = subparsers.add_parser(
        "trace",
        help="Record or replay traces",
        description="Record or replay traces",
    )
    trace_parser.add_argument("--record", help="Record to file")
    trace_parser.add_argument("--replay", help="Replay from file")
    trace_parser.add_argument("--world", help="World file")
    trace_parser.add_argument("--overlay", action="store_true", help="Show overlay")
    trace_parser.add_argument("--assert-file", help="Assertions file")

    # Replay hash (deterministic dump-state hash)
    replay_hash_parser = subparsers.add_parser(
        "replay-hash",
        help="Run a deterministic replay script and write a hash report",
        description="Run a deterministic replay script and write a hash report",
    )
    replay_hash_parser.add_argument("--replay", required=True, help="Path to replay script JSON")
    replay_hash_parser.add_argument("--frames", type=int, default=300, help="Frame count metadata for the report")
    replay_hash_parser.add_argument("--warmup", type=int, default=0, help="Warmup frame metadata for the report")
    replay_hash_parser.add_argument("--float-round", type=int, default=6, help="Round floats to N decimals")
    replay_hash_parser.add_argument("--out", required=True, help="Path to write hash JSON")
    replay_hash_parser.add_argument("--expect", help="Expected hash JSON or text file")


def handle(args: argparse.Namespace) -> int:
    if args.command == "replay-script":
        return _handle_replay_script(args)
    if args.command == "replay-suite":
        return _handle_replay_suite(args)
    if args.command == "trace":
        return _handle_trace(args)
    if args.command == "replay-hash":
        return _handle_replay_hash(args)
    return 1


def _handle_replay_script(args: argparse.Namespace) -> int:
    try:
        script_path = Path(args.path)
        with suppress_stdout():
            script = replay_script.load_replay_script(script_path)
            payload = replay_script.run_replay_script(script, script_path=script_path)

        out_path = getattr(args, "out", None)
        if out_path:
            with suppress_stdout():
                write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)

        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 0
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("RPLY-001", "replay_script failed", once=True)
        payload = {"ok": False, "code": 1, "error": "replay_script.failed"}
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 1


def _handle_replay_suite(args: argparse.Namespace) -> int:
    try:
        with suppress_stdout():
            replay_suite_summary = replay_suite.run_replay_suite(str(args.folder))
        out_path = getattr(args, "out", None)
        if out_path:
            with suppress_stdout():
                write_json_atomic(
                    Path(out_path), replay_suite_summary, indent=2, sort_keys=True, trailing_newline=True
                )

        sys.stdout.write(
            dumps_json_deterministic(replay_suite_summary, indent=2, sort_keys=True, trailing_newline=True)
        )
        failed = replay_suite_summary.get("failed", 0) if isinstance(replay_suite_summary, dict) else 1
        try:
            failed_int = int(failed)
        except (TypeError, ValueError):
            failed_int = 1
        return 0 if failed_int == 0 else 1
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("RPLY-002", "replay_suite failed", once=True)
        payload = {"ok": False, "code": 1, "error": "replay_suite.failed"}
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 1


def _handle_trace(args: argparse.Namespace) -> int:
    return trace_command.handle_trace(args)


def _load_expected_hash(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError("Expected hash file is empty")

    if raw.startswith("{") or raw.startswith("[") or raw.startswith('"'):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Expected hash JSON invalid: {exc}") from exc
        if isinstance(payload, dict):
            value = payload.get("hash")
        else:
            value = payload
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Expected hash JSON missing 'hash' string")
        return value.strip().lower()

    return raw.strip().lower()


def _handle_replay_hash(args: argparse.Namespace) -> int:
    replay_path = Path(args.replay)
    if not replay_path.exists():
        print(f"[Mesh][ReplayHash] ERROR: replay not found: {replay_path}")
        return 1

    try:
        decimals = int(args.float_round)
    except (TypeError, ValueError):
        print("[Mesh][ReplayHash] ERROR: --float-round must be an integer")
        return 1
    if decimals < 0:
        print("[Mesh][ReplayHash] ERROR: --float-round must be >= 0")
        return 1

    try:
        frames = int(args.frames)
    except (TypeError, ValueError):
        print("[Mesh][ReplayHash] ERROR: --frames must be an integer")
        return 1
    try:
        warmup = int(args.warmup)
    except (TypeError, ValueError):
        print("[Mesh][ReplayHash] ERROR: --warmup must be an integer")
        return 1

    try:
        script = replay_script.load_replay_script(replay_path)
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("RPLY-003", "load_replay_script failed", once=True)
        print(f"[Mesh][ReplayHash] ERROR: failed to load replay: {exc}")
        return 1

    try:
        with suppress_stdout():
            payload = replay_script.run_replay_script(script, script_path=replay_path)
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("RPLY-004", "run_replay_script failed", once=True)
        print(f"[Mesh][ReplayHash] ERROR: replay failed: {exc}")
        return 1

    try:
        digest = hash_payload(payload, decimals=decimals)
    except Exception as exc:  # noqa: BLE001  # REASON: cli fallback isolation
        _log_swallow("RPLY-005", "hash_payload failed", once=True)
        print(f"[Mesh][ReplayHash] ERROR: hash failed: {exc}")
        return 1

    engine_sha = None
    try:
        from engine.tooling.perf_command import _get_engine_git_sha

        engine_sha = _get_engine_git_sha()
    except Exception as exc:
        _log_swallow("RPLY-006", "_get_engine_git_sha failed", once=True)
        engine_sha = None

    report = {
        "schema_version": 1,
        "replay": replay_path.as_posix(),
        "frames": frames,
        "warmup": warmup,
        "hash": digest,
        "engine_git_sha": engine_sha,
        "notes": {"float_round": decimals},
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out_path, report, indent=2, sort_keys=True, trailing_newline=True)

    expect_path = str(getattr(args, "expect", "") or "").strip()
    if expect_path:
        try:
            expected_hash = _load_expected_hash(Path(expect_path))
        except (OSError, ValueError) as exc:  # REASON: cli fallback isolation
            _log_swallow("RPLY-007", "_load_expected_hash failed", once=True)
            print(f"[Mesh][ReplayHash] ERROR: {exc}")
            return 1
        if expected_hash != digest:
            print(
                "[Mesh][ReplayHash] ERROR: hash mismatch "
                f"(expected={expected_hash} actual={digest})"
            )
            return 2

    print(f"[Mesh][ReplayHash] OK: {digest}")
    return 0
