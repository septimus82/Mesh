"""Flake quarantine (S1 5.3, owner decision D10): dated, issue-linked, expiring, report-only, never retried.

``tests/baselines/quarantine.txt`` lists one quarantined test per line, four whitespace-separated fields:

    <node id> <issue number> <added YYYY-MM-DD> <expires YYYY-MM-DD>

``tests/conftest.py`` deselects every listed test from every run (CI's pytest jobs, the fast tier, verify-all and each
``tooling/test_tiers.py`` lane), except ``pytest --mesh-quarantined``, which runs only them: Extended's report-only
``quarantine`` job. ``problems`` is what ``tests/test_flake_quarantine_contract.py`` holds the file to: an open issue
number, ``added`` not in the future, ``expires`` not past and at most ``MAX_DAYS`` after ``added``, and a test that
exists. Stdlib only.
"""

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATH = REPO / "tests" / "baselines" / "quarantine.txt"
MAX_DAYS = 30


def _rows(text: str) -> list[list[str]]:
    return [line.strip().rsplit(None, 3) for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def quarantined(path: Path = PATH) -> set[str]:
    """The node ids of the well-formed entries. A malformed line quarantines nothing (its test keeps running in the
    required lanes) and fails the contract test."""
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {row[0] for row in _rows(text) if len(row) == 4}


def _test_exists(nodeid: str, repo: Path, trees: dict[str, set[str]]) -> bool:
    path, _, rest = nodeid.partition("::")
    if path not in trees:
        file = repo / path
        names: set[str] = set()
        if path.endswith(".py") and file.is_file():
            names = {node.name for node in ast.walk(ast.parse(file.read_text(encoding="utf-8")))
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        trees[path] = names
    # ponytail: names only (class and function); a parametrized id's [params] aren't checked. A wrong one deselects
    # nothing, so the test keeps running in the required lanes.
    parts = rest.split("[", 1)[0].split("::") if rest else []
    return bool(parts) and all(part in trees[path] for part in parts)


def problems(text: str, today: date, repo: Path = REPO) -> list[str]:
    out: list[str] = []
    trees: dict[str, set[str]] = {}
    for row in _rows(text):
        line = " ".join(row)
        if len(row) != 4:
            out.append(f"{line}: expected '<node id> <issue> <added YYYY-MM-DD> <expires YYYY-MM-DD>'")
            continue
        nodeid, issue, added_text, expires_text = row
        if not re.fullmatch(r"[1-9]\d*", issue):
            out.append(f"{line}: no issue number ({issue!r}); quarantine needs an open issue with the evidence")
        try:
            if not all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) for text in (added_text, expires_text)):
                raise ValueError  # (fromisoformat also takes 20261226 and week dates)
            added, expires = date.fromisoformat(added_text), date.fromisoformat(expires_text)
        except ValueError:
            out.append(f"{line}: dates must be YYYY-MM-DD")
        else:
            if added > today:
                out.append(f"{line}: added {added} is in the future")
            if expires < today:
                out.append(f"{line}: expired on {expires}; fix the test and remove the entry (or renew it on evidence)")
            if (expires - added).days > MAX_DAYS:
                out.append(f"{line}: expires {(expires - added).days} days after it was added, more than {MAX_DAYS}")
        if not _test_exists(nodeid, repo, trees):
            out.append(f"{line}: no such test")
    return out
