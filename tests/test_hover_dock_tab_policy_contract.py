from __future__ import annotations

from pathlib import Path

import re


def test_hover_dock_tab_reads_are_centralized() -> None:
    root = Path(__file__).resolve().parents[1]
    engine_root = root / "engine"
    allowlist = {
        "engine/editor_controller.py",
        "engine/editor/editor_hover_dock_tab_query.py",
    }
    attr_patterns = [
        re.compile(r"\._hover_dock_tab\b"),
        re.compile(r"\._hover_dock_tab_rect\b"),
        re.compile(r"['_\"]_hover_dock_tab['_\"]"),
        re.compile(r"['_\"]_hover_dock_tab_rect['_\"]"),
    ]
    violations: list[str] = []
    for path in engine_root.rglob("*.py"):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel in allowlist:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in attr_patterns):
            violations.append(rel)
    assert not violations, f"Use editor_hover_dock_tab_query for hover dock tab reads: {violations}"
