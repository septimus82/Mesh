"""Contract tests for resolve_validation_targets() in discovery.py.

These tests verify that validation path resolution is robust:
- "." resolves to worlds/main_world.json if it exists
- directory paths scan JSONs deterministically
- file paths return single target
- missing paths return []
"""

from __future__ import annotations

import pytest
from pathlib import Path

from engine.tooling_runtime.discovery import resolve_validation_targets

pytestmark = pytest.mark.fast


class TestResolveValidationTargetsDefault:
    """Test default "." / None / empty path resolution."""

    def test_dot_resolves_to_main_world_if_exists(self, tmp_path: Path) -> None:
        """'.' should resolve to worlds/main_world.json if it exists."""
        worlds_dir = tmp_path / "worlds"
        worlds_dir.mkdir()
        main_world = worlds_dir / "main_world.json"
        main_world.write_text('{"scenes": {}}')

        result = resolve_validation_targets(".", tmp_path)

        assert result == [main_world]

    def test_none_resolves_to_main_world_if_exists(self, tmp_path: Path) -> None:
        """None should resolve to worlds/main_world.json if it exists."""
        worlds_dir = tmp_path / "worlds"
        worlds_dir.mkdir()
        main_world = worlds_dir / "main_world.json"
        main_world.write_text('{"scenes": {}}')

        result = resolve_validation_targets(None, tmp_path)

        assert result == [main_world]

    def test_empty_string_resolves_to_main_world_if_exists(self, tmp_path: Path) -> None:
        """Empty string should resolve to worlds/main_world.json if it exists."""
        worlds_dir = tmp_path / "worlds"
        worlds_dir.mkdir()
        main_world = worlds_dir / "main_world.json"
        main_world.write_text('{"scenes": {}}')

        result = resolve_validation_targets("", tmp_path)

        assert result == [main_world]

    def test_dot_falls_back_to_worlds_scan_if_no_main_world(self, tmp_path: Path) -> None:
        """'.' should scan worlds/ if main_world.json doesn't exist."""
        worlds_dir = tmp_path / "worlds"
        worlds_dir.mkdir()
        (worlds_dir / "alpha.json").write_text("{}")
        (worlds_dir / "beta.json").write_text("{}")

        result = resolve_validation_targets(".", tmp_path)

        assert len(result) == 2
        assert result[0].name == "alpha.json"
        assert result[1].name == "beta.json"

    def test_dot_returns_empty_if_no_worlds_dir(self, tmp_path: Path) -> None:
        """'.' should return [] if worlds/ doesn't exist."""
        result = resolve_validation_targets(".", tmp_path)

        assert result == []


class TestResolveValidationTargetsDirectory:
    """Test directory path resolution."""

    def test_directory_scans_json_files_recursively(self, tmp_path: Path) -> None:
        """Directory should scan all JSON files recursively."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.json").write_text("{}")
        (subdir / "nested.json").write_text("{}")

        result = resolve_validation_targets(tmp_path, tmp_path)

        assert len(result) == 2
        names = [p.name for p in result]
        assert "root.json" in names
        assert "nested.json" in names

    def test_directory_scan_is_deterministic(self, tmp_path: Path) -> None:
        """Directory scan should return files in lexicographic order."""
        worlds_dir = tmp_path / "worlds"
        worlds_dir.mkdir()
        (worlds_dir / "zebra.json").write_text("{}")
        (worlds_dir / "alpha.json").write_text("{}")
        (worlds_dir / "mango.json").write_text("{}")

        result = resolve_validation_targets(worlds_dir, tmp_path)

        assert len(result) == 3
        assert result[0].name == "alpha.json"
        assert result[1].name == "mango.json"
        assert result[2].name == "zebra.json"

    def test_directory_ignores_non_json_files(self, tmp_path: Path) -> None:
        """Directory scan should only include .json files."""
        (tmp_path / "valid.json").write_text("{}")
        (tmp_path / "readme.txt").write_text("not json")
        (tmp_path / "script.py").write_text("# code")

        result = resolve_validation_targets(tmp_path, tmp_path)

        assert len(result) == 1
        assert result[0].name == "valid.json"


class TestResolveValidationTargetsFile:
    """Test file path resolution."""

    def test_file_path_returns_single_target(self, tmp_path: Path) -> None:
        """File path should return that single file."""
        world_file = tmp_path / "my_world.json"
        world_file.write_text('{"scenes": {}}')

        result = resolve_validation_targets(world_file, tmp_path)

        assert result == [world_file]

    def test_relative_file_path_resolved_against_repo_root(self, tmp_path: Path) -> None:
        """Relative file path should resolve against repo_root."""
        worlds_dir = tmp_path / "worlds"
        worlds_dir.mkdir()
        world_file = worlds_dir / "custom.json"
        world_file.write_text('{"scenes": {}}')

        result = resolve_validation_targets("worlds/custom.json", tmp_path)

        assert result == [world_file]

    def test_absolute_file_path_used_directly(self, tmp_path: Path) -> None:
        """Absolute file path should be used as-is."""
        world_file = tmp_path / "absolute_world.json"
        world_file.write_text('{"scenes": {}}')

        result = resolve_validation_targets(str(world_file), tmp_path)

        assert result == [world_file]


class TestResolveValidationTargetsMissing:
    """Test missing path handling."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Missing file path should return []."""
        result = resolve_validation_targets("nonexistent.json", tmp_path)

        assert result == []

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """Missing directory should return []."""
        result = resolve_validation_targets("nonexistent_dir", tmp_path)

        assert result == []


class TestResolveValidationTargetsEdgeCases:
    """Test edge cases and complex scenarios."""

    def test_whitespace_path_treated_as_default(self, tmp_path: Path) -> None:
        """Whitespace-only path should be treated as default."""
        worlds_dir = tmp_path / "worlds"
        worlds_dir.mkdir()
        main_world = worlds_dir / "main_world.json"
        main_world.write_text('{"scenes": {}}')

        result = resolve_validation_targets("   ", tmp_path)

        assert result == [main_world]

    def test_nested_json_files_found(self, tmp_path: Path) -> None:
        """Deeply nested JSON files should be found."""
        deep_dir = tmp_path / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)
        deep_file = deep_dir / "deep.json"
        deep_file.write_text("{}")

        result = resolve_validation_targets(tmp_path, tmp_path)

        assert len(result) == 1
        assert result[0] == deep_file

    def test_path_object_accepted(self, tmp_path: Path) -> None:
        """Path object should be accepted as input."""
        world_file = tmp_path / "world.json"
        world_file.write_text('{"scenes": {}}')

        result = resolve_validation_targets(Path(world_file), tmp_path)

        assert result == [world_file]

    def test_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        """Empty directory should return []."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = resolve_validation_targets(empty_dir, tmp_path)

        assert result == []
