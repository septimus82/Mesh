"""Contract tests for project_explorer_perf_model.

Verifies:
- compute_filter_key determinism and stability
- slice_visible_rows correct windowing and overscan
- estimate_total_height correctness
"""

from __future__ import annotations


class TestComputeFilterKey:
    """Tests for compute_filter_key determinism."""

    def test_empty_inputs_produce_stable_key(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        key1 = compute_filter_key("", None, 0)
        key2 = compute_filter_key("", None, 0)
        assert key1 == key2
        assert len(key1) == 16  # MD5 truncated to 16 hex chars

    def test_same_inputs_produce_same_key(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        key1 = compute_filter_key("test", {"a", "b", "c"}, 42)
        key2 = compute_filter_key("test", {"a", "b", "c"}, 42)
        assert key1 == key2

    def test_expanded_ids_order_independent(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        # Different orderings should produce same key (sorted internally)
        key1 = compute_filter_key("query", {"z", "a", "m"}, 1)
        key2 = compute_filter_key("query", {"a", "m", "z"}, 1)
        key3 = compute_filter_key("query", ["m", "z", "a"], 1)
        assert key1 == key2 == key3

    def test_query_normalized_to_lowercase(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        key1 = compute_filter_key("TEST", None, 0)
        key2 = compute_filter_key("test", None, 0)
        key3 = compute_filter_key("TeSt", None, 0)
        assert key1 == key2 == key3

    def test_query_whitespace_trimmed(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        key1 = compute_filter_key("  test  ", None, 0)
        key2 = compute_filter_key("test", None, 0)
        assert key1 == key2

    def test_different_queries_produce_different_keys(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        key1 = compute_filter_key("alpha", None, 0)
        key2 = compute_filter_key("beta", None, 0)
        assert key1 != key2

    def test_different_tree_revs_produce_different_keys(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        key1 = compute_filter_key("test", None, 1)
        key2 = compute_filter_key("test", None, 2)
        assert key1 != key2

    def test_different_expanded_ids_produce_different_keys(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        key1 = compute_filter_key("test", {"a", "b"}, 0)
        key2 = compute_filter_key("test", {"a", "c"}, 0)
        assert key1 != key2

    def test_none_vs_empty_expanded_ids_same(self) -> None:
        from engine.editor.project_explorer_perf_model import compute_filter_key

        key1 = compute_filter_key("test", None, 0)
        key2 = compute_filter_key("test", [], 0)
        key3 = compute_filter_key("test", set(), 0)
        assert key1 == key2 == key3


class TestSliceVisibleRows:
    """Tests for slice_visible_rows viewport slicing."""

    def test_empty_rows_returns_empty_slice(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        result = slice_visible_rows([], 0.0, 100.0, 20.0)
        assert result.start == 0
        assert result.end == 0
        assert result.rows == []

    def test_zero_row_height_returns_empty(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        result = slice_visible_rows(["a", "b", "c"], 0.0, 100.0, 0.0)
        assert result.rows == []

    def test_zero_viewport_returns_empty(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        result = slice_visible_rows(["a", "b", "c"], 0.0, 0.0, 20.0)
        assert result.rows == []

    def test_no_scroll_shows_top_rows_with_overscan(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        # 10 rows, viewport shows 5, overscan=2
        rows = list(range(10))
        result = slice_visible_rows(rows, 0.0, 100.0, 20.0, overscan=2)

        # First visible = 0, visible_count = 5+1=6, overscan=2
        # start = max(0, 0-2) = 0
        # end = min(10, 0+6+2) = 8
        assert result.start == 0
        assert result.end == 8
        assert result.rows == [0, 1, 2, 3, 4, 5, 6, 7]

    def test_scrolled_down_shows_middle_rows(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        # 20 rows, scrolled to row 5, viewport shows 5 rows
        rows = list(range(20))
        result = slice_visible_rows(rows, 100.0, 100.0, 20.0, overscan=2)

        # First visible = 100/20 = 5, visible_count = 6
        # start = max(0, 5-2) = 3
        # end = min(20, 5+6+2) = 13
        assert result.start == 3
        assert result.end == 13
        assert result.rows == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    def test_scrolled_to_bottom_clamps_end(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        # 10 rows, scrolled past end
        rows = list(range(10))
        result = slice_visible_rows(rows, 200.0, 100.0, 20.0, overscan=2)

        # First visible = 200/20 = 10, visible_count = 6
        # start = max(0, 10-2) = 8
        # end = min(10, 10+6+2) = 10
        assert result.start == 8
        assert result.end == 10
        assert result.rows == [8, 9]

    def test_default_overscan_is_3(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        rows = list(range(20))
        result = slice_visible_rows(rows, 100.0, 100.0, 20.0)

        # First visible = 5, visible_count = 6, overscan=3 (default)
        # start = max(0, 5-3) = 2
        # end = min(20, 5+6+3) = 14
        assert result.start == 2
        assert result.end == 14

    def test_small_list_returns_all(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        rows = ["a", "b", "c"]
        result = slice_visible_rows(rows, 0.0, 1000.0, 20.0, overscan=5)

        assert result.start == 0
        assert result.end == 3
        assert result.rows == ["a", "b", "c"]

    def test_returns_new_list_not_slice(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        rows = [1, 2, 3, 4, 5]
        result = slice_visible_rows(rows, 0.0, 100.0, 20.0, overscan=0)

        # Modify original
        rows[0] = 999
        # Result should not be affected (it's a copy)
        assert result.rows[0] == 1


class TestEstimateTotalHeight:
    """Tests for estimate_total_height."""

    def test_zero_rows_returns_zero(self) -> None:
        from engine.editor.project_explorer_perf_model import estimate_total_height

        assert estimate_total_height(0, 20.0) == 0.0

    def test_negative_rows_returns_zero(self) -> None:
        from engine.editor.project_explorer_perf_model import estimate_total_height

        assert estimate_total_height(-5, 20.0) == 0.0

    def test_zero_row_height_returns_zero(self) -> None:
        from engine.editor.project_explorer_perf_model import estimate_total_height

        assert estimate_total_height(10, 0.0) == 0.0

    def test_negative_row_height_returns_zero(self) -> None:
        from engine.editor.project_explorer_perf_model import estimate_total_height

        assert estimate_total_height(10, -5.0) == 0.0

    def test_correct_calculation(self) -> None:
        from engine.editor.project_explorer_perf_model import estimate_total_height

        assert estimate_total_height(10, 20.0) == 200.0
        assert estimate_total_height(100, 18.0) == 1800.0
        assert estimate_total_height(1, 50.0) == 50.0

    def test_returns_float(self) -> None:
        from engine.editor.project_explorer_perf_model import estimate_total_height

        result = estimate_total_height(10, 20)
        assert isinstance(result, float)


class TestSliceResultTuple:
    """Tests for SliceResult tuple behavior."""

    def test_tuple_unpacking(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        rows = list(range(10))
        start, end, visible = slice_visible_rows(rows, 0.0, 60.0, 20.0, overscan=1)

        assert isinstance(start, int)
        assert isinstance(end, int)
        assert isinstance(visible, list)

    def test_named_properties(self) -> None:
        from engine.editor.project_explorer_perf_model import slice_visible_rows

        rows = list(range(10))
        result = slice_visible_rows(rows, 0.0, 60.0, 20.0, overscan=1)

        assert result.start == result[0]
        assert result.end == result[1]
        assert result.rows == result[2]
