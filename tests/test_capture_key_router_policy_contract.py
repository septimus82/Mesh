from __future__ import annotations

import ast
from pathlib import Path


def test_no_legacy_handlers() -> None:
    path = Path("engine/input_runtime/capture_runtime.py")
    source = path.read_text(encoding="utf-8")
    assert "handle_unmapped_key" not in source


def test_capture_runtime_handle_key_press_size() -> None:
    source = Path("engine/input_runtime/capture_runtime.py").read_text(encoding="utf-8")
    mod = ast.parse(source)
    fn = None
    for node in mod.body:
        if isinstance(node, ast.FunctionDef) and node.name == "handle_key_press":
            fn = node
            break
    assert fn is not None
    start = fn.lineno
    end = fn.end_lineno or fn.lineno
    assert (end - start + 1) <= 250
