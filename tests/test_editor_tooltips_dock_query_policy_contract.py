from __future__ import annotations

from pathlib import Path


def test_editor_tooltips_use_dock_query() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "engine" / "editor_tooltips_model.py"
    text = path.read_text(encoding="utf-8", errors="ignore")
    left_key = "left" + "_dock" + "_width"
    right_key = "right" + "_dock" + "_width"
    assert "get_raw_dock_widths" in text, "Tooltip model must use editor_dock_query for dock widths."
    assert left_key not in text, "Direct dock width reads are disallowed in tooltips."
    assert right_key not in text, "Direct dock width reads are disallowed in tooltips."
