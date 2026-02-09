from __future__ import annotations

import ast
from pathlib import Path


def _get_function_node(source: str, name: str) -> ast.FunctionDef:
    mod = ast.parse(source)
    for node in mod.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing function: {name}")


def test_get_editor_actions_size_and_shape() -> None:
    path = Path("engine/editor/editor_actions.py")
    source = path.read_text(encoding="utf-8")
    fn = _get_function_node(source, "get_editor_actions")
    start = fn.lineno
    end = fn.end_lineno or fn.lineno
    line_count = end - start + 1
    assert line_count <= 200, f"get_editor_actions too large: {line_count} lines"
    nested = [n for n in ast.walk(fn) if isinstance(n, ast.FunctionDef) and n is not fn]
    assert not nested, "get_editor_actions should not contain nested function defs"


def test_no_duplicate_enabled_helpers() -> None:
    path = Path("engine/editor/editor_actions.py")
    source = path.read_text(encoding="utf-8")
    mod = ast.parse(source)
    names: list[str] = []
    for node in mod.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_enabled_"):
            names.append(node.name)
    duplicates = {name for name in names if names.count(name) > 1}
    assert not duplicates, f"Duplicate _enabled_ helpers found: {sorted(duplicates)}"
