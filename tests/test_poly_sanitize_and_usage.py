from __future__ import annotations

from engine.geometry_tools import sanitize_poly


def test_sanitize_poly_empty() -> None:
    assert sanitize_poly([]) == []


def test_sanitize_poly_too_few_points() -> None:
    assert sanitize_poly([[0, 0], [1, 1]]) == []


def test_sanitize_poly_removes_duplicates() -> None:
    points = sanitize_poly([[0, 0], [0, 0], [1, 0], [0, 1]])
    assert points == [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]


def test_sanitize_poly_removes_closing_point() -> None:
    points = sanitize_poly([[0, 0], [1, 0], [0, 1], [0, 0]])
    assert points == [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
