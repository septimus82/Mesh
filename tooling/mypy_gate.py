from __future__ import annotations

import argparse
import copy
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

BASELINE_PATH = Path(__file__).resolve().parent / "mypy_baseline.txt"
_LAST_RUN_DIAGNOSTICS: dict[str, object] | None = None
_MYPY_ERROR_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): error: (?P<message>.*?)(?P<code>\s+\[[^\]]+\])$"
)
_MYPY_EMBEDDED_LINE_RE = re.compile(r"\bon line \d+\b")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_cache_dir(repo_root: Path) -> Path:
    return repo_root / ".mypy_cache" / "mypy_gate"


def _build_mypy_command(repo_root: Path) -> tuple[list[str], Path]:
    cache_dir = _default_cache_dir(repo_root)
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        ".",
        "--show-error-codes",
        "--incremental",
        "--cache-dir",
        str(cache_dir),
    ]
    return cmd, cache_dir


def _extract_mypy_summary(output: str) -> tuple[str | None, int | None]:
    summary_line: str | None = None
    files_checked: int | None = None
    for raw_line in output.splitlines():
        line = str(raw_line).strip()
        if not line:
            continue
        if line.startswith("Success:") or line.startswith("Found "):
            summary_line = line

    if summary_line:
        match = re.search(r"\(checked\s+(\d+)\s+source files?\)", summary_line)
        if match:
            files_checked = int(match.group(1))
        else:
            match = re.search(r"no issues found in\s+(\d+)\s+source files?", summary_line)
            if match:
                files_checked = int(match.group(1))
    return summary_line, files_checked


def _normalize_lines(raw: str, repo_root: Path) -> list[str]:
    root_posix = repo_root.resolve().as_posix()
    root_native = str(repo_root.resolve())
    lines: list[str] = []
    for entry in raw.splitlines():
        line = entry.strip()
        if not line:
            continue
        if " error: " not in line:
            continue
        if root_posix in line:
            line = line.replace(root_posix, "")
        if root_native in line:
            line = line.replace(root_native, "")
        line = line.replace("\\", "/")
        if line.startswith("/"):
            line = line[1:]
        line = _normalize_mypy_error_line(line)
        lines.append(line)
    return lines


def _normalize_mypy_error_line(line: str) -> str:
    match = _MYPY_ERROR_RE.match(line)
    if not match:
        return line
    message = _MYPY_EMBEDDED_LINE_RE.sub("on line <line>", match.group("message"))
    return f"{match.group('path')}: error: {message}{match.group('code')}"


def _run_mypy(repo_root: Path) -> tuple[int, list[str], dict[str, object]]:
    cmd, cache_dir = _build_mypy_command(repo_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    wall_time_seconds = float(max(0.0, time.perf_counter() - started))
    output = (result.stdout or "") + (result.stderr or "")
    summary, files_checked = _extract_mypy_summary(output)
    diagnostics: dict[str, object] = {
        "schema_version": 1,
        "command_argv": list(cmd),
        "command_line": " ".join(str(part) for part in cmd),
        "wall_time_seconds": wall_time_seconds,
        "summary": summary,
        "files_checked": files_checked,
        "cache": {
            "enabled": True,
            "incremental": True,
            "cache_dir": cache_dir.resolve().as_posix(),
        },
        "python_version": sys.version.split()[0],
        "return_code": int(result.returncode),
    }
    return result.returncode, _normalize_lines(output, repo_root), diagnostics


def _read_baseline() -> list[str]:
    if not BASELINE_PATH.exists():
        return []
    raw = BASELINE_PATH.read_text(encoding="utf-8")
    lines: list[str] = []
    for entry in raw.splitlines():
        line = entry.strip().replace("\\", "/")
        if line:
            lines.append(_normalize_mypy_error_line(line))
    return lines


def _write_baseline(lines: list[str]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")


def get_last_run_diagnostics() -> dict[str, object] | None:
    if _LAST_RUN_DIAGNOSTICS is None:
        return None
    return copy.deepcopy(_LAST_RUN_DIAGNOSTICS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mypy ratchet gate")
    parser.add_argument("--update-baseline", action="store_true", help="Update baseline with current mypy output")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    global _LAST_RUN_DIAGNOSTICS
    code, current_lines, diagnostics = _run_mypy(repo_root)
    _LAST_RUN_DIAGNOSTICS = diagnostics
    if code not in (0, 1):
        print(f"[mypy-gate] failed to run mypy (code {code})")
        return 2

    if args.update_baseline:
        _write_baseline(current_lines)
        print(f"[mypy-gate] baseline updated at {BASELINE_PATH.as_posix()}")
        return 0

    baseline_lines = _read_baseline()
    baseline_counts = Counter(baseline_lines)
    current_counts = Counter(current_lines)
    new_errors: list[str] = []
    for line in sorted(current_counts):
        current_count = current_counts[line]
        baseline_count = baseline_counts.get(line, 0)
        if current_count > baseline_count:
            extra_count = current_count - baseline_count
            new_errors.extend([line] * extra_count)

    if new_errors:
        print("[mypy-gate] new mypy errors detected:")
        for line in new_errors:
            print(line)
        return 1

    print("[mypy-gate] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
