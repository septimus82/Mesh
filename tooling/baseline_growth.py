"""Baselines and ratchets don't grow unless a commit says why (#624 phase B, PR b).

Each ratchet below lets through what its committed baseline lists, so a pull request that adds to the baseline in the
same change passed CI. This compares each baseline in the working tree against the same file at the merge base
(``git merge-base HEAD <base>``) and fails on any growth, unless a commit in ``<merge-base>..HEAD`` carries a line

    baseline-growth: <path>: <reason>

naming that file (exactly as listed below) and a reason. A commit message, not the pull request body: it travels with
the change, works offline and on push runs, and can't be edited after CI has run. Shrinking passes; a baseline that is
new at the merge base has nothing to grow from.

    python -m tooling.baseline_growth --base origin/redesign/visual-editor

Exit codes: 0 no unexplained growth, 1 growth without a marker, 2 the check could not run (no git, a base that doesn't
resolve, a baseline that doesn't parse). Stdlib only: CI runs it without installing the project.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# path -> how its contents are compared
BASELINES: dict[str, str] = {
    "tooling/ruff_baseline.txt": "lines",
    "tooling/mypy_baseline.txt": "lines",
    "tooling/exception_policy_baseline.json": "counts",
    "tooling/metrics/exception_budget_count.txt": "number",
    "tests/baselines/unmarked_test_nodeids.txt": "lines",
    "tests/baselines/never_runs.txt": "lines",
    "tests/baselines/quarantine.txt": "lines",  # a new or renewed quarantine (D10): its changed line is growth
    "tests/baselines/fast_marking_contract_allowlist.txt": "lines",
    "tests/test_todo_audit_ratchet_contract.py": "BASELINE_TOTAL",  # the tech-debt marker cap, a constant in the test
    "tests/baselines/public_api_exports.txt": "lines",  # the public API grows only on purpose
    # Budgets and tolerances: every number in them is a limit, so a higher one (or one removed) loosens a gate.
    "tooling/metrics/verify_step_budget.json": "counts",
    "tooling/metrics/authoring_trace_budget.json": "counts",
    "tooling/perf_baselines/baselines.json": "counts",
}
# path -> sections of a "counts" file in which a new key is growth too (it turns a limit off, not just up)
LOOSENING_SECTIONS: dict[str, tuple[str, ...]] = {
    "tooling/metrics/verify_step_budget.json": ("report_only_ceiling_ratios",),
}
MYPY_BASELINE = "tooling/mypy_baseline.txt"
_MARKER_RE = re.compile(r"^[ \t]*baseline-growth:[ \t]*(?P<path>[^\s:]+)[ \t]*:[ \t]*(?P<reason>[^\s\x00].*?)[ \t]*$",
                        re.M)


class CheckError(Exception):
    """The check could not run (exit 2)."""


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    except OSError as exc:
        raise CheckError(f"git is not available: {exc}") from exc
    if result.returncode != 0:
        raise CheckError(f"git {' '.join(args)} failed: {result.stderr.strip() or result.returncode}")
    return result.stdout


def _entries(text: str) -> Counter[str]:
    # One entry per line; blank and "#" lines are comments, and so is a trailing "  # reason" (never_runs.txt).
    return Counter(line.split("  #", 1)[0].strip() for line in text.splitlines()
                   if line.strip() and not line.lstrip().startswith("#"))


def _flatten(value: object, prefix: str, out: dict[str, float]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key != "schema_version":
                _flatten(item, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, list):
        ids = [item.get("id") for item in value if isinstance(item, dict)]
        keyed = len(ids) == len(value) and all(isinstance(i, str) for i in ids) and len(set(ids)) == len(ids)
        for index, item in enumerate(value):  # a list of records with unique ids: by id, so reordering isn't growth
            key = item["id"] if keyed and isinstance(item, dict) else index
            _flatten(item, f"{prefix}[{key}]", out)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        out[prefix] = value


def _counts(text: str, path: str) -> dict[str, float]:
    """Every number in the JSON by its path (``a.b[id].c``); strings and booleans don't count."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CheckError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CheckError(f"{path} is not a JSON object")
    out: dict[str, float] = {}
    _flatten(payload, "", out)
    return out


def _number(text: str, path: str, kind: str) -> int:
    if kind == "number":
        found = text.strip()
    else:
        assigned = re.findall(rf"^{kind}\s*=\s*(\d+)\s*$", text, re.M)
        found = assigned[-1] if assigned else ""  # the last assignment wins, as in Python
    try:
        return int(found)
    except ValueError as exc:
        raise CheckError(f"{path}: no {kind} found") from exc


def growth(path: str, kind: str, base: str, head: str | None) -> list[str]:
    """How ``head`` grew from ``base`` (empty when it didn't). A baseline deleted at head counts as growth: every ratchet
    that reads one then lets everything through, or fails without saying why."""
    if head is None:
        return ["deleted"]
    if kind == "lines":
        added = _entries(head) - _entries(base)
        rows = sorted(added.elements())
        return [f"+ {row}" for row in rows[:20]] + ([f"... and {len(rows) - 20} more"] if len(rows) > 20 else [])
    if kind == "counts":
        old, new = _counts(base, path), _counts(head, path)
        grew = [f"{key}: {old[key]} -> {new[key] if key in new else 'removed'}"
                for key in sorted(old) if key not in new or new[key] > old[key]]  # (up or removed)
        # A new key here makes a hard limit report-only, so adding one loosens a gate too (#697).
        return grew + [f"{key}: new {new[key]}" for key in sorted(new) if key not in old
                       and any(f".{part}." in f".{key}" for part in LOOSENING_SECTIONS.get(path, ()))]
    old_n, new_n = _number(base, path, kind), _number(head, path, kind)
    return [f"{old_n} -> {new_n}"] if new_n > old_n else []


def markers(repo: Path, merge_base: str) -> dict[str, str]:
    """``path -> reason`` from the ``baseline-growth:`` lines of the commits in ``merge_base..HEAD``."""
    log = _git(repo, "log", "--format=%B%x00", f"{merge_base}..HEAD")
    return {m.group("path"): m.group("reason") for m in _MARKER_RE.finditer(log)}


def check(repo: Path, base: str, paths: list[str] | None = None) -> tuple[int, list[str]]:
    """Compare ``paths`` (default: every baseline) with the merge base of HEAD and ``base``: (exit code, report lines)."""
    try:
        merge_base = _git(repo, "merge-base", "HEAD", base).strip()
        explained = markers(repo, merge_base)
        lines: list[str] = []
        unexplained = 0
        for path in paths or list(BASELINES):
            if not _git(repo, "ls-tree", "--name-only", merge_base, "--", path).strip():
                continue  # new since the merge base: nothing to grow from
            base_text = _git(repo, "show", f"{merge_base}:{path}")
            head_file = repo / path
            head_text = head_file.read_text(encoding="utf-8") if head_file.is_file() else None
            grew = growth(path, BASELINES[path], base_text, head_text)
            if not grew:
                continue
            if path in explained:
                lines.append(f"{path} grew, explained: {explained[path]}")
            else:
                unexplained += 1
                lines.append(f"{path} grew since {merge_base[:12]} with no 'baseline-growth: {path}: <reason>' "
                             "line in a commit message:")
            lines += [f"    {row}" for row in grew]
    except CheckError as exc:
        return 2, [str(exc)]
    return (1 if unexplained else 0), lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", required=True, help="the branch (or commit) the change is merged into")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    code, lines = check(args.repo, args.base)
    for line in lines:
        print(f"[baseline-growth] {line}")
    print(f"[baseline-growth] {('ok', 'FAILED: a baseline grew without a reason', 'could not check')[code]}"
          f" (against the merge base with {args.base})")
    return code


if __name__ == "__main__":
    sys.exit(main())
