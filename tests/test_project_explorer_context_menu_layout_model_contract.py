from engine.editor.project_explorer_context_menu_layout_model import clamp_menu_rect


def test_clamp_menu_rect_within_bounds() -> None:
    assert clamp_menu_rect(10, 10, 100, 50, 800, 600) == (10, 10)


def test_clamp_menu_rect_right_edge() -> None:
    assert clamp_menu_rect(790, 10, 100, 50, 800, 600) == (700, 10)


def test_clamp_menu_rect_top_edge() -> None:
    assert clamp_menu_rect(10, 590, 100, 50, 800, 600) == (10, 550)


def test_clamp_menu_rect_corner() -> None:
    assert clamp_menu_rect(790, 590, 100, 50, 800, 600) == (700, 550)
