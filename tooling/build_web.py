from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
import tomllib

from engine.diagnostics import clear_diagnostics
from engine.diagnostics import diagnostics_to_json
from engine.diagnostics import error as diag_error
from engine.diagnostics import get_diagnostics


def _read_pygbag_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _extract_output_dir(config: dict) -> str | None:
    cfg = config.get("pygbag")
    if isinstance(cfg, dict):
        output = cfg.get("output")
        if isinstance(output, str) and output.strip():
            return output
    return None


def _build_pygbag_command(
    *,
    entrypoint: str,
    extra_args: list[str],
    disable_sound_format_error: bool,
) -> list[str]:
    cmd = [sys.executable, "-m", "pygbag", "--build"]
    if disable_sound_format_error:
        cmd.append("--disable-sound-format-error")
    cmd.extend(extra_args)
    cmd.append(entrypoint)
    return cmd


def _first_non_empty_line(text: str) -> str:
    for raw in str(text or "").splitlines():
        line = str(raw).strip()
        if line:
            return line
    return ""


def _emit_tooling_failure_diagnostic(
    *,
    entrypoint: str,
    cmd: list[str],
    returncode: int,
    failure_text: str,
) -> None:
    clear_diagnostics()
    first_line = _first_non_empty_line(failure_text)
    message = first_line or f"pygbag failed with code {int(returncode)}"
    diag_error(
        "WEB_BUILD_TOOLING_FAILED",
        message,
        "tooling.build_web",
        location=str(entrypoint),
        context={
            "command": " ".join(str(part) for part in cmd),
            "returncode": int(returncode),
        },
        hint="build-web enables --disable-sound-format-error by default; pass it explicitly or fix remaining build errors.",
    )
    sys.stderr.write(diagnostics_to_json(get_diagnostics()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a WebAssembly bundle via pygbag.")
    parser.add_argument("entrypoint", nargs="?", default="web_main.py", help="Entry point script.")
    parser.add_argument(
        "--disable-sound-format-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass pygbag --disable-sound-format-error to ignore unsupported audio format hard-failures (default: enabled).",
    )
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Extra argument passed through to pygbag (repeatable).",
    )
    args = parser.parse_args(argv)

    pygbag_toml = Path("pygbag.toml")
    config = _read_pygbag_toml(pygbag_toml)
    output_dir = _extract_output_dir(config)
    if pygbag_toml.exists():
        print(f"[Mesh][Web] Using {pygbag_toml.as_posix()}")
    if output_dir:
        print(f"[Mesh][Web] Output directory: {output_dir}")

    cmd = _build_pygbag_command(
        entrypoint=str(args.entrypoint),
        extra_args=[str(item) for item in args.extra_arg],
        disable_sound_format_error=bool(args.disable_sound_format_error),
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if int(result.returncode) != 0:
        _emit_tooling_failure_diagnostic(
            entrypoint=str(args.entrypoint),
            cmd=cmd,
            returncode=int(result.returncode),
            failure_text=str(result.stderr or result.stdout or ""),
        )
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
