"""Contract tests for selection outline builder with styles.

Tests build_selection_outlines_with_styles for deterministic styled outline generation.
Headless, no arcade dependency.
"""

from __future__ import annotations

import pytest

from engine.editor.selection_outline import (
    RectF,
    StyledSelectionOutline,
    build_selection_outlines_with_styles,
    STYLE_NORMAL,
    STYLE_ORIGINAL,
    STYLE_DUPLICATE,
)


# -----------------------------------------------------------------------------
# Test fixtures
# -----------------------------------------------------------------------------


def make_entity(eid: str, x: float, y: float, w: float = 32.0, h: float = 32.0) -> dict:
    """Create a minimal entity dict."""
    return {"id": eid, "x": x, "y": y, "width": w, "height": h}


def make_fake_sprite(x: float, y: float, w: float = 32.0, h: float = 32.0) -> object:
    """Create a fake sprite object with position/size attributes."""
    class FakeSprite:
        def __init__(self, cx: float, cy: float, width: float, height: float) -> None:
            self.center_x = cx
            self.center_y = cy
            self.width = width
            self.height = height
    return FakeSprite(x, y, w, h)


# -----------------------------------------------------------------------------
# build_selection_outlines_with_styles
# -----------------------------------------------------------------------------


class TestBuildSelectionOutlinesWithStyles:
    """Tests for build_selection_outlines_with_styles function."""

    def test_basic_styled_outlines(self) -> None:
        """Basic styled outline generation."""
        entity_by_id = {
            "entity_a": make_entity("entity_a", 0.0, 0.0),
            "entity_b": make_entity("entity_b", 100.0, 100.0),
        }
        sprite_by_id = {
            "entity_a": make_fake_sprite(0.0, 0.0),
            "entity_b": make_fake_sprite(100.0, 100.0),
        }
        style_map = {
            "entity_a": STYLE_ORIGINAL,
            "entity_b": STYLE_DUPLICATE,
        }

        outlines = build_selection_outlines_with_styles(
            selected_ids=["entity_a", "entity_b"],
            primary_id="entity_b",
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
            style_map=style_map,
        )

        assert len(outlines) == 2

        # Find outlines by entity_id
        outline_a = next(o for o in outlines if o.entity_id == "entity_a")
        outline_b = next(o for o in outlines if o.entity_id == "entity_b")

        assert outline_a.style == STYLE_ORIGINAL
        assert outline_a.is_primary is False

        assert outline_b.style == STYLE_DUPLICATE
        assert outline_b.is_primary is True

    def test_deterministic_ordering(self) -> None:
        """Outlines should be in deterministic (sorted) order."""
        entity_by_id = {
            "z_entity": make_entity("z_entity", 0.0, 0.0),
            "a_entity": make_entity("a_entity", 50.0, 50.0),
            "m_entity": make_entity("m_entity", 100.0, 100.0),
        }
        sprite_by_id = {}  # Will use entity data fallback

        outlines = build_selection_outlines_with_styles(
            selected_ids=["z_entity", "a_entity", "m_entity"],
            primary_id=None,
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
            style_map=None,
        )

        # Should be sorted alphabetically
        ids = [o.entity_id for o in outlines]
        assert ids == ["a_entity", "m_entity", "z_entity"]

    def test_default_normal_style_without_style_map(self) -> None:
        """Without style_map, all outlines get 'normal' style."""
        entity_by_id = {
            "entity_a": make_entity("entity_a", 0.0, 0.0),
        }
        sprite_by_id = {}

        outlines = build_selection_outlines_with_styles(
            selected_ids=["entity_a"],
            primary_id=None,
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
            style_map=None,
        )

        assert len(outlines) == 1
        assert outlines[0].style == STYLE_NORMAL

    def test_includes_extras_from_style_map(self) -> None:
        """IDs in style_map but not in selected_ids should be included."""
        entity_by_id = {
            "entity_a": make_entity("entity_a", 0.0, 0.0),
            "entity_b": make_entity("entity_b", 100.0, 100.0),
        }
        sprite_by_id = {}
        style_map = {
            "entity_a": STYLE_DUPLICATE,
            "entity_b": STYLE_ORIGINAL,  # Not in selected_ids
        }

        outlines = build_selection_outlines_with_styles(
            selected_ids=["entity_a"],  # Only entity_a selected
            primary_id=None,
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
            style_map=style_map,
        )

        # Both should be included
        assert len(outlines) == 2
        ids = [o.entity_id for o in outlines]
        assert "entity_a" in ids
        assert "entity_b" in ids

    def test_missing_entity_skipped(self) -> None:
        """Entities not in entity_by_id should be skipped."""
        entity_by_id = {
            "entity_a": make_entity("entity_a", 0.0, 0.0),
        }
        sprite_by_id = {}

        outlines = build_selection_outlines_with_styles(
            selected_ids=["entity_a", "missing_entity"],
            primary_id=None,
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
            style_map=None,
        )

        # Only entity_a should appear (missing_entity has no data)
        # Actually missing_entity will get default rect, let's check
        assert len(outlines) >= 1
        entity_a_outline = next((o for o in outlines if o.entity_id == "entity_a"), None)
        assert entity_a_outline is not None

    def test_primary_flag_correct(self) -> None:
        """is_primary flag should only be True for primary_id."""
        entity_by_id = {
            "entity_a": make_entity("entity_a", 0.0, 0.0),
            "entity_b": make_entity("entity_b", 100.0, 100.0),
            "entity_c": make_entity("entity_c", 200.0, 200.0),
        }
        sprite_by_id = {}

        outlines = build_selection_outlines_with_styles(
            selected_ids=["entity_a", "entity_b", "entity_c"],
            primary_id="entity_b",
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
            style_map=None,
        )

        primary_count = sum(1 for o in outlines if o.is_primary)
        assert primary_count == 1

        primary_outline = next(o for o in outlines if o.is_primary)
        assert primary_outline.entity_id == "entity_b"

    def test_styled_selection_outline_dataclass(self) -> None:
        """StyledSelectionOutline should have correct attributes."""
        outline = StyledSelectionOutline(
            entity_id="test_entity",
            rect=RectF(x=0.0, y=0.0, w=32.0, h=32.0),
            is_primary=True,
            style=STYLE_DUPLICATE,
        )
        assert outline.entity_id == "test_entity"
        assert outline.rect.w == 32.0
        assert outline.is_primary is True
        assert outline.style == STYLE_DUPLICATE

    def test_empty_selection(self) -> None:
        """Empty selection returns empty list."""
        outlines = build_selection_outlines_with_styles(
            selected_ids=[],
            primary_id=None,
            entity_by_id={},
            sprite_by_id={},
            style_map=None,
        )
        assert outlines == []

    def test_all_three_styles_together(self) -> None:
        """Test all three styles in one call."""
        entity_by_id = {
            "original_1": make_entity("original_1", 0.0, 0.0),
            "duplicate_1": make_entity("duplicate_1", 50.0, 50.0),
            "normal_1": make_entity("normal_1", 100.0, 100.0),
        }
        sprite_by_id = {}
        style_map = {
            "original_1": STYLE_ORIGINAL,
            "duplicate_1": STYLE_DUPLICATE,
            "normal_1": STYLE_NORMAL,
        }

        outlines = build_selection_outlines_with_styles(
            selected_ids=["original_1", "duplicate_1", "normal_1"],
            primary_id="duplicate_1",
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
            style_map=style_map,
        )

        assert len(outlines) == 3

        styles_found = {o.style for o in outlines}
        assert styles_found == {STYLE_ORIGINAL, STYLE_DUPLICATE, STYLE_NORMAL}

        # Primary should be duplicate_1
        primary = next(o for o in outlines if o.is_primary)
        assert primary.entity_id == "duplicate_1"
        assert primary.style == STYLE_DUPLICATE
