from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from engine.logging_tools import get_logger


# Keep logger name stable (historically this lived in engine.tooling.verify_demo)
# so stderr messaging remains identical across the refactor.
_LOG = get_logger("engine.tooling.verify_demo")

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
        *_CURATED_TEST_FILES,
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


def run_verify_demo(
    pytest_args: Optional[List[str]] = None,
    *,
    capture_output: bool = False,
    quiet: bool = False,
    log_path: Path | None = None,
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

    cmd = build_verify_demo_pytest_cmd()
    if pytest_args:
        cmd.extend(pytest_args)
    if not quiet:
        _LOG.info("Running %d test modules...", len(_CURATED_TEST_FILES))
    result = subprocess.run(cmd, capture_output=capture_output)

    if result.returncode == 0:
        if not quiet:
            _LOG.info("PASSED")
        return 0

    stdout = ""
    stderr = ""
    if capture_output:
        stdout = (result.stdout or b"").decode("utf-8", errors="replace") if isinstance(result.stdout, (bytes, bytearray)) else str(result.stdout or "")
        stderr = (result.stderr or b"").decode("utf-8", errors="replace") if isinstance(result.stderr, (bytes, bytearray)) else str(result.stderr or "")

    if log_path is not None and capture_output:
        try:
            _write_failure_log(Path(log_path), stdout, stderr)
            if not quiet:
                _LOG.error("verify-demo failed; log written to %s", log_path)
        except Exception as exc:  # noqa: BLE001
            if not quiet:
                _LOG.error("verify-demo failed; log write error: %s", exc)
    elif not quiet:
        if stderr:
            _LOG.error("verify-demo stderr (tail):")
            for line in _tail_lines(stderr):
                _LOG.error("%s", line)
        if stdout:
            _LOG.error("verify-demo stdout (tail):")
            for line in _tail_lines(stdout):
                _LOG.error("%s", line)

    if not quiet:
        _LOG.error("FAILED (pytest exit=%s)", result.returncode)
    return result.returncode
