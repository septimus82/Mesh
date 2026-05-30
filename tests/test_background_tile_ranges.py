"""Unit tests for compute_background_tile_ranges pure helper.

Verifies that the viewport-derived tiling ranges:
- Clamp to the visible band (every tile intersects [0, viewport])
- Fully cover the visible region (no gaps)
- Slash overdraw vs. the old 2000-based bounds
- Are a strict subset of the old 2000-based range
- Return (0, 1) for non-repeating axes
- Compute x and y identically given symmetric inputs
"""
from __future__ import annotations

import pytest

from engine.scene_render_pipeline import compute_background_tile_ranges

pytestmark = [pytest.mark.fast]

# Representative test parameters used by most tests.
# base_x=641 and base_y=361 are non-degenerate (not exact multiples of tex_w/tex_h),
# ensuring tile boundaries don't coincide exactly with the viewport edges.
_BASE_X: float = 641.0
_BASE_Y: float = 361.0
_TEX: float = 16.0
_VW: float = 1280.0
_VH: float = 720.0


def _old_x_range(base_x: float, tex_w: float) -> tuple[int, int]:
    """Reproduce the legacy 2000-based x range (end-exclusive)."""
    start = -int(base_x // tex_w + 2)
    end = int(2000 // tex_w + 2)
    return (start, end)


def _old_y_range(base_y: float, tex_h: float) -> tuple[int, int]:
    """Reproduce the legacy 2000-based y range (end-exclusive)."""
    start = -int(base_y // tex_h + 2)
    end = int(2000 // tex_h + 2)
    return (start, end)


def test_non_repeat_x_returns_single_tile() -> None:
    (x_start, x_end), _ = compute_background_tile_ranges(
        _BASE_X, _BASE_Y, _TEX, _TEX, _VW, _VH, repeat_x=False, repeat_y=True
    )
    assert (x_start, x_end) == (0, 1)


def test_non_repeat_y_returns_single_tile() -> None:
    _, (y_start, y_end) = compute_background_tile_ranges(
        _BASE_X, _BASE_Y, _TEX, _TEX, _VW, _VH, repeat_x=True, repeat_y=False
    )
    assert (y_start, y_end) == (0, 1)


def test_both_non_repeat_returns_single_tile_each_axis() -> None:
    (x_start, x_end), (y_start, y_end) = compute_background_tile_ranges(
        _BASE_X, _BASE_Y, _TEX, _TEX, _VW, _VH, repeat_x=False, repeat_y=False
    )
    assert (x_start, x_end) == (0, 1)
    assert (y_start, y_end) == (0, 1)


def test_every_tile_in_range_intersects_viewport() -> None:
    """Every tile drawn must overlap at least one pixel of [0, viewport]."""
    (x_start, x_end), (y_start, y_end) = compute_background_tile_ranges(
        _BASE_X, _BASE_Y, _TEX, _TEX, _VW, _VH, repeat_x=True, repeat_y=True
    )
    half = _TEX / 2.0
    for ix in range(x_start, x_end):
        center = _BASE_X + ix * _TEX
        assert center + half > 0.0, f"tile ix={ix} right edge is outside viewport left"
        assert center - half < _VW, f"tile ix={ix} left edge is outside viewport right"
    for iy in range(y_start, y_end):
        center = _BASE_Y + iy * _TEX
        assert center + half > 0.0, f"tile iy={iy} top edge is outside viewport bottom"
        assert center - half < _VH, f"tile iy={iy} bottom edge is outside viewport top"


def test_viewport_fully_covered() -> None:
    """The union of tile rects must fully bracket [0, viewport] on each axis."""
    (x_start, x_end), (y_start, y_end) = compute_background_tile_ranges(
        _BASE_X, _BASE_Y, _TEX, _TEX, _VW, _VH, repeat_x=True, repeat_y=True
    )
    half = _TEX / 2.0

    # x-axis: leftmost tile covers x=0, rightmost tile covers x=viewport_w
    left_center = _BASE_X + x_start * _TEX
    assert left_center + half > 0.0, "leftmost tile does not cover viewport left edge"
    right_center = _BASE_X + (x_end - 1) * _TEX
    assert right_center - half < _VW, "rightmost tile starts beyond viewport right"
    assert right_center + half >= _VW, "rightmost tile does not cover viewport right edge"

    # y-axis
    bottom_center = _BASE_Y + y_start * _TEX
    assert bottom_center + half > 0.0, "bottommost tile does not cover viewport bottom"
    top_center = _BASE_Y + (y_end - 1) * _TEX
    assert top_center - half < _VH, "topmost tile starts beyond viewport top"
    assert top_center + half >= _VH, "topmost tile does not cover viewport top edge"


def test_overdraw_count_far_less_than_old_2000_bound() -> None:
    """New tile count must be much smaller than the old 2000-based bound."""
    (x_start, x_end), (y_start, y_end) = compute_background_tile_ranges(
        _BASE_X, _BASE_Y, _TEX, _TEX, _VW, _VH, repeat_x=True, repeat_y=True
    )
    new_x_count = x_end - x_start
    new_y_count = y_end - y_start

    old_x_start, old_x_end = _old_x_range(_BASE_X, _TEX)
    old_y_start, old_y_end = _old_y_range(_BASE_Y, _TEX)
    old_x_count = old_x_end - old_x_start
    old_y_count = old_y_end - old_y_start

    assert new_x_count < old_x_count, (
        f"x overdraw not reduced: new={new_x_count} >= old={old_x_count}"
    )
    assert new_y_count < old_y_count, (
        f"y overdraw not reduced: new={new_y_count} >= old={old_y_count}"
    )


def test_new_range_is_subset_of_old_2000_range() -> None:
    """New range must be contained within the old 2000-based range (no new visible tiles)."""
    (x_start, x_end), (y_start, y_end) = compute_background_tile_ranges(
        _BASE_X, _BASE_Y, _TEX, _TEX, _VW, _VH, repeat_x=True, repeat_y=True
    )
    old_x_start, old_x_end = _old_x_range(_BASE_X, _TEX)
    old_y_start, old_y_end = _old_y_range(_BASE_Y, _TEX)

    assert x_start >= old_x_start, "new x_start is before old x_start (adds tiles)"
    assert x_end <= old_x_end, "new x_end is after old x_end (adds tiles)"
    assert y_start >= old_y_start, "new y_start is before old y_start (adds tiles)"
    assert y_end <= old_y_end, "new y_end is after old y_end (adds tiles)"


def test_symmetry_x_equals_y_for_equal_inputs() -> None:
    """x and y ranges must be identical when given the same base/tex/viewport values."""
    base = 300.0
    tex = 32.0
    vp = 800.0
    (x_start, x_end), (y_start, y_end) = compute_background_tile_ranges(
        base, base, tex, tex, vp, vp, repeat_x=True, repeat_y=True
    )
    assert (x_start, x_end) == (y_start, y_end), (
        f"asymmetric: x=({x_start},{x_end}), y=({y_start},{y_end})"
    )
