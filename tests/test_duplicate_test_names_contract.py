from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _find_duplicate_tests(source: str, *, path: str) -> list[str]:
    tree = ast.parse(source, filename=path)
    duplicates: list[str] = []

    module_tests: dict[str, list[int]] = defaultdict(list)
    class_tests: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            module_tests[node.name].append(node.lineno)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_"):
                    class_tests[node.name][child.name].append(child.lineno)

    for name, lines in module_tests.items():
        if len(lines) > 1:
            duplicates.append(f"{path}: {name} defined at lines {lines}")
    for class_name, methods in class_tests.items():
        for name, lines in methods.items():
            if len(lines) > 1:
                duplicates.append(f"{path}: {class_name}.{name} defined at lines {lines}")
    return duplicates


def test_duplicate_test_name_scanner_flags_synthetic_duplicate() -> None:
    source = """
def test_same():
    pass

def test_same():
    pass

class TestExample:
    def test_case(self):
        pass

    def test_case(self):
        pass
"""

    assert _find_duplicate_tests(source, path="synthetic.py") == [
        "synthetic.py: test_same defined at lines [2, 5]",
        "synthetic.py: TestExample.test_case defined at lines [9, 12]",
    ]


def test_no_duplicate_test_names_in_module_or_class_scope() -> None:
    duplicates: list[str] = []
    for path in sorted((_REPO_ROOT / "tests").rglob("test*.py")):
        rel_path = path.relative_to(_REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8-sig")
        duplicates.extend(_find_duplicate_tests(source, path=rel_path))

    assert duplicates == []
