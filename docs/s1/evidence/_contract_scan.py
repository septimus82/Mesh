"""Static half of the S1-0 contract map (pure AST, imports nothing from the engine).

production_fallbacks(): every ``getattr(<window-ish>, "name", ...)`` / ``hasattr(<window-ish>, "name")`` in engine/,
mesh_net/ and mesh_cli/, where the receiver's source text ends in a window-like name. These are the reads that
silently turn a feature off when the attribute is missing.

test_fake_attrs(): attribute names that tests give to, or read from, *fake* windows: names bound to MagicMock()/
Mock()/SimpleNamespace(...)/create_autospec() whose variable name looks like a window, keyword arguments of such
SimpleNamespace(...) calls, ``fake.attr = ...`` assignments and ``fake.attr`` reads, and ``self.attr`` assignments
plus method names in test classes named like ``*Window*`` (fakes/dummies/stubs).

Used by contract_gaps_real_window.py; run alone it prints a summary.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WINDOWISH = re.compile(r"(^|\.)_?(window|win|game_window|gw|fake_window|dummy_window|stub_window|mock_window)$")
FAKE_CALLS = {"MagicMock", "Mock", "SimpleNamespace", "NonCallableMagicMock", "create_autospec", "AsyncMock"}


def _py_files(*roots: str) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        out.extend(p for p in (REPO / root).rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(out)


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    except SyntaxError:
        return None


def production_fallbacks(roots: tuple[str, ...] = ("engine", "mesh_net", "mesh_cli"),
                         receiver: re.Pattern[str] = WINDOWISH) -> dict[str, list[str]]:
    """{attr name: ["file:line kind(receiver)", ...]} for getattr/hasattr fallbacks on receivers matching ``receiver``
    (window-like by default)."""
    found: dict[str, list[str]] = defaultdict(list)
    for path in _py_files(*roots):
        tree = _parse(path)
        if tree is None:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in ("getattr", "hasattr") or len(node.args) < 2:
                continue
            recv, name = node.args[0], node.args[1]
            if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
                continue
            text = ast.unparse(recv)
            if receiver.search(text):
                found[name.value].append(f"{rel}:{node.lineno} {node.func.id}({text})")
    return dict(found)


def production_direct_reads(roots: tuple[str, ...] = ("engine", "mesh_net", "mesh_cli")) -> dict[str, list[str]]:
    """{attr: ["file:line receiver"]} for plain ``<window-ish>.attr`` LOADS (not stores) in production code."""
    found: dict[str, list[str]] = defaultdict(list)
    for path in _py_files(*roots):
        tree = _parse(path)
        if tree is None:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                text = ast.unparse(node.value)
                if WINDOWISH.search(text) and not node.attr.startswith("__"):
                    found[node.attr].append(f"{rel}:{node.lineno} {text}")
    return dict(found)


def production_window_writes(roots: tuple[str, ...] = ("engine", "mesh_net", "mesh_cli")) -> set[str]:
    """Attribute names production ever stores on a window-like receiver (``window.x = ...``, ``setattr(window, "x",
    ...)``, or ``self.x = ...`` inside engine/game.py and engine/game_parts/). A missing name outside this set is never
    created by production at all."""
    names: set[str] = set()
    for path in _py_files(*roots):
        tree = _parse(path)
        if tree is None:
            continue
        rel = path.relative_to(REPO).as_posix()
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
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
    return None


def test_fake_attrs(root: str = "tests") -> tuple[dict[str, set[str]], dict[str, int]]:
    """({attr: {test files}}, counters) for fake windows across tests/."""
    attrs: dict[str, set[str]] = defaultdict(set)
    counts = {"MagicMock_windows": 0, "SimpleNamespace_windows": 0, "fake_window_classes": 0, "files": 0}
    for path in _py_files(root):
        tree = _parse(path)
        if tree is None:
            continue
        rel = path.relative_to(REPO).as_posix()
        fakes: set[str] = set()  # unparsed target texts bound to a fake
        touched = False
        for node in ast.walk(tree):
            # window = MagicMock() / SimpleNamespace(...)  (also self.window = ..., window: Any = ...)
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                call = _call_name(node.value)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    text = ast.unparse(t)
                    if call in FAKE_CALLS and WINDOWISH.search(text):
                        fakes.add(text)
                        touched = True
                        counts["SimpleNamespace_windows" if call == "SimpleNamespace" else "MagicMock_windows"] += 1
                        if call == "SimpleNamespace":
                            for kw in node.value.keywords:  # type: ignore[union-attr]
                                if kw.arg:
                                    attrs[kw.arg].add(rel)
            # SimpleNamespace(window=SimpleNamespace(a=..., b=...)) or f(window=MagicMock(...))
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg and WINDOWISH.search(kw.arg) and _call_name(kw.value) in FAKE_CALLS:
                        touched = True
                        key = "SimpleNamespace_windows" if _call_name(kw.value) == "SimpleNamespace" else "MagicMock_windows"
                        counts[key] += 1
                        for inner in kw.value.keywords:  # type: ignore[attr-defined]
                            if inner.arg:
                                attrs[inner.arg].add(rel)
            # class FakeWindow / DummyWindow / _StubWindow ...
            if isinstance(node, ast.ClassDef) and "window" in node.name.lower() and not node.name.startswith("Test"):
                counts["fake_window_classes"] += 1
                touched = True
                for item in ast.walk(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("__"):
                        attrs[item.name].add(rel)
                    if isinstance(item, (ast.Assign, ast.AnnAssign)):
                        tgts = item.targets if isinstance(item, ast.Assign) else [item.target]
                        for t in tgts:
                            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                                attrs[t.attr].add(rel)
                            elif isinstance(t, ast.Name):
                                attrs[t.id].add(rel)
        if fakes:
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and ast.unparse(node.value) in fakes:
                    if not node.attr.startswith(("assert_", "return_value", "side_effect", "call_args", "called",
                                                 "call_count", "mock_calls", "method_calls", "reset_mock",
                                                 "configure_mock", "spec")):
                        attrs[node.attr].add(rel)
        if touched:
            counts["files"] += 1
    return dict(attrs), counts


if __name__ == "__main__":
    fb = production_fallbacks()
    ta, counts = test_fake_attrs()
    print(f"production window fallbacks: {sum(len(v) for v in fb.values())} reads of {len(fb)} names")
    print(f"test fakes: {counts} ; distinct attribute names on fake windows: {len(ta)}")
