from __future__ import annotations

import ast
from pathlib import Path


def test_editor_actions_no_duplicate_enabled_functions() -> None:
    """Guard against duplicate _enabled_* defs that shadow earlier functions."""
    path = Path("engine/editor/editor_actions.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    seen: set[str] = set()
    duplicates: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_enabled_"):
            if node.name in seen:
                duplicates.append(node.name)
            else:
                seen.add(node.name)

    assert not duplicates, "Duplicate _enabled_* functions found: " + ", ".join(sorted(set(duplicates)))
