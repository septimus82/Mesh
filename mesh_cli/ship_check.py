from __future__ import annotations

import argparse
import contextlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .shipping_policy import iter_ship_check_artifact_specs

_SECTION_ORDER: tuple[str, ...] = ("verify", "package", "web", "perf")


@dataclass(frozen=True, slots=True)
class ShipArtifactStatus:
    name: str
    path: str
    present: bool
    required: bool
    section: str


@dataclass(frozen=True, slots=True)
class ShipCheckSummary:
    ok: bool
    skipped_sections: tuple[str, ...]
    artifacts: tuple[ShipArtifactStatus, ...]
    web_smoke_artifact_path: str
    web_smoke_codes: tuple[str, ...]
    optional_runtime_smoke_path: str
    optional_runtime_smoke_present: bool
    lines: tuple[str, ...]


def _normalize_display_root(root: str) -> str:
    text = str(root or "").replace("\\", "/").strip()
    if not text:
        return "artifacts"
    return text.rstrip("/")


def _display_path(root_display: str, relpath: str) -> str:
    base = _normalize_display_root(root_display)
    rel = relpath.replace("\\", "/").strip().lstrip("/")
    return f"{base}/{rel}" if rel else base


def _artifact_spec_rows() -> tuple[tuple[str, str, bool, str], ...]:
    return iter_ship_check_artifact_specs()


def _load_web_smoke_codes(artifacts_root: Path) -> tuple[str, ...]:
    path = artifacts_root / "web_smoke.json"
    if not path.is_file():
        return tuple()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return tuple()
    if not isinstance(payload, dict):
        return tuple()
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, list):
        return tuple()
    codes: set[str] = set()
    for row in diagnostics:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code", "") or "").strip()
        if code:
            codes.add(code)
    return tuple(sorted(codes))


def build_ship_check_summary(
    *,
    artifacts_root: Path,
    artifacts_display_root: str,
    skip_verify: bool,
    skip_package: bool,
    skip_web: bool,
    skip_perf: bool,
    gate_ok: bool,
) -> ShipCheckSummary:
    skipped_map = {
        "verify": bool(skip_verify),
        "package": bool(skip_package),
        "web": bool(skip_web),
        "perf": bool(skip_perf),
    }
    skipped_sections = tuple(section for section in _SECTION_ORDER if skipped_map[section])
    smoke_expected = (not bool(skip_verify)) or (not bool(skip_package))

    artifact_rows: list[ShipArtifactStatus] = []
    for name, relpath, required, section in _artifact_spec_rows():
        abs_path = artifacts_root / relpath
        required_now = bool(required and not skipped_map[section])
        if name == "runtime_diagnostics_snapshot":
            required_now = bool(smoke_expected)
        artifact_rows.append(
            ShipArtifactStatus(
                name=name,
                path=_display_path(artifacts_display_root, relpath),
                present=abs_path.is_file(),
                required=required_now,
                section=section,
            )
        )

    optional_runtime_smoke_rel = "runtime_smoke.json"
    optional_runtime_smoke_path = _display_path(artifacts_display_root, optional_runtime_smoke_rel)
    optional_runtime_smoke_present = (artifacts_root / optional_runtime_smoke_rel).is_file()
    web_smoke_artifact_rel = "web_smoke.json"
    web_smoke_artifact_path = _display_path(artifacts_display_root, web_smoke_artifact_rel)
    web_smoke_codes = _load_web_smoke_codes(artifacts_root)

    required_artifacts_ok = all(row.present for row in artifact_rows if row.required)
    missing_required = [row for row in artifact_rows if row.required and not row.present]
    overall_ok = bool(gate_ok and required_artifacts_ok)

    lines: list[str] = ["Shipping Readiness Summary"]
    for section in skipped_sections:
        lines.append(f"SECTION: {section} SKIPPED")
    lines.append(f"SHIP_CHECK_OK: {'true' if overall_ok else 'false'}")
    for row in artifact_rows:
        lines.append(f"ARTIFACT: {row.name} {row.path} present:{'true' if row.present else 'false'}")
    lines.append(f"WEB_SMOKE_ARTIFACT: {web_smoke_artifact_path}")
    lines.append(f"WEB_SMOKE_CODES: {','.join(web_smoke_codes) if web_smoke_codes else '-'}")
    for row in missing_required:
        lines.append(f"ERROR: missing_required_artifact {row.name} {row.path}")
    lines.append(
        "OPTIONAL_RUNTIME_SMOKE: "
        f"{optional_runtime_smoke_path} present:{'true' if optional_runtime_smoke_present else 'false'}"
    )

    return ShipCheckSummary(
        ok=overall_ok,
        skipped_sections=skipped_sections,
        artifacts=tuple(artifact_rows),
        web_smoke_artifact_path=web_smoke_artifact_path,
        web_smoke_codes=web_smoke_codes,
        optional_runtime_smoke_path=optional_runtime_smoke_path,
        optional_runtime_smoke_present=optional_runtime_smoke_present,
        lines=tuple(lines),
    )


def _run_verify_all_ci_bundle(artifacts_arg: str, *, skip_web: bool) -> tuple[int, dict[str, Any]]:
    from . import verify as verify_commands

    verify_args = argparse.Namespace(
        command="verify-all",
        out_dir=None,
        artifacts=artifacts_arg,
        no_index=False,
        report=False,
        report_json=False,
        report_json_artifact=False,
        artifact_index=False,
        ci_bundle=True,
        release_notes_artifact=False,
        skip_web_smoke=bool(skip_web),
        pytest_args=[],
    )
    payload, code = verify_commands._build_verify_all_payload(verify_args)
    payload_dict = payload if isinstance(payload, dict) else {}
    return int(code), payload_dict


def _verify_required_steps_ok(
    payload: dict[str, Any],
    *,
    skip_package: bool,
    skip_web: bool,
    skip_perf: bool,
) -> bool:
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return False

    ignored_failures = set()
    if skip_package:
        ignored_failures.add("player-package-gate")
    if skip_web:
        ignored_failures.add("web-smoke")
    if skip_perf:
        ignored_failures.add("perf-baseline-compare")

    for raw_row in steps:
        if not isinstance(raw_row, dict):
            continue
        if bool(raw_row.get("ok")):
            continue
        error = str(raw_row.get("error", "") or "")
        if error == "skipped: previous step failed":
            continue
        name = str(raw_row.get("name", "") or "")
        if name in ignored_failures:
            continue
        return False
    return True


def _print_lines(lines: tuple[str, ...] | list[str]) -> None:
    for line in lines:
        print(line)


def _call_quietly(func, /, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return func(*args, **kwargs)


def _run_web_gate(*, repo_root: Path, artifacts_path: Path, quiet: bool) -> int:
    import subprocess
    import sys

    build_cmd = [
        sys.executable,
        "-m",
        "mesh_cli",
        "build-web",
        "--out",
        str(artifacts_path / "web_build"),
    ]
    if quiet:
        build_result = _call_quietly(subprocess.run, build_cmd, capture_output=True, text=True, cwd=str(repo_root))
    else:
        build_result = subprocess.run(build_cmd, capture_output=True, text=True, cwd=str(repo_root))
    build_code = int(build_result.returncode)

    from .web_smoke import run_web_smoke

    web_smoke_path = artifacts_path / "web_smoke.json"
    if quiet:
        smoke_code = int(
            _call_quietly(
                run_web_smoke,
                build_dir=(artifacts_path / "web_build").as_posix(),
                artifact_path=web_smoke_path.as_posix(),
            )
        )
    else:
        smoke_code = int(
            run_web_smoke(
                build_dir=(artifacts_path / "web_build").as_posix(),
                artifact_path=web_smoke_path.as_posix(),
            )
        )

    if build_code != 0:
        return build_code
    return smoke_code


def _handle_ship_check(args: argparse.Namespace) -> int:
    from engine.repo_root import get_repo_root

    artifacts_arg = str(getattr(args, "artifacts", "") or "artifacts").strip() or "artifacts"
    quiet = bool(getattr(args, "quiet", False))
    skip_verify = bool(getattr(args, "skip_verify", False))
    skip_package = bool(getattr(args, "skip_package", False))
    skip_web = bool(getattr(args, "skip_web", False))
    skip_perf = bool(getattr(args, "skip_perf", False))
    continue_on_web_fail = bool(getattr(args, "continue_on_web_fail", False))

    artifacts_path = Path(artifacts_arg)
    if not artifacts_path.is_absolute():
        artifacts_path = (Path.cwd() / artifacts_path).resolve()
    repo_root = get_repo_root(start=Path.cwd(), strict=False)

    gate_ok = True

    if not skip_verify:
        if not quiet:
            print("[Mesh][ShipCheck] Running verify-all --ci-bundle")
        if quiet:
            verify_code, verify_payload = _call_quietly(_run_verify_all_ci_bundle, artifacts_arg, skip_web=skip_web)
        else:
            verify_code, verify_payload = _run_verify_all_ci_bundle(artifacts_arg, skip_web=skip_web)
        verify_ok = verify_code == 0
        if not verify_ok:
            verify_ok = _verify_required_steps_ok(
                verify_payload,
                skip_package=skip_package,
                skip_web=skip_web,
                skip_perf=skip_perf,
            )
        gate_ok = bool(gate_ok and verify_ok)
    elif not quiet:
        print("[Mesh][ShipCheck] Skipping verify-all")

    if not skip_package:
        if not quiet:
            print("[Mesh][ShipCheck] Running package-player --smoke")
        from .player_package import package_player_bundle

        package_out = artifacts_path / "player_pkg"
        diagnostics_artifact = artifacts_path / "runtime_diagnostics_snapshot.json"
        if quiet:
            package_code = int(
                _call_quietly(
                    package_player_bundle,
                    out_dir=package_out.as_posix(),
                    manifest_path=None,
                    smoke=True,
                    smoke_diagnostics_artifact=diagnostics_artifact.as_posix(),
                )
            )
        else:
            package_code = int(
                package_player_bundle(
                    out_dir=package_out.as_posix(),
                    manifest_path=None,
                    smoke=True,
                    smoke_diagnostics_artifact=diagnostics_artifact.as_posix(),
                )
            )
        gate_ok = bool(gate_ok and package_code == 0)
    elif not quiet:
        print("[Mesh][ShipCheck] Skipping package-player")

    should_run_standalone_web = bool(skip_verify and not skip_web)
    if should_run_standalone_web:
        if not quiet:
            print("[Mesh][ShipCheck] Running web-smoke")
        web_code = _run_web_gate(repo_root=Path(repo_root).resolve(), artifacts_path=artifacts_path, quiet=quiet)
        gate_ok = bool(gate_ok and web_code == 0)
        if web_code != 0 and not continue_on_web_fail and not quiet:
            print("[Mesh][ShipCheck] web-smoke failed")
    elif skip_web and not quiet:
        print("[Mesh][ShipCheck] Skipping web-smoke")
    elif not quiet:
        print("[Mesh][ShipCheck] Using verify-all web-smoke result")

    summary = build_ship_check_summary(
        artifacts_root=artifacts_path,
        artifacts_display_root=artifacts_arg,
        skip_verify=skip_verify,
        skip_package=skip_package,
        skip_web=skip_web,
        skip_perf=skip_perf,
        gate_ok=gate_ok,
    )
    _print_lines(summary.lines)
    return 0 if summary.ok else 1


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "ship-check",
        help="Run shipping readiness checks and print a deterministic artifact summary",
    )
    parser.add_argument(
        "--artifacts",
        default="artifacts",
        help="Artifacts directory used by verify/package/web gates (default: artifacts)",
    )
    parser.add_argument("--skip-package", action="store_true", help="Skip package-player --smoke step")
    parser.add_argument("--skip-web", action="store_true", help="Skip web-smoke step and web artifact requirement")
    parser.add_argument("--skip-perf", action="store_true", help="Skip perf artifact requirement checks")
    parser.add_argument("--skip-verify", action="store_true", help="Skip verify-all --ci-bundle step")
    parser.add_argument(
        "--continue-on-web-fail",
        action="store_true",
        help="Continue to summary even when web-smoke fails (still exits non-zero)",
    )
    parser.add_argument("--quiet", action="store_true", help="Print only the final summary block")
    parser.set_defaults(func=_handle_ship_check)


__all__ = [
    "ShipArtifactStatus",
    "ShipCheckSummary",
    "build_ship_check_summary",
    "register",
]
