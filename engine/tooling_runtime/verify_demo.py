from __future__ import annotations

import itertools
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional

from engine.logging_tools import get_logger


# Keep logger name stable (historically this lived in engine.tooling.verify_demo)
# so stderr messaging remains identical across the refactor.
_LOG = get_logger("engine.tooling.verify_demo")
_VERIFY_DEMO_FAILURE_SCHEMA_VERSION = 1
_VERIFY_DEMO_FAILURE_LINE_LIMIT = 40
_VERIFY_DEMO_RUN_COUNTER = itertools.count(1)
_VERIFY_DEMO_IGNORE_GLOBS: tuple[str, ...] = ("tests/temp_*",)
_MISSING_PATH_RE = re.compile(r"FileNotFoundError:.*['\"]([^'\"]+)['\"]")


def _log_swallow(tag: str, purpose: str) -> None:
    _LOG.debug(
        "SWALLOWED_EXCEPTION SWALLOW[%s] %s",
        tag,
        purpose,
        exc_info=True,
    )

# Curated, deterministic test list for fast dev verification.
# Keep this list stable and explicitly ordered to avoid nondeterministic discovery.
_CURATED_TEST_FILES: tuple[str, ...] = (
    # Golden slice contracts + picker/HUD + showcase intent
    "tests/test_golden_slice_content_invariants.py",
    "tests/test_golden_slice_boss_victory_ux_contract.py",
    "tests/test_golden_slice_demo_hud_strip.py",
    "tests/test_golden_slice_variant_picker_list_source.py",
    "tests/test_golden_slice_variant_picker_hardening.py",
    "tests/test_golden_slice_variant_e_occluder_showcase.py",
    "tests/test_golden_slice_variant_e_boss_reward_clarity.py",
    "tests/test_golden_slice_variants_contract.py",
    "tests/test_golden_slice_scaffold_command.py",
    "tests/test_golden_slice_pipeline_gate.py",
    "tests/test_golden_slice_lighting_showcase_intent.py",

    # Act 1 slice/stub tests
    "tests/test_act1_prologue_slice.py",
    "tests/test_act1_chapter1_slice.py",
    "tests/test_act1_chapter1_preset_exists.py",
    "tests/test_act1_chapter2_stub.py",
    "tests/test_act1_chapter2_slice.py",
    "tests/test_act1_chapter3_stub.py",
    "tests/test_act1_chapter3_slice.py",
    "tests/test_act1_chapter4_stub.py",
    "tests/test_act1_chapter4_slice.py",
    "tests/test_act1_chapter5_stub.py",

    # Preset stability / registry sanity
    "tests/test_presets_required_exist.py",
    "tests/test_presets_not_duplicated.py",
    "tests/test_preset_demo_master_exists.py",
    "tests/test_preset_act1_full_demo_exists.py",
    "tests/test_preset_golden_slice_demo_all_exists.py",
    "tests/test_preset_golden_slice_index_exists.py",
    "tests/test_preset_golden_slice_showcase_all_exists.py",
    "tests/test_preset_registry_schema.py",
)


def iter_missing_paths(paths: Iterable[str]) -> List[str]:
    missing: List[str] = []
    for p in paths:
        if not Path(p).exists():
            missing.append(p)
    return missing


def build_verify_demo_pytest_cmd() -> List[str]:
    # Exact argv ordering is intentionally curated and regression-tested.
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-W",
        "error",
        *[f"--ignore-glob={pattern}" for pattern in _VERIFY_DEMO_IGNORE_GLOBS],
        *_CURATED_TEST_FILES,
    ]


def _next_verify_demo_run_root(scratch_dir: Path | None) -> Path | None:
    if scratch_dir is None:
        return None
    scratch_root = Path(scratch_dir)
    run_id = f"pid{os.getpid()}-run{next(_VERIFY_DEMO_RUN_COUNTER):04d}"
    return scratch_root / run_id


def _build_verify_demo_pytest_isolation_args(run_root: Path | None) -> List[str]:
    if run_root is None:
        return []
    run_root.mkdir(parents=True, exist_ok=True)
    basetemp = run_root / "basetemp"
    cache_dir = run_root / "cache"
    return [
        "--basetemp",
        str(basetemp),
        "-o",
        f"cache_dir={cache_dir.as_posix()}",
    ]


def validate_pytest_passthrough_args(pytest_args: List[str]) -> Optional[str]:
    """Return an error message if passthrough args are disallowed, else None.

    Strict guard: disallow flags/args that change test selection.
    - Path args (anything not starting with '-') are disallowed.
    - '-k' / '--keyword' and '-m' / '--markers' are disallowed.
    """
    i = 0
    while i < len(pytest_args):
        token = pytest_args[i]

        # Disallow adding any extra positional args (paths / nodeids / plugins etc).
        if token and not token.startswith("-"):
            return (
                "Passthrough contains a positional argument (likely a path/nodeid), which could change what runs. "
                "Remove it to keep verify-demo deterministic."
            )

        # Disallow -k / -m (both separate and inline forms, and long forms).
        if token in {"-k", "--keyword", "-m", "--markers"}:
            return f"Passthrough flag '{token}' is not allowed because it can change test selection."

        if token.startswith("-k") and token != "-k":
            return "Passthrough flag '-k' is not allowed because it can change test selection."
        if token.startswith("-m") and token != "-m":
            return "Passthrough flag '-m' is not allowed because it can change test selection."
        if token.startswith("--keyword="):
            return "Passthrough flag '--keyword' is not allowed because it can change test selection."
        if token.startswith("--markers="):
            return "Passthrough flag '--markers' is not allowed because it can change test selection."

        i += 1

    return None


def _tail_lines(text: str, limit: int = 200) -> list[str]:
    lines = text.splitlines()
    if len(lines) <= limit:
        return lines
    return lines[-limit:]


def _head_lines(text: str, limit: int = _VERIFY_DEMO_FAILURE_LINE_LIMIT) -> list[str]:
    lines = text.splitlines()
    if len(lines) <= limit:
        return lines
    return lines[:limit]


def _write_failure_log(path: Path, stdout: str, stderr: str) -> None:
    payload = [
        "=== verify-demo stdout ===",
        stdout.rstrip(),
        "",
        "=== verify-demo stderr ===",
        stderr.rstrip(),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(payload), encoding="utf-8")


def _diagnostic_artifact_dir(*, log_path: Path | None, scratch_dir: Path | None) -> Path | None:
    if log_path is not None:
        return Path(log_path).parent
    if scratch_dir is None:
        return None
    scratch_root = Path(scratch_dir)
    if scratch_root.name == "verify_demo_pytest":
        return scratch_root.parent
    return scratch_root


def _write_failure_artifact(
    path: Path,
    *,
    exit_code: int,
    argv: list[str],
    cwd: Path,
    run_root: Path | None,
    basetemp: Path | None,
    cache_dir: Path | None,
    stdout: str,
    stderr: str,
) -> None:
    from engine.persistence_io import write_json_atomic

    missing_path = _extract_missing_path(stdout=stdout, stderr=stderr)
    payload: dict[str, Any] = {
        "schema_version": _VERIFY_DEMO_FAILURE_SCHEMA_VERSION,
        "exit_code": int(exit_code),
        "argv": list(argv),
        "cwd": str(cwd),
        "run_root": str(run_root) if run_root is not None else "",
        "basetemp": str(basetemp) if basetemp is not None else "",
        "cache_dir": str(cache_dir) if cache_dir is not None else "",
        "stdout_head": _head_lines(stdout),
        "stderr_head": _head_lines(stderr),
        "missing_path": missing_path,
    }
    write_json_atomic(
        path,
        payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )


def _extract_missing_path(*, stdout: str, stderr: str) -> str:
    for text in (stderr, stdout):
        for line in text.splitlines():
            if "FileNotFoundError" not in line:
                continue
            match = _MISSING_PATH_RE.search(line)
            if match is not None:
                return match.group(1)
    return ""


def run_verify_demo(
    pytest_args: Optional[List[str]] = None,
    *,
    capture_output: bool = False,
    quiet: bool = False,
    log_path: Path | None = None,
    scratch_dir: Path | None = None,
) -> int:
    pytest_args = pytest_args or []
    if pytest_args:
        err = validate_pytest_passthrough_args(pytest_args)
        if err:
            if not quiet:
                _LOG.error("Unsafe pytest passthrough args.")
                _LOG.error("%s", err)
                _LOG.error("Disallowed: -k/--keyword, -m/--markers, and any positional path args.")
            return 2

    missing = iter_missing_paths(_CURATED_TEST_FILES)
    if missing:
        if not quiet:
            _LOG.error("Missing expected test file(s):")
            for p in missing:
                _LOG.error("  - %s", p)
        return 2

    effective_scratch_dir = scratch_dir
    if effective_scratch_dir is None and log_path is not None:
        effective_scratch_dir = Path(log_path).parent / "verify_demo_pytest"
    run_root = _next_verify_demo_run_root(effective_scratch_dir)
    basetemp = run_root / "basetemp" if run_root is not None else None
    cache_dir = run_root / "cache" if run_root is not None else None
    cwd = Path.cwd()
    failure_artifact_dir = _diagnostic_artifact_dir(log_path=log_path, scratch_dir=effective_scratch_dir)
    failure_artifact_path = (
        failure_artifact_dir / "verify_demo_failure.json"
        if failure_artifact_dir is not None
        else None
    )

    cmd = build_verify_demo_pytest_cmd()
    cmd.extend(_build_verify_demo_pytest_isolation_args(run_root))
    if pytest_args:
        cmd.extend(pytest_args)
    if not quiet:
        _LOG.info("Running %d test modules...", len(_CURATED_TEST_FILES))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )

    if result.returncode == 0:
        if not quiet:
            _LOG.info("PASSED")
        return 0

    stdout = str(result.stdout or "")
    stderr = str(result.stderr or "")

    if failure_artifact_path is not None:
        try:
            _write_failure_artifact(
                failure_artifact_path,
                exit_code=int(result.returncode),
                argv=cmd,
                cwd=cwd,
                run_root=run_root,
                basetemp=basetemp,
                cache_dir=cache_dir,
                stdout=stdout,
                stderr=stderr,
            )
        except Exception as exc:  # noqa: BLE001  # REASON: verify-demo should preserve the original test failure while tolerating secondary artifact-write errors
            _log_swallow("VDEMO-001", "verify-demo failure artifact write fallback")
            _LOG.error("VDEMO-001 verify-demo failure artifact write error: %s", exc, exc_info=True)

    if log_path is not None:
        try:
            _write_failure_log(Path(log_path), stdout, stderr)
            if not quiet:
                _LOG.error("verify-demo failed; log written to %s", log_path)
        except Exception as exc:  # noqa: BLE001  # REASON: verify-demo should preserve the original test failure while tolerating secondary log-write errors
            _log_swallow("VDEMO-001", "verify-demo log write fallback")
            _LOG.error("VDEMO-001 verify-demo log write error: %s", exc, exc_info=True)
    elif not quiet and capture_output:
        if stderr:
            _LOG.error("verify-demo stderr (tail):")
            for line in _tail_lines(stderr):
                _LOG.error("%s", line)
        if stdout:
            _LOG.error("verify-demo stdout (tail):")
            for line in _tail_lines(stdout):
                _LOG.error("%s", line)

    _LOG.error(
        "VDEMO-001 verify-demo failed exit=%s argv=%s cwd=%s basetemp=%s cache_dir=%s failure_artifact=%s",
        result.returncode,
        cmd,
        cwd,
        basetemp,
        cache_dir,
        failure_artifact_path,
    )
    if not quiet:
        _LOG.error("FAILED (pytest exit=%s)", result.returncode)
    return result.returncode
