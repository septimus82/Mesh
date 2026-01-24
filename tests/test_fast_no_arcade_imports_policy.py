from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


_FORBIDDEN = [
    re.compile(r"^\s*import\s+arcade\b"),
    re.compile(r"^\s*from\s+arcade\b"),
    re.compile(r"^\s*import\s+arcade\.gl\b"),
    re.compile(r"^\s*from\s+arcade\.gl\b"),
]


def _extract_fast_nodeids(conftest_path: Path) -> set[str]:
    tree = ast.parse(conftest_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_FAST_TEST_NODEIDS":
                    value = ast.literal_eval(node.value)
                    return {str(entry) for entry in value}
    return set()


def _is_fast_file(path: Path, fast_nodeids: set[str]) -> bool:
    if path.name in fast_nodeids:
        return True
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "pytest.mark.fast" in text or "pytestmark = pytest.mark.fast" in text


def test_fast_tests_do_not_import_arcade() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    conftest_path = repo_root / "tests" / "conftest.py"
    fast_nodeids = _extract_fast_nodeids(conftest_path)

    violations: list[str] = []
    tests_root = repo_root / "tests"
    for root, _, files in os.walk(tests_root):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = Path(root) / name
            if not _is_fast_file(path, fast_nodeids):
                continue
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            in_type_checking = False
            type_check_indent = -1
            for idx, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                indent = len(line) - len(line.lstrip())
                if in_type_checking and indent <= type_check_indent:
                    in_type_checking = False
                if "TYPE_CHECKING" in line and stripped.startswith("if"):
                    in_type_checking = True
                    type_check_indent = indent
                    continue
                if in_type_checking:
                    continue
                for pattern in _FORBIDDEN:
                    if pattern.search(line):
                        violations.append(f"{path.relative_to(repo_root)}:{idx}: {stripped}")
                        break

    if violations:
        pytest.fail("Fast tests must not import arcade:\n" + "\n".join(violations))
