from __future__ import annotations

import re
from pathlib import Path


def test_hover_field_reads_are_centralized() -> None:
    root = Path(__file__).resolve().parents[1]
    engine_root = root / "engine"
    allowlist = {
        "engine/editor_controller_core.py",
        "engine/editor_controller.py",
        "engine/editor/editor_hover_query.py",
        "engine/editor/editor_hover_dock_tab_query.py",
    }
    patterns = [
        re.compile(r"\._hover_splitter\b"),
        re.compile(r"\._hover_splitter_rect\b"),
        re.compile(r"\._hover_inspector_field_key\b"),
        re.compile(r"\._hover_inspector_field_rect\b"),
        re.compile(r"\._hover_entity_id\b"),
        re.compile(r"\._hover_entity_rect\b"),
        re.compile(r"['_\"]_hover_splitter['_\"]"),
        re.compile(r"['_\"]_hover_splitter_rect['_\"]"),
        re.compile(r"['_\"]_hover_inspector_field_key['_\"]"),
        re.compile(r"['_\"]_hover_inspector_field_rect['_\"]"),
        re.compile(r"['_\"]_hover_entity_id['_\"]"),
        re.compile(r"['_\"]_hover_entity_rect['_\"]"),
    ]
    violations: list[str] = []
    for path in engine_root.rglob("*.py"):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel in allowlist:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            violations.append(rel)
    assert not violations, f"Use editor_hover_query for hover field reads: {violations}"
