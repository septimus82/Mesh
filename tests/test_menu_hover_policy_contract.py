from __future__ import annotations

from pathlib import Path
import re


def test_menu_hover_reads_are_centralized() -> None:
    root = Path(__file__).resolve().parents[1]
    engine_root = root / "engine"
    allowlist = {
        "engine/editor_controller_core.py",
        "engine/editor_controller.py",
        "engine/editor/editor_menu_hover_query.py",
        "engine/editor_runtime/hover_detection.py",
        "engine/editor_runtime/input.py",
        "engine/editor_runtime/editor_input_menu_handlers.py",
    }
    patterns = [
        re.compile(r"\._menu_hover_title\b"),
        re.compile(r"\._menu_hover_title_rect\b"),
        re.compile(r"\._menu_hover_item_id\b"),
        re.compile(r"\._menu_hover_item_rect\b"),
        re.compile(r"\._context_menu_hover_id\b"),
        re.compile(r"\._hover_context_item_rect\b"),
        re.compile(r"['_\"]_menu_hover_title['_\"]"),
        re.compile(r"['_\"]_menu_hover_title_rect['_\"]"),
        re.compile(r"['_\"]_menu_hover_item_id['_\"]"),
        re.compile(r"['_\"]_menu_hover_item_rect['_\"]"),
        re.compile(r"['_\"]_context_menu_hover_id['_\"]"),
        re.compile(r"['_\"]_hover_context_item_rect['_\"]"),
    ]
    violations: list[str] = []
    for path in engine_root.rglob("*.py"):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel in allowlist:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            violations.append(rel)
    assert not violations, f"Use editor_menu_hover_query for menu/context hover reads: {violations}"
