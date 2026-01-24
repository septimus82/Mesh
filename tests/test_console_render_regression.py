from __future__ import annotations

from engine.console_runtime.render import get_visible_lines, wrap_lines_for_display


def test_visible_lines_slice_is_stable() -> None:
    lines = [f"line{i}" for i in range(10)]
    visible, offset = get_visible_lines(lines, visible_line_count=3, scroll_offset=0)
    assert offset == 0
    assert visible == ["line7", "line8", "line9"]

    visible, offset = get_visible_lines(lines, visible_line_count=3, scroll_offset=2)
    assert offset == 2
    assert visible == ["line5", "line6", "line7"]


def test_wrap_lines_for_display_is_deterministic() -> None:
    wrapped = wrap_lines_for_display(["abcdef", "x\ny"], max_cols=2)
    assert wrapped == ["ab", "cd", "ef", "x", "y"]

    capped = wrap_lines_for_display(["abcdef"], max_cols=2, max_lines=2)
    assert capped == ["cd", "ef"]
