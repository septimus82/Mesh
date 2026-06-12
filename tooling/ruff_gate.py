from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

BASELINE_PATH = Path(__file__).resolve().parent / "ruff_baseline.txt"
_EMBEDDED_LINE_RE = re.compile(r"\bline \d+\b")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_relative_path(filename: str, repo_root: Path) -> str:
    path = Path(filename)
    try:
        if path.is_absolute():
            return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        pass
    normalized = filename.replace("\\", "/")
    root_posix = repo_root.resolve().as_posix()
    if normalized.startswith(root_posix):
        normalized = normalized[len(root_posix) :]
    return normalized.lstrip("/")


def _normalize_message(message: str) -> str:
    return _EMBEDDED_LINE_RE.sub("line <line>", " ".join(str(message).split()))


def normalize_finding(finding: dict[str, object], repo_root: Path) -> str:
    path = _repo_relative_path(str(finding.get("filename", "")), repo_root)
    code = str(finding.get("code", "")).strip()
    message = _normalize_message(str(finding.get("message", "")).strip())
    return f"{path}: {code} {message}".strip()


def normalize_findings(findings: list[dict[str, object]], repo_root: Path) -> list[str]:
    return [normalize_finding(finding, repo_root) for finding in findings]


def _run_ruff(repo_root: Path) -> tuple[int, list[str]]:
    result = subprocess.run([sys.executable, "-m", "ruff", "check", "--output-format=json", "."], cwd=repo_root, capture_output=True, text=True)
    output = result.stdout or "[]"
    try:
        findings = json.loads(output)
    except json.JSONDecodeError:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        return result.returncode if result.returncode not in (0, 1) else 2, []
    if not isinstance(findings, list):
        return 2, []
    return result.returncode, normalize_findings(findings, repo_root)


def _read_baseline() -> list[str]:
    if not BASELINE_PATH.exists():
        return []
    return [line.strip().replace("\\", "/") for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_baseline(lines: list[str]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")


def find_new_findings(current_lines: list[str], baseline_lines: list[str]) -> list[str]:
    baseline_counts = Counter(baseline_lines)
    current_counts = Counter(current_lines)
    new_findings: list[str] = []
    for line in sorted(current_counts):
        extra_count = current_counts[line] - baseline_counts.get(line, 0)
        if extra_count > 0:
            new_findings.extend([line] * extra_count)
    return new_findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ruff ratchet gate")
    parser.add_argument("--update-baseline", action="store_true", help="Update baseline with current ruff output")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    code, current_lines = _run_ruff(repo_root)
    if code not in (0, 1):
        print(f"[ruff-gate] failed to run ruff (code {code})")
        return 2

    if args.update_baseline:
        _write_baseline(current_lines)
        print(f"[ruff-gate] baseline updated at {BASELINE_PATH.as_posix()}")
        return 0

    new_findings = find_new_findings(current_lines, _read_baseline())
    if new_findings:
        print("[ruff-gate] new ruff findings detected:")
        for line in new_findings:
            print(line)
        return 1

    print("[ruff-gate] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
