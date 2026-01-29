"""Contract tests for asset_rename_model.

Verifies:
- compute_rename_paths determinism
- find_scene_asset_references determinism and ordering
- compute_reference_replacements correctness
- apply_reference_replacements immutability and determinism
- format_rename_undo_label stability
"""

from __future__ import annotations

import copy

import pytest


class TestComputeRenamePaths:
    """Tests for compute_rename_paths."""

    def test_simple_rename_same_folder(self) -> None:
        from engine.editor.asset_rename_model import compute_rename_paths

        old, new = compute_rename_paths("assets/sprites/hero.png", "player.png")
        assert old == "assets/sprites/hero.png"
        assert new == "assets/sprites/player.png"

    def test_rename_in_root(self) -> None:
        from engine.editor.asset_rename_model import compute_rename_paths

        old, new = compute_rename_paths("config.json", "settings.json")
        assert old == "config.json"
        assert new == "settings.json"

    def test_normalizes_backslashes(self) -> None:
        from engine.editor.asset_rename_model import compute_rename_paths

        old, new = compute_rename_paths("assets\\sprites\\hero.png", "player.png")
        assert old == "assets/sprites/hero.png"
        assert new == "assets/sprites/player.png"

    def test_empty_old_path_returns_empty_new(self) -> None:
        from engine.editor.asset_rename_model import compute_rename_paths

        old, new = compute_rename_paths("", "player.png")
        assert old == ""
        assert new == ""

    def test_empty_new_name_returns_empty_new(self) -> None:
        from engine.editor.asset_rename_model import compute_rename_paths

        old, new = compute_rename_paths("assets/hero.png", "")
        assert old == "assets/hero.png"
        assert new == ""

    def test_strips_whitespace(self) -> None:
        from engine.editor.asset_rename_model import compute_rename_paths

        old, new = compute_rename_paths("  assets/hero.png  ", "  player.png  ")
        assert old == "assets/hero.png"
        assert new == "assets/player.png"

    def test_deterministic_across_calls(self) -> None:
        from engine.editor.asset_rename_model import compute_rename_paths

        expected = None
        for _ in range(10):
            result = compute_rename_paths("assets/sprites/hero.png", "player.png")
            if expected is None:
                expected = result
            else:
                assert result == expected


class TestFindSceneAssetReferences:
    """Tests for find_scene_asset_references."""

    def test_empty_payload_returns_empty(self) -> None:
        from engine.editor.asset_rename_model import find_scene_asset_references

        assert find_scene_asset_references(None) == []
        assert find_scene_asset_references({}) == []
        assert find_scene_asset_references({"entities": []}) == []

    def test_finds_sprite_field(self) -> None:
        from engine.editor.asset_rename_model import find_scene_asset_references

        scene = {
            "entities": [
                {"id": "hero", "sprite": "assets/hero.png"},
            ],
        }
        refs = find_scene_asset_references(scene)
        assert len(refs) == 1
        assert refs[0].entity_id == "hero"
        assert refs[0].field_path == "sprite"
        assert refs[0].value == "assets/hero.png"

    def test_finds_nested_sprite_sheet_image(self) -> None:
        from engine.editor.asset_rename_model import find_scene_asset_references

        scene = {
            "entities": [
                {
                    "id": "player",
                    "sprite_sheet": {"image": "assets/player_sheet.png", "frames": 4},
                },
            ],
        }
        refs = find_scene_asset_references(scene)
        assert len(refs) == 1
        assert refs[0].entity_id == "player"
        assert refs[0].field_path == "sprite_sheet.image"
        assert refs[0].value == "assets/player_sheet.png"

    def test_sorted_by_entity_id(self) -> None:
        from engine.editor.asset_rename_model import find_scene_asset_references

        scene = {
            "entities": [
                {"id": "zebra", "sprite": "z.png"},
                {"id": "alpha", "sprite": "a.png"},
                {"id": "middle", "sprite": "m.png"},
            ],
        }
        refs = find_scene_asset_references(scene)
        entity_ids = [r.entity_id for r in refs]
        assert entity_ids == ["alpha", "middle", "zebra"]

    def test_multiple_fields_same_entity(self) -> None:
        from engine.editor.asset_rename_model import find_scene_asset_references

        scene = {
            "entities": [
                {
                    "id": "hero",
                    "sprite": "hero.png",
                    "texture": "hero_tex.png",
                },
            ],
        }
        refs = find_scene_asset_references(scene)
        assert len(refs) == 2
        field_paths = [r.field_path for r in refs]
        assert "sprite" in field_paths
        assert "texture" in field_paths

    def test_normalizes_paths(self) -> None:
        from engine.editor.asset_rename_model import find_scene_asset_references

        scene = {
            "entities": [
                {"id": "hero", "sprite": "assets\\hero.png"},
            ],
        }
        refs = find_scene_asset_references(scene)
        assert refs[0].value == "assets/hero.png"

    def test_ignores_empty_values(self) -> None:
        from engine.editor.asset_rename_model import find_scene_asset_references

        scene = {
            "entities": [
                {"id": "hero", "sprite": "", "texture": "   "},
            ],
        }
        refs = find_scene_asset_references(scene)
        assert len(refs) == 0

    def test_deterministic_across_calls(self) -> None:
        from engine.editor.asset_rename_model import find_scene_asset_references

        scene = {
            "entities": [
                {"id": "c", "sprite": "c.png"},
                {"id": "a", "sprite": "a.png"},
                {"id": "b", "sprite": "b.png"},
            ],
        }
        expected = None
        for _ in range(10):
            result = find_scene_asset_references(scene)
            if expected is None:
                expected = result
            else:
                assert result == expected


class TestComputeReferenceReplacements:
    """Tests for compute_reference_replacements."""

    def test_no_matches_returns_empty(self) -> None:
        from engine.editor.asset_rename_model import compute_reference_replacements

        scene = {
            "entities": [
                {"id": "hero", "sprite": "other.png"},
            ],
        }
        replacements = compute_reference_replacements(scene, "hero.png", "player.png")
        assert replacements == []

    def test_finds_matching_references(self) -> None:
        from engine.editor.asset_rename_model import compute_reference_replacements

        scene = {
            "entities": [
                {"id": "hero", "sprite": "assets/hero.png"},
                {"id": "enemy", "sprite": "assets/enemy.png"},
            ],
        }
        replacements = compute_reference_replacements(
            scene, "assets/hero.png", "assets/player.png"
        )
        assert len(replacements) == 1
        assert replacements[0].entity_id == "hero"
        assert replacements[0].old_value == "assets/hero.png"
        assert replacements[0].new_value == "assets/player.png"

    def test_finds_multiple_references(self) -> None:
        from engine.editor.asset_rename_model import compute_reference_replacements

        scene = {
            "entities": [
                {"id": "hero1", "sprite": "shared.png"},
                {"id": "hero2", "sprite": "shared.png"},
            ],
        }
        replacements = compute_reference_replacements(scene, "shared.png", "new.png")
        assert len(replacements) == 2

    def test_empty_paths_returns_empty(self) -> None:
        from engine.editor.asset_rename_model import compute_reference_replacements

        scene = {"entities": [{"id": "hero", "sprite": "hero.png"}]}
        assert compute_reference_replacements(scene, "", "new.png") == []
        assert compute_reference_replacements(scene, "hero.png", "") == []

    def test_same_paths_returns_empty(self) -> None:
        from engine.editor.asset_rename_model import compute_reference_replacements

        scene = {"entities": [{"id": "hero", "sprite": "hero.png"}]}
        assert compute_reference_replacements(scene, "hero.png", "hero.png") == []


class TestApplyReferenceReplacements:
    """Tests for apply_reference_replacements."""

    def test_empty_replacements_returns_copy(self) -> None:
        from engine.editor.asset_rename_model import apply_reference_replacements

        scene = {"entities": [{"id": "hero", "sprite": "hero.png"}]}
        result = apply_reference_replacements(scene, [])
        assert result == scene
        assert result is not scene  # Should be a copy

    def test_applies_top_level_replacement(self) -> None:
        from engine.editor.asset_rename_model import (
            Replacement,
            apply_reference_replacements,
        )

        scene = {"entities": [{"id": "hero", "sprite": "hero.png"}]}
        replacements = [
            Replacement("hero", "sprite", "hero.png", "player.png"),
        ]
        result = apply_reference_replacements(scene, replacements)
        assert result["entities"][0]["sprite"] == "player.png"

    def test_applies_nested_replacement(self) -> None:
        from engine.editor.asset_rename_model import (
            Replacement,
            apply_reference_replacements,
        )

        scene = {
            "entities": [
                {"id": "hero", "sprite_sheet": {"image": "hero.png", "frames": 4}},
            ],
        }
        replacements = [
            Replacement("hero", "sprite_sheet.image", "hero.png", "player.png"),
        ]
        result = apply_reference_replacements(scene, replacements)
        assert result["entities"][0]["sprite_sheet"]["image"] == "player.png"
        assert result["entities"][0]["sprite_sheet"]["frames"] == 4

    def test_does_not_mutate_original(self) -> None:
        from engine.editor.asset_rename_model import (
            Replacement,
            apply_reference_replacements,
        )

        scene = {"entities": [{"id": "hero", "sprite": "hero.png"}]}
        original = copy.deepcopy(scene)
        replacements = [
            Replacement("hero", "sprite", "hero.png", "player.png"),
        ]
        apply_reference_replacements(scene, replacements)
        assert scene == original  # Original unchanged

    def test_handles_missing_entity(self) -> None:
        from engine.editor.asset_rename_model import (
            Replacement,
            apply_reference_replacements,
        )

        scene = {"entities": [{"id": "hero", "sprite": "hero.png"}]}
        replacements = [
            Replacement("nonexistent", "sprite", "hero.png", "player.png"),
        ]
        result = apply_reference_replacements(scene, replacements)
        # Should not crash, entity unchanged
        assert result["entities"][0]["sprite"] == "hero.png"

    def test_deterministic_across_calls(self) -> None:
        from engine.editor.asset_rename_model import (
            Replacement,
            apply_reference_replacements,
        )

        scene = {
            "entities": [
                {"id": "a", "sprite": "shared.png"},
                {"id": "b", "sprite": "shared.png"},
            ],
        }
        replacements = [
            Replacement("a", "sprite", "shared.png", "new.png"),
            Replacement("b", "sprite", "shared.png", "new.png"),
        ]
        expected = None
        for _ in range(10):
            result = apply_reference_replacements(scene, replacements)
            if expected is None:
                expected = result
            else:
                assert result == expected


class TestFormatRenameUndoLabel:
    """Tests for format_rename_undo_label."""

    def test_zero_refs(self) -> None:
        from engine.editor.asset_rename_model import format_rename_undo_label

        label = format_rename_undo_label("assets/hero.png", "assets/player.png", 0)
        assert label == "Rename hero.png → player.png"

    def test_one_ref(self) -> None:
        from engine.editor.asset_rename_model import format_rename_undo_label

        label = format_rename_undo_label("assets/hero.png", "assets/player.png", 1)
        assert label == "Rename hero.png → player.png (1 ref)"

    def test_multiple_refs(self) -> None:
        from engine.editor.asset_rename_model import format_rename_undo_label

        label = format_rename_undo_label("assets/hero.png", "assets/player.png", 5)
        assert label == "Rename hero.png → player.png (5 refs)"

    def test_root_level_files(self) -> None:
        from engine.editor.asset_rename_model import format_rename_undo_label

        label = format_rename_undo_label("config.json", "settings.json", 0)
        assert label == "Rename config.json → settings.json"

    def test_deterministic(self) -> None:
        from engine.editor.asset_rename_model import format_rename_undo_label

        expected = None
        for _ in range(10):
            result = format_rename_undo_label("a.png", "b.png", 3)
            if expected is None:
                expected = result
            else:
                assert result == expected


class TestIntegrationWorkflow:
    """Integration tests for the full rename workflow."""

    def test_full_rename_workflow(self) -> None:
        from engine.editor.asset_rename_model import (
            apply_reference_replacements,
            compute_reference_replacements,
            compute_rename_paths,
            format_rename_undo_label,
        )

        # Initial scene with references to hero.png
        scene = {
            "entities": [
                {"id": "player", "sprite": "assets/sprites/hero.png"},
                {"id": "clone", "sprite": "assets/sprites/hero.png"},
                {"id": "enemy", "sprite": "assets/sprites/goblin.png"},
            ],
        }

        # Compute paths for rename
        old_rel, new_rel = compute_rename_paths(
            "assets/sprites/hero.png", "player.png"
        )
        assert old_rel == "assets/sprites/hero.png"
        assert new_rel == "assets/sprites/player.png"

        # Compute replacements
        replacements = compute_reference_replacements(scene, old_rel, new_rel)
        assert len(replacements) == 2  # player and clone

        # Apply replacements
        new_scene = apply_reference_replacements(scene, replacements)

        # Verify changes
        assert new_scene["entities"][0]["sprite"] == "assets/sprites/player.png"
        assert new_scene["entities"][1]["sprite"] == "assets/sprites/player.png"
        assert new_scene["entities"][2]["sprite"] == "assets/sprites/goblin.png"

        # Format undo label
        label = format_rename_undo_label(old_rel, new_rel, len(replacements))
        assert label == "Rename hero.png → player.png (2 refs)"

        # Original scene unchanged
        assert scene["entities"][0]["sprite"] == "assets/sprites/hero.png"
