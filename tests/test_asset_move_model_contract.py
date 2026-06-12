"""Contract tests for asset_move_model.

Verifies:
- compute_move_paths determinism and correctness
- validate_destination logic
- format_move_undo_label correctness
"""

from __future__ import annotations


class TestComputeMovePaths:
    """Tests for compute_move_paths."""

    def test_move_to_subfolder(self) -> None:
        from engine.editor.asset_move_model import compute_move_paths

        old, new = compute_move_paths("assets/hero.png", "assets/sprites")
        assert old == "assets/hero.png"
        assert new == "assets/sprites/hero.png"

    def test_move_to_root(self) -> None:
        from engine.editor.asset_move_model import compute_move_paths

        old, new = compute_move_paths("assets/hero.png", "")
        assert old == "assets/hero.png"
        assert new == "hero.png"

    def test_normalizes_slashes(self) -> None:
        from engine.editor.asset_move_model import compute_move_paths

        old, new = compute_move_paths("assets\\hero.png", "assets\\sprites")
        assert old == "assets/hero.png"
        assert new == "assets/sprites/hero.png"

    def test_empty_source(self) -> None:
        from engine.editor.asset_move_model import compute_move_paths

        old, new = compute_move_paths("", "assets")
        assert old == ""
        assert new == ""

    def test_deterministic(self) -> None:
        from engine.editor.asset_move_model import compute_move_paths

        expected = None
        for _ in range(10):
            result = compute_move_paths("a/b.png", "c")
            if expected is None:
                expected = result
            else:
                assert result == expected

class TestValidateDestination:
    """Tests for validate_destination."""

    def test_valid_move(self) -> None:
        from engine.editor.asset_move_model import validate_destination

        valid, _ = validate_destination("assets/hero.png", "assets/sprites")
        assert valid is True

    def test_same_folder_invalid(self) -> None:
        from engine.editor.asset_move_model import validate_destination

        valid, reason = validate_destination("assets/sprites/hero.png", "assets/sprites")
        assert valid is False
        assert "Same as source" in reason or "same as source" in reason.lower()

    def test_same_folder_root(self) -> None:
        from engine.editor.asset_move_model import validate_destination

        valid, reason = validate_destination("config.json", "")
        assert valid is False

    def test_empty_source(self) -> None:
        from engine.editor.asset_move_model import validate_destination

        valid, _ = validate_destination("", "assets")
        assert valid is False

class TestFormatMoveUndoLabel:
    """Tests for format_move_undo_label."""

    def test_simple_move(self) -> None:
        from engine.editor.asset_move_model import format_move_undo_label

        label = format_move_undo_label("assets/hero.png", "assets/new/hero.png", 0)
        assert label == "Move hero.png → assets/new/hero.png"

    def test_move_with_refs(self) -> None:
        from engine.editor.asset_move_model import format_move_undo_label

        label = format_move_undo_label("assets/hero.png", "assets/new/hero.png", 3)
        assert "3 refs" in label
