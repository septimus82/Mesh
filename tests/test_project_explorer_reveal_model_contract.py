"""Contract tests for project_explorer_reveal_model.

Verifies:
- choose_reveal_target priority and determinism
- compute_reveal_scroll_index boundaries and centering
- normalize_repo_relative_path stability
- format_copy_path_text correctness
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tests._typing import as_any


class TestNormalizeRepoRelativePath:
    """Tests for normalize_repo_relative_path."""

    def test_empty_string_returns_empty(self) -> None:
        from engine.editor.project_explorer_reveal_model import normalize_repo_relative_path

        assert normalize_repo_relative_path("") == ""

    def test_none_returns_empty(self) -> None:
        from engine.editor.project_explorer_reveal_model import normalize_repo_relative_path

        assert normalize_repo_relative_path(None) == ""

    def test_whitespace_only_returns_empty(self) -> None:
        from engine.editor.project_explorer_reveal_model import normalize_repo_relative_path

        assert normalize_repo_relative_path("   ") == ""

    def test_strips_whitespace(self) -> None:
        from engine.editor.project_explorer_reveal_model import normalize_repo_relative_path

        assert normalize_repo_relative_path("  path/to/file.py  ") == "path/to/file.py"

    def test_converts_backslashes_to_forward(self) -> None:
        from engine.editor.project_explorer_reveal_model import normalize_repo_relative_path

        assert normalize_repo_relative_path("path\\to\\file.py") == "path/to/file.py"
        assert normalize_repo_relative_path("path\\to/mixed\\file.py") == "path/to/mixed/file.py"

    def test_strips_leading_trailing_slashes(self) -> None:
        from engine.editor.project_explorer_reveal_model import normalize_repo_relative_path

        assert normalize_repo_relative_path("/path/to/file.py") == "path/to/file.py"
        assert normalize_repo_relative_path("path/to/file.py/") == "path/to/file.py"
        assert normalize_repo_relative_path("/path/to/file.py/") == "path/to/file.py"

    def test_deterministic_repeated_calls(self) -> None:
        from engine.editor.project_explorer_reveal_model import normalize_repo_relative_path

        for _ in range(10):
            assert normalize_repo_relative_path("  /path\\to/file.py/  ") == "path/to/file.py"


class TestChooseRevealTarget:
    """Tests for choose_reveal_target deterministic priority."""

    def test_returns_none_when_both_empty(self) -> None:
        from engine.editor.project_explorer_reveal_model import choose_reveal_target

        assert choose_reveal_target(None, None) is None
        assert choose_reveal_target("", "") is None
        assert choose_reveal_target("   ", "   ") is None

    def test_scene_path_takes_priority(self) -> None:
        from engine.editor.project_explorer_reveal_model import choose_reveal_target

        result = choose_reveal_target("scenes/demo.json", "assets/sprite.png")
        assert result == "scenes/demo.json"

    def test_falls_back_to_asset_when_no_scene(self) -> None:
        from engine.editor.project_explorer_reveal_model import choose_reveal_target

        result = choose_reveal_target(None, "assets/sprite.png")
        assert result == "assets/sprite.png"

        result = choose_reveal_target("", "assets/sprite.png")
        assert result == "assets/sprite.png"

    def test_normalizes_paths(self) -> None:
        from engine.editor.project_explorer_reveal_model import choose_reveal_target

        result = choose_reveal_target("scenes\\demo.json", None)
        assert result == "scenes/demo.json"

        result = choose_reveal_target(None, "  /assets\\sprite.png/  ")
        assert result == "assets/sprite.png"

    def test_deterministic_across_repeated_calls(self) -> None:
        from engine.editor.project_explorer_reveal_model import choose_reveal_target

        expected = None
        for _ in range(10):
            result = choose_reveal_target("scenes/demo.json", "assets/sprite.png")
            if expected is None:
                expected = result
            else:
                assert result == expected


class TestFindRowIndexForPath:
    """Tests for find_row_index_for_path."""

    def test_returns_none_for_empty_target(self) -> None:
        from engine.editor.project_explorer_reveal_model import find_row_index_for_path

        rows = ["a.py", "b.py"]
        assert find_row_index_for_path(rows, "", lambda x: x) is None
        assert find_row_index_for_path(rows, as_any(None), lambda x: x) is None

    def test_returns_none_for_empty_rows(self) -> None:
        from engine.editor.project_explorer_reveal_model import find_row_index_for_path

        assert find_row_index_for_path([], "target.py", lambda x: x) is None

    def test_finds_exact_match(self) -> None:
        from engine.editor.project_explorer_reveal_model import find_row_index_for_path

        rows = ["path/a.py", "path/b.py", "path/c.py"]
        assert find_row_index_for_path(rows, "path/b.py", lambda x: x) == 1

    def test_normalizes_both_paths(self) -> None:
        from engine.editor.project_explorer_reveal_model import find_row_index_for_path

        rows = ["path/to/file.py"]
        # Backslash target should match forward slash row
        assert find_row_index_for_path(rows, "path\\to\\file.py", lambda x: x) == 0

    def test_returns_first_match(self) -> None:
        from engine.editor.project_explorer_reveal_model import find_row_index_for_path

        rows = ["a.py", "target.py", "b.py", "target.py"]
        assert find_row_index_for_path(rows, "target.py", lambda x: x) == 1

    def test_custom_get_path_fn(self) -> None:
        from engine.editor.project_explorer_reveal_model import find_row_index_for_path

        @dataclass
        class Row:
            rel_path: str

        rows = [Row("a.py"), Row("b.py"), Row("c.py")]
        assert find_row_index_for_path(rows, "b.py", lambda r: r.rel_path) == 1


class TestComputeRevealScrollIndex:
    """Tests for compute_reveal_scroll_index centering and boundaries."""

    def test_returns_none_for_missing_target(self) -> None:
        from engine.editor.project_explorer_reveal_model import compute_reveal_scroll_index

        rows = ["a.py", "b.py"]
        row_idx, scroll_start = compute_reveal_scroll_index(rows, "missing.py", lambda x: x, 5)
        assert row_idx is None
        assert scroll_start == 0

    def test_returns_row_index_when_found(self) -> None:
        from engine.editor.project_explorer_reveal_model import compute_reveal_scroll_index

        rows = ["a.py", "b.py", "c.py"]
        row_idx, _ = compute_reveal_scroll_index(rows, "b.py", lambda x: x, 5)
        assert row_idx == 1

    def test_centers_target_in_viewport(self) -> None:
        from engine.editor.project_explorer_reveal_model import compute_reveal_scroll_index

        # 10 rows, viewport shows 4, target at index 5
        rows = [f"row_{i}.py" for i in range(10)]
        row_idx, scroll_start = compute_reveal_scroll_index(rows, "row_5.py", lambda x: x, 4)
        assert row_idx == 5
        # Center of 4-row viewport means scroll to idx 5 - 2 = 3
        assert scroll_start == 3

    def test_clamps_scroll_start_at_zero(self) -> None:
        from engine.editor.project_explorer_reveal_model import compute_reveal_scroll_index

        # Target near start, shouldn't scroll to negative
        rows = [f"row_{i}.py" for i in range(10)]
        row_idx, scroll_start = compute_reveal_scroll_index(rows, "row_0.py", lambda x: x, 6)
        assert row_idx == 0
        assert scroll_start == 0

    def test_clamps_scroll_start_at_max(self) -> None:
        from engine.editor.project_explorer_reveal_model import compute_reveal_scroll_index

        # Target near end, shouldn't scroll past content
        rows = [f"row_{i}.py" for i in range(10)]
        row_idx, scroll_start = compute_reveal_scroll_index(rows, "row_9.py", lambda x: x, 4)
        assert row_idx == 9
        # Max start = 10 - 4 = 6
        assert scroll_start == 6

    def test_handles_small_list(self) -> None:
        from engine.editor.project_explorer_reveal_model import compute_reveal_scroll_index

        # Fewer rows than viewport
        rows = ["a.py", "b.py"]
        row_idx, scroll_start = compute_reveal_scroll_index(rows, "b.py", lambda x: x, 10)
        assert row_idx == 1
        assert scroll_start == 0  # Can't scroll when everything fits

    def test_deterministic_across_repeated_calls(self) -> None:
        from engine.editor.project_explorer_reveal_model import compute_reveal_scroll_index

        rows = [f"row_{i}.py" for i in range(20)]
        expected = None
        for _ in range(10):
            result = compute_reveal_scroll_index(rows, "row_10.py", lambda x: x, 5)
            if expected is None:
                expected = result
            else:
                assert result == expected


class TestFormatCopyPathText:
    """Tests for format_copy_path_text."""

    def test_empty_returns_empty(self) -> None:
        from engine.editor.project_explorer_reveal_model import format_copy_path_text

        assert format_copy_path_text("") == ""
        assert format_copy_path_text(None) == ""

    def test_normalizes_path(self) -> None:
        from engine.editor.project_explorer_reveal_model import format_copy_path_text

        assert format_copy_path_text("path\\to\\file.py") == "path/to/file.py"
        assert format_copy_path_text("  /path/to/file/  ") == "path/to/file"

    def test_returns_repo_relative(self) -> None:
        from engine.editor.project_explorer_reveal_model import format_copy_path_text

        assert format_copy_path_text("scenes/demo.json") == "scenes/demo.json"
        assert format_copy_path_text("assets/sprites/hero.png") == "assets/sprites/hero.png"


class TestIntegrationWithProjectRow:
    """Integration tests with ProjectRow-like structures."""

    def test_reveal_workflow(self) -> None:
        from engine.editor.project_explorer_reveal_model import (
            choose_reveal_target,
            compute_reveal_scroll_index,
        )

        @dataclass
        class ProjectRow:
            rel_path: str
            name: str

        # Simulate having rows in project explorer
        rows = [
            ProjectRow("assets", "assets"),
            ProjectRow("assets/sprites", "sprites"),
            ProjectRow("assets/sprites/hero.png", "hero.png"),
            ProjectRow("scenes", "scenes"),
            ProjectRow("scenes/demo.json", "demo.json"),
        ]

        # Choose target based on current scene
        target = choose_reveal_target("scenes/demo.json", "assets/sprites/hero.png")
        assert target == "scenes/demo.json"

        # Find row and compute scroll
        row_idx, scroll_start = compute_reveal_scroll_index(
            rows, target, lambda r: r.rel_path, 3
        )
        assert row_idx == 4  # scenes/demo.json is at index 4
        # Centered: 4 - 1 = 3, but clamped to max_start = 5 - 3 = 2
        assert scroll_start == 2

    def test_copy_path_workflow(self) -> None:
        from engine.editor.project_explorer_reveal_model import format_copy_path_text

        @dataclass
        class ProjectRow:
            rel_path: str
            name: str

        row = ProjectRow("assets/sprites/hero.png", "hero.png")
        copied = format_copy_path_text(row.rel_path)
        assert copied == "assets/sprites/hero.png"
