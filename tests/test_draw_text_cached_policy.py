from __future__ import annotations

import ast
from pathlib import Path


def test_draw_text_cached_call_signature_policy() -> None:
    """Ensure draw_text_cached is only called with text/x/y positional args."""
    root = Path("engine")
    violations: list[str] = []

    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr

            if name != "draw_text_cached":
                continue

            if len(node.args) > 3:
                violations.append(f"{path}:{node.lineno} uses {len(node.args)} positional args")
                continue

            if node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Attribute) and arg0.attr in {"text_cache", "_text_cache", "cache"}:
                    violations.append(f"{path}:{node.lineno} first arg looks like a cache object")

    assert not violations, "draw_text_cached must be called as draw_text_cached(text, x, y, *, ...):\n" + "\n".join(violations)
