"""Contract tests for project_explorer_rank_model.

Verifies:
- normalize_query determinism
- compute_match_score scoring rules (exact > prefix > substring)
- rank_rows deterministic ordering with tie-breakers
- Stability across repeated calls
"""

from __future__ import annotations

from tests._typing import as_any


class TestNormalizeQuery:
    """Tests for normalize_query determinism."""

    def test_empty_string_returns_empty(self) -> None:
        from engine.editor.project_explorer_rank_model import normalize_query

        assert normalize_query("") == ""

    def test_none_returns_empty(self) -> None:
        from engine.editor.project_explorer_rank_model import normalize_query

        assert normalize_query(as_any(None)) == ""

    def test_whitespace_only_returns_empty(self) -> None:
        from engine.editor.project_explorer_rank_model import normalize_query

        assert normalize_query("   ") == ""
        assert normalize_query("\t\n") == ""

    def test_strips_whitespace(self) -> None:
        from engine.editor.project_explorer_rank_model import normalize_query

        assert normalize_query("  test  ") == "test"

    def test_lowercases_text(self) -> None:
        from engine.editor.project_explorer_rank_model import normalize_query

        assert normalize_query("TEST") == "test"
        assert normalize_query("TeSt") == "test"

    def test_deterministic_repeated_calls(self) -> None:
        from engine.editor.project_explorer_rank_model import normalize_query

        for _ in range(10):
            assert normalize_query("  MiXeD CaSe  ") == "mixed case"


class TestComputeMatchScore:
    """Tests for compute_match_score scoring rules."""

    def test_empty_query_returns_no_match(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_NO_MATCH,
            compute_match_score,
        )

        assert compute_match_score("some_file.py", "") == SCORE_NO_MATCH

    def test_empty_text_returns_no_match(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_NO_MATCH,
            compute_match_score,
        )

        assert compute_match_score("", "query") == SCORE_NO_MATCH

    def test_exact_filename_match_highest_score(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_EXACT,
            compute_match_score,
        )

        assert compute_match_score("path/to/config.json", "config.json") == SCORE_EXACT
        assert compute_match_score("config.json", "config.json") == SCORE_EXACT

    def test_exact_match_case_insensitive(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_EXACT,
            compute_match_score,
        )

        assert compute_match_score("Config.JSON", "config.json") == SCORE_EXACT

    def test_prefix_match_second_highest(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_PREFIX,
            compute_match_score,
        )

        assert compute_match_score("path/config_test.py", "config") == SCORE_PREFIX
        assert compute_match_score("config_test.py", "config") == SCORE_PREFIX

    def test_word_boundary_match_medium_score(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_WORD_BOUNDARY,
            compute_match_score,
        )

        # After underscore
        assert compute_match_score("my_config.py", "config") == SCORE_WORD_BOUNDARY
        # After hyphen
        assert compute_match_score("my-config.py", "config") == SCORE_WORD_BOUNDARY
        # After dot
        assert compute_match_score("my.config.py", "config") == SCORE_WORD_BOUNDARY
        # After path separator (but filename doesn't start with query)
        assert compute_match_score("path/my_config.py", "config") == SCORE_WORD_BOUNDARY

    def test_substring_match_lower_score(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_SUBSTRING,
            compute_match_score,
        )

        # Middle of word, no boundary
        assert compute_match_score("preconfigurations.py", "config") == SCORE_SUBSTRING

    def test_no_match_returns_negative(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_NO_MATCH,
            compute_match_score,
        )

        assert compute_match_score("something.py", "xyz") == SCORE_NO_MATCH

    def test_score_ordering_exact_highest(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_EXACT,
            SCORE_NO_MATCH,
            SCORE_PREFIX,
            SCORE_SUBSTRING,
            SCORE_WORD_BOUNDARY,
        )

        assert SCORE_EXACT > SCORE_PREFIX > SCORE_WORD_BOUNDARY > SCORE_SUBSTRING > SCORE_NO_MATCH


class TestRankRows:
    """Tests for rank_rows deterministic sorting."""

    def test_empty_query_preserves_order(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        rows = ["c.py", "a.py", "b.py"]
        result = rank_rows(rows, "", lambda x: x)
        assert result == ["c.py", "a.py", "b.py"]

    def test_whitespace_query_preserves_order(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        rows = ["c.py", "a.py", "b.py"]
        result = rank_rows(rows, "   ", lambda x: x)
        assert result == ["c.py", "a.py", "b.py"]

    def test_exact_match_ranked_first(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        rows = ["preconfig.py", "config.py", "my_config.py"]
        result = rank_rows(rows, "config.py", lambda x: x)
        assert result[0] == "config.py"

    def test_prefix_ranked_before_substring(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        rows = ["preconfig.py", "config_test.py"]
        result = rank_rows(rows, "config", lambda x: x)
        assert result[0] == "config_test.py"  # Prefix match
        assert result[1] == "preconfig.py"  # Substring match

    def test_word_boundary_ranked_before_plain_substring(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        rows = ["preconfig.py", "my_config.py"]
        result = rank_rows(rows, "config", lambda x: x)
        assert result[0] == "my_config.py"  # Word boundary match
        assert result[1] == "preconfig.py"  # Substring match

    def test_tie_breaker_shorter_path_first(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        # Both are prefix matches, so tie-break by length
        rows = ["config_longer.py", "config.py"]
        result = rank_rows(rows, "config", lambda x: x)
        assert result[0] == "config.py"  # Shorter
        assert result[1] == "config_longer.py"

    def test_tie_breaker_lexicographic_when_same_length(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        # Both prefix matches, same length -> lexicographic
        rows = ["configz.py", "configa.py"]
        result = rank_rows(rows, "config", lambda x: x)
        assert result[0] == "configa.py"  # 'a' < 'z'
        assert result[1] == "configz.py"

    def test_non_matching_rows_excluded(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        rows = ["config.py", "other.py", "test.py"]
        result = rank_rows(rows, "config", lambda x: x)
        assert result == ["config.py"]

    def test_deterministic_across_repeated_calls(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        rows = ["z_config.py", "config.py", "a_config.py", "preconfig.py"]
        expected = None
        for _ in range(10):
            result = rank_rows(rows, "config", lambda x: x)
            if expected is None:
                expected = result
            else:
                assert result == expected, "Ranking should be deterministic"

    def test_custom_get_text_fn(self) -> None:
        from dataclasses import dataclass

        from engine.editor.project_explorer_rank_model import rank_rows

        @dataclass
        class Row:
            path: str
            name: str

        rows = [
            Row("a/preconfig.py", "preconfig.py"),
            Row("b/config.py", "config.py"),
        ]
        result = rank_rows(rows, "config.py", lambda r: r.path)
        assert result[0].name == "config.py"

    def test_returns_new_list(self) -> None:
        from engine.editor.project_explorer_rank_model import rank_rows

        rows = ["config.py", "test.py"]
        result = rank_rows(rows, "config", lambda x: x)
        rows.append("new.py")
        assert "new.py" not in result


class TestScoreOrdering:
    """Tests to verify score constant ordering is correct."""

    def test_all_scores_distinct(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_EXACT,
            SCORE_NO_MATCH,
            SCORE_PREFIX,
            SCORE_SUBSTRING,
            SCORE_WORD_BOUNDARY,
        )

        scores = [SCORE_EXACT, SCORE_PREFIX, SCORE_WORD_BOUNDARY, SCORE_SUBSTRING, SCORE_NO_MATCH]
        assert len(scores) == len(set(scores)), "All scores should be distinct"

    def test_descending_order(self) -> None:
        from engine.editor.project_explorer_rank_model import (
            SCORE_EXACT,
            SCORE_NO_MATCH,
            SCORE_PREFIX,
            SCORE_SUBSTRING,
            SCORE_WORD_BOUNDARY,
        )

        scores = [SCORE_EXACT, SCORE_PREFIX, SCORE_WORD_BOUNDARY, SCORE_SUBSTRING, SCORE_NO_MATCH]
        assert scores == sorted(scores, reverse=True), "Scores should be in descending order"


class TestIntegrationWithProjectRow:
    """Tests using actual ProjectRow-like structures."""

    def test_rank_project_rows_by_rel_path(self) -> None:
        from dataclasses import dataclass

        from engine.editor.project_explorer_rank_model import rank_rows

        @dataclass
        class ProjectRow:
            rel_path: str
            name: str
            depth: int
            is_dir: bool

        rows = [
            ProjectRow("scenes/preconfig.json", "preconfig.json", 1, False),
            ProjectRow("scenes/config.json", "config.json", 1, False),
            ProjectRow("assets/my_config.png", "my_config.png", 1, False),
        ]

        result = rank_rows(rows, "config", lambda r: r.rel_path)

        # Exact filename match first, then prefix, then word boundary
        assert result[0].rel_path == "scenes/config.json"  # Prefix on filename
        assert result[1].rel_path == "assets/my_config.png"  # Word boundary
        assert result[2].rel_path == "scenes/preconfig.json"  # Substring
