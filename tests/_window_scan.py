"""Static half of the fake-only window attribute meta-test (S1 5.6 (b); from docs/s1/evidence/_contract_scan.py).

Pure AST: nothing from the engine is imported.

- ``production_fallbacks()``: every ``getattr(<window>, "name", ...)`` / ``hasattr(<window>, "name")`` in engine/,
  mesh_net/ and mesh_cli/, where the receiver's text ends in a window-like name. Such a read silently turns a feature
  off when the attribute is missing.
- ``production_window_writes()``: every attribute name production ever stores on a window (created lazily).
- ``fake_window_attrs()``: the attribute names tests give to, or read from, unspec'd fake windows (MagicMock/Mock/
  SimpleNamespace windows, ``class *Window*`` stand-ins). A spec'd ``tests._fake_window.fake_window()`` is not one.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("engine", "mesh_net", "mesh_cli")
WINDOWISH = re.compile(r"(^|\.)_?(window|win|game_window|gw|fake_window|dummy_window|stub_window|mock_window)$")
FAKE_CALLS = {"MagicMock", "Mock", "SimpleNamespace", "NonCallableMagicMock", "create_autospec", "AsyncMock"}
_MOCK_API = ("assert_", "return_value", "side_effect", "call_args", "called", "call_count", "mock_calls",
             "method_calls", "reset_mock", "configure_mock", "spec")


# (only files whose text could hold a match are parsed: the scan runs in the required pytest jobs)
_PRODUCTION_HINT = re.compile(r"\b_?(window|win|game_window|gw)\b")
_FAKE_HINT = re.compile(r"(?:window|\bwin|\bgw)\w*\s*(?::[^=\n]*)?=\s*(?:\w+\.)?(?:MagicMock|Mock|SimpleNamespace|"
                        r"NonCallableMagicMock|create_autospec|AsyncMock)\(|class \w*[Ww]indow")


@cache
def _trees(roots: tuple[str, ...], hint: re.Pattern[str]) -> tuple[tuple[str, ast.AST], ...]:
    out = []
    for root in roots:
        for path in sorted((REPO / root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if not hint.search(text):
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            out.append((path.relative_to(REPO).as_posix(), tree))
    return tuple(out)


def production_fallbacks() -> dict[str, list[str]]:
    """{name: ["file:line", ...]} for getattr/hasattr fallbacks on window-like receivers."""
    found: dict[str, list[str]] = defaultdict(list)
    for rel, tree in _trees(PRODUCTION, _PRODUCTION_HINT):
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("getattr", "hasattr") and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)
                    and WINDOWISH.search(ast.unparse(node.args[0]))):
                found[node.args[1].value].append(f"{rel}:{node.lineno}")
    return dict(found)


def production_window_writes() -> set[str]:
    """Names production stores on a window-like receiver (``window.x = ...``, ``setattr(window, "x", ...)``, or
    ``self.x = ...`` in engine/game.py and engine/game_parts/)."""
    names: set[str] = set()
    for rel, tree in _trees(PRODUCTION, _PRODUCTION_HINT):
        self_is_window = rel == "engine/game.py" or rel.startswith("engine/game_parts/")
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                text = ast.unparse(node.value)
                if WINDOWISH.search(text) or (self_is_window and text == "self"):
                    names.add(node.attr)
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr"
                  and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                  and WINDOWISH.search(ast.unparse(node.args[0]))):
                names.add(str(node.args[1].value))
    return names


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    return None


def fake_window_attrs() -> dict[str, set[str]]:
    """{name: {test files}} for the attributes unspec'd fake windows across tests/ are given or read."""
    attrs: dict[str, set[str]] = defaultdict(set)
    for rel, tree in _trees(("tests",), _FAKE_HINT):
        fakes: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                call = _call_name(node.value)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if call in FAKE_CALLS and WINDOWISH.search(ast.unparse(target)):
                        fakes.add(ast.unparse(target))
                        if call == "SimpleNamespace":
                            for kw in node.value.keywords:  # type: ignore[union-attr]
                                if kw.arg:
                                    attrs[kw.arg].add(rel)
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg and WINDOWISH.search(kw.arg) and _call_name(kw.value) in FAKE_CALLS:
                        for inner in kw.value.keywords:  # type: ignore[attr-defined]
                            if inner.arg:
                                attrs[inner.arg].add(rel)
            if isinstance(node, ast.ClassDef) and "window" in node.name.lower() and not node.name.startswith("Test"):
                for item in ast.walk(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("__"):
                        attrs[item.name].add(rel)
                    if isinstance(item, (ast.Assign, ast.AnnAssign)):
                        for target in item.targets if isinstance(item, ast.Assign) else [item.target]:
                            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) \
                                    and target.value.id == "self":
                                attrs[target.attr].add(rel)
                            elif isinstance(target, ast.Name):
                                attrs[target.id].add(rel)
        if fakes:
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and ast.unparse(node.value) in fakes \
                        and not node.attr.startswith(_MOCK_API):
                    attrs[node.attr].add(rel)
    return dict(attrs)
