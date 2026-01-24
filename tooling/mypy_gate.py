from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


BASELINE_PATH = Path(__file__).resolve().parent / "mypy_baseline.txt"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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
        lines.append(line)
    return lines


def _run_mypy(repo_root: Path) -> tuple[int, list[str]]:
    cmd = [sys.executable, "-m", "mypy", ".", "--show-error-codes"]
    result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, _normalize_lines(output, repo_root)


def _read_baseline() -> list[str]:
    if not BASELINE_PATH.exists():
        return []
    raw = BASELINE_PATH.read_text(encoding="utf-8")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _write_baseline(lines: list[str]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mypy ratchet gate")
    parser.add_argument("--update-baseline", action="store_true", help="Update baseline with current mypy output")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    code, current_lines = _run_mypy(repo_root)
    if code not in (0, 1):
        print(f"[mypy-gate] failed to run mypy (code {code})")
        return 2

    if args.update_baseline:
        _write_baseline(current_lines)
        print(f"[mypy-gate] baseline updated at {BASELINE_PATH.as_posix()}")
        return 0

    baseline_lines = _read_baseline()
    baseline_set = set(baseline_lines)
    current_set = set(current_lines)
    new_errors = sorted(current_set - baseline_set)

    if new_errors:
        print("[mypy-gate] new mypy errors detected:")
        for line in new_errors:
            print(line)
        return 1

    print("[mypy-gate] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
