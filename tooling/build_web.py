from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from engine.diagnostics import clear_diagnostics, diagnostics_to_json, get_diagnostics
from engine.diagnostics import error as diag_error


def _read_pygbag_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _extract_output_dir(config: dict) -> str | None:
    cfg = config.get("pygbag")
    if isinstance(cfg, dict):
        output = cfg.get("output")
        if isinstance(output, str) and output.strip():
            return output
    return None


def _iter_stage_include_paths(*, repo_root: Path, entrypoint: str, config: dict) -> list[tuple[Path, Path]]:
    rows: list[tuple[Path, Path]] = []
    seen: set[str] = set()

    def _add(rel_path: str) -> None:
        normalized = str(rel_path or "").replace("\\", "/").strip().lstrip("./")
        if not normalized:
            return
        key = normalized.rstrip("/")
        if key in seen:
            return
        seen.add(key)
        source = repo_root / key
        if source.exists():
            rows.append((source, Path(key)))

    _add(entrypoint)
    _add("engine")
    _add("mesh_cli")
    _add("pygbag.toml")

    pygbag = config.get("pygbag") if isinstance(config, dict) else None
    includes = pygbag.get("include") if isinstance(pygbag, dict) else None
    if isinstance(includes, list):
        for item in includes:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text:
                continue
            if text.endswith("/**"):
                _add(text[:-3])
            else:
                _add(text)

    return sorted(rows, key=lambda row: row[1].as_posix())


def _copy_stage_tree(*, repo_root: Path, stage_root: Path, entrypoint: str, config: dict) -> None:
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)

    for source, relative_target in _iter_stage_include_paths(repo_root=repo_root, entrypoint=entrypoint, config=config):
        target = stage_root / relative_target
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _copy_built_output(*, source_dir: Path, target_dir: Path) -> None:
    if not source_dir.exists():
        raise FileNotFoundError(f"expected staged web output not found: {source_dir.as_posix()}")
    last_error: OSError | None = None
    for _attempt in range(5):
        try:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, target_dir)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)
    if last_error is not None:
        raise last_error


def _staged_output_dir(*, stage_root: Path, config: dict) -> Path:
    stage_output_dir = _extract_output_dir(config) or "build/web"
    return stage_root / stage_output_dir


def _staged_output_passes_web_smoke(stage_output_dir: Path) -> bool:
    try:
        from mesh_cli.web_smoke import run_web_smoke
    except ImportError:
        return False
    for _attempt in range(4):
        if int(run_web_smoke(build_dir=stage_output_dir.as_posix(), artifact_path=None)) == 0:
            return True
        time.sleep(0.5)
    return False


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
        "--out-dir",
        help="Optional destination directory for copied web output (defaults to pygbag.toml output or build/web).",
    )
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

    repo_root = Path.cwd().resolve()
    pygbag_toml = repo_root / "pygbag.toml"
    config = _read_pygbag_toml(pygbag_toml)
    output_dir = _extract_output_dir(config)
    if pygbag_toml.exists():
        print(f"[Mesh][Web] Using {pygbag_toml.as_posix()}")
    if output_dir:
        print(f"[Mesh][Web] Output directory: {output_dir}")

    entrypoint = str(args.entrypoint)
    stage_root = repo_root / "artifacts" / "_web_build_stage"
    try:
        _copy_stage_tree(repo_root=repo_root, stage_root=stage_root, entrypoint=entrypoint, config=config)
    except OSError as exc:
        _emit_tooling_failure_diagnostic(
            entrypoint=entrypoint,
            cmd=["stage-web-build"],
            returncode=1,
            failure_text=str(exc),
        )
        return 1

    cmd = _build_pygbag_command(
        entrypoint=entrypoint,
        extra_args=[str(item) for item in args.extra_arg],
        disable_sound_format_error=bool(args.disable_sound_format_error),
    )
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(stage_root))
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    staged_output_dir = _staged_output_dir(stage_root=stage_root, config=config)
    if int(result.returncode) != 0:
        smoke_ok = _staged_output_passes_web_smoke(staged_output_dir)
        if not smoke_ok:
            _emit_tooling_failure_diagnostic(
                entrypoint=str(args.entrypoint),
                cmd=cmd,
                returncode=int(result.returncode),
                failure_text=str(result.stderr or result.stdout or ""),
            )
            return int(result.returncode)
        print(f"[Mesh][Web] pygbag returned {int(result.returncode)} but staged output passed web smoke; continuing")

    try:
        target_dir_raw = str(getattr(args, "out_dir", "") or "").strip()
        target_dir = Path(target_dir_raw) if target_dir_raw else repo_root / (output_dir or "build/web")
        if not target_dir.is_absolute():
            target_dir = repo_root / target_dir
        _copy_built_output(
            source_dir=staged_output_dir,
            target_dir=target_dir,
        )
    except OSError as exc:
        _emit_tooling_failure_diagnostic(
            entrypoint=entrypoint,
            cmd=cmd,
            returncode=1,
            failure_text=str(exc),
        )
        return 1

    if stage_root.exists():
        try:
            shutil.rmtree(stage_root)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
