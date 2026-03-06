"""
CLI command: ``mesh_cli demo run``

Orchestrates a full demo pipeline end-to-end in a deterministic,
fail-fast sequence:

1. release check
2. new-game
3. campaign replay-check
4. debug export (deterministic)
5. export build
6. demo report (JSON + text)
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable

from engine.persistence_io import (
    dumps_json_deterministic,
    write_json_atomic,
    write_text_atomic,
)
from engine.provenance import (
    format_provenance_text,
    get_provenance,
    provenance_to_dict,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SEED = 42
DEFAULT_CAMPAIGN = "mini_campaign_01"

# Type alias for step runners.
# (out_dir, seed, campaign) -> (exit_code, outputs_dict)
StepFn = Callable[[Path, int, str], "tuple[int, dict[str, Any]]"]

# ---------------------------------------------------------------------------
# Individual step runners (each is independently mockable)
# ---------------------------------------------------------------------------


def _step_release_check(
    out_dir: Path, seed: int, campaign: str,
) -> tuple[int, dict[str, Any]]:
    from mesh_cli.release import _handle_check

    release_dir = out_dir / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    args = argparse.Namespace(
        command="release",
        release_command="check",
        repo_root=".",
        artifacts=str(release_dir),
        report=None,
        summary=None,
        deterministic=True,
        quiet=True,
    )
    code = _handle_check(args)
    return code, {"dir": "release/"}


def _step_new_game(
    out_dir: Path, seed: int, campaign: str,
) -> tuple[int, dict[str, Any]]:
    from mesh_cli.new_game import build_new_game_payload

    out_path = out_dir / "new_game.json"
    payload = build_new_game_payload(campaign=campaign, seed=seed)
    write_json_atomic(out_path, payload)
    return 0, {"path": "new_game.json"}


def _step_campaign_replay_check(
    out_dir: Path, seed: int, campaign: str,
) -> tuple[int, dict[str, Any]]:
    from mesh_cli.campaign import _handle_replay_check

    replay_dir = out_dir / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    args = argparse.Namespace(
        command="campaign",
        campaign_command="replay-check",
        campaign=campaign,
        out_dir=str(replay_dir),
        json=False,
    )
    code = _handle_replay_check(args)
    return code, {"dir": "replay/"}


def _step_debug_export(
    out_dir: Path, seed: int, campaign: str,
) -> tuple[int, dict[str, Any]]:
    from mesh_cli.debug import _handle_export

    debug_dir = out_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    out_path = debug_dir / "debug_bundle.json"
    args = argparse.Namespace(
        command="debug",
        debug_command="export",
        out=str(out_path),
        deterministic=True,
    )
    code = _handle_export(args)
    return code, {"path": "debug/debug_bundle.json"}


def _step_export_build(
    out_dir: Path, seed: int, campaign: str,
) -> tuple[int, dict[str, Any]]:
    from mesh_cli.export import _handle_export_build

    bundle_dir = out_dir / "bundle"
    args = argparse.Namespace(
        command="export",
        export_command="build",
        repo_root=".",
        out=str(bundle_dir),
        include_unused=False,
        allow_missing=False,
        deterministic=True,
    )
    code = _handle_export_build(args)
    return code, {"dir": "bundle/"}


# Ordered pipeline definition.
# Each entry is (step_name, runner_function).
# Tests monkeypatch the runner functions to control execution.
PIPELINE: list[tuple[str, StepFn]] = [
    ("release-check", _step_release_check),
    ("new-game", _step_new_game),
    ("campaign-replay-check", _step_campaign_replay_check),
    ("debug-export", _step_debug_export),
    ("export-build", _step_export_build),
]

# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

_REPORT_SCHEMA_VERSION = 1


def _file_size(path: Path) -> int | None:
    """Return file size in bytes, or *None* if it doesn't exist."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def _collect_file_sizes(out_dir: Path) -> dict[str, int]:
    """Walk ``out_dir`` and return ``{relative_path: size}`` for key files."""
    sizes: dict[str, int] = {}
    if not out_dir.is_dir():
        return sizes
    for p in sorted(out_dir.rglob("*.json")):
        rel = p.relative_to(out_dir).as_posix()
        sizes[rel] = p.stat().st_size
    return sizes


def _build_report(
    *,
    seed: int,
    campaign: str,
    out_dir_arg: str,
    steps: list[dict[str, Any]],
    file_sizes: dict[str, int],
    ok: bool,
    failed_step: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "seed": seed,
        "campaign": campaign,
        "out_dir": out_dir_arg,
        "steps": steps,
        "file_sizes": file_sizes,
        "ok": ok,
        "failed_step": failed_step,
        # Demo reports are expected to be byte-stable for the same seed + inputs.
        "provenance": provenance_to_dict(get_provenance(deterministic=True)),
    }


def _format_report_text(report: dict[str, Any]) -> str:
    lines = [
        "Mesh Demo Run",
        f"Campaign: {report['campaign']}",
        f"Seed: {report['seed']}",
        f"Output: {report['out_dir']}",
    ]
    prov = report.get("provenance")
    if prov:
        from engine.provenance import Provenance, format_provenance_text

        p = Provenance(**prov) if isinstance(prov, dict) else None
        if p:
            lines.append("")
            lines.append(format_provenance_text(p))
    lines += [
        "",
        "Steps:",
    ]
    for step in report.get("steps", []):
        tag = "OK" if step.get("ok") else "FAIL"
        name = step.get("name", "?")
        code = step.get("exit_code", "?")
        lines.append(f"  {name}: {tag} (exit={code})")
    lines.append("")

    if report.get("ok"):
        lines.append("Result: OK")
    else:
        lines.append(f"Result: FAILED at {report.get('failed_step', '?')}")
    lines.append("")

    fs = report.get("file_sizes", {})
    if fs:
        lines.append("Key files:")
        for path in sorted(fs):
            lines.append(f"  {path}  ({fs[path]:,} bytes)")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_demo(
    *,
    out_dir: Path,
    seed: int = DEFAULT_SEED,
    campaign: str = DEFAULT_CAMPAIGN,
    quiet: bool = False,
    pipeline: list[tuple[str, StepFn]] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Execute the demo pipeline and return ``(exit_code, report_dict)``.

    This is the main programmatic entry-point — the CLI ``handle()`` function
    delegates here.

    Parameters
    ----------
    out_dir:
        Root directory for all outputs.
    seed:
        RNG seed passed to new-game.
    campaign:
        Campaign identifier.
    quiet:
        When *True*, stdout from sub-steps is suppressed.
    pipeline:
        Override the step list (for testing).
    """
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    step_list = pipeline if pipeline is not None else PIPELINE

    step_records: list[dict[str, Any]] = []
    failed_step: str | None = None

    for name, runner in step_list:
        record: dict[str, Any] = {
            "name": name,
            "ok": False,
            "exit_code": 1,
            "outputs": {},
            "error": None,
        }
        try:
            if quiet:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code, outputs = runner(out_dir, seed, campaign)
            else:
                code, outputs = runner(out_dir, seed, campaign)
            record["exit_code"] = int(code)
            record["ok"] = code == 0
            record["outputs"] = outputs
        except Exception as exc:  # noqa: BLE001
            record["exit_code"] = 1
            record["error"] = f"{type(exc).__name__}: {exc}"

        step_records.append(record)
        if not record["ok"]:
            failed_step = name
            break

    all_ok = failed_step is None
    file_sizes = _collect_file_sizes(out_dir)

    report = _build_report(
        seed=seed,
        campaign=campaign,
        out_dir_arg=out_dir.as_posix(),
        steps=step_records,
        file_sizes=file_sizes,
        ok=all_ok,
        failed_step=failed_step,
    )

    # Write report files
    report_json_path = out_dir / "demo_report.json"
    report_txt_path = out_dir / "demo_report.txt"
    write_json_atomic(report_json_path, report)
    write_text_atomic(report_txt_path, _format_report_text(report))

    return 0 if all_ok else 1, report


# ---------------------------------------------------------------------------
# CLI entry-points
# ---------------------------------------------------------------------------


def register_subcommand(demo_subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``demo pipeline`` subcommand on an existing demo parser."""
    run_parser = demo_subparsers.add_parser(
        "pipeline",
        help="Run the full demo pipeline (release, new-game, replay, export).",
        description=(
            "Orchestrates release check, new-game, campaign replay-check, "
            "debug export, and export build in one fail-fast sequence."
        ),
    )
    run_parser.add_argument(
        "--out-dir",
        required=True,
        help="Root directory for all output artifacts.",
    )
    run_parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"RNG seed (default: {DEFAULT_SEED}).",
    )
    run_parser.add_argument(
        "--campaign",
        default=DEFAULT_CAMPAIGN,
        help=f"Campaign identifier (default: {DEFAULT_CAMPAIGN}).",
    )
    run_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress normal stdout (report files are still written).",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        dest="print_json",
        help="Print demo_report.json to stdout deterministically.",
    )
    run_parser.add_argument(
        "--no-fail",
        action="store_true",
        dest="no_fail",
        help="Exit 0 even if a step fails (report still records the failure).",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle the ``demo pipeline`` subcommand."""
    return _handle_pipeline(args)


def _handle_pipeline(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    seed: int = args.seed
    campaign: str = args.campaign
    quiet: bool = args.quiet
    print_json: bool = args.print_json
    no_fail: bool = args.no_fail

    exit_code, report = run_demo(
        out_dir=out_dir,
        seed=seed,
        campaign=campaign,
        quiet=quiet,
    )

    if print_json:
        sys.stdout.write(dumps_json_deterministic(report))

    if report["ok"]:
        if not quiet:
            print("[Mesh][Demo] OK")
    else:
        step = report.get("failed_step", "?")
        report_path = (out_dir.resolve() / "demo_report.json").as_posix()
        if not quiet:
            print(f"[Mesh][Demo] FAILED at '{step}' — see {report_path}")

    if no_fail:
        return 0
    return exit_code
