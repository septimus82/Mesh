
"""
Matrix contract tests for Safe Refactor Ops (V2).
Covers path mapping, reference scanning, and replacement logic under various conditions.
"""
import pytest
from typing import List, Dict, Any

from engine.editor.asset_refactor_model import (
    normalize_repo_rel,
    compute_move_mapping,
    scan_scene_references,
    compute_replacements,
    apply_replacements,
    AssetReference,
    Replacement
)

# -- Path Mapping Matrix --

@pytest.mark.parametrize("old_path,new_path,expected_mapping", [
    ("a.png", "b.png", {"a.png": "b.png"}),
    ("dir/a.png", "dir/b.png", {"dir/a.png": "dir/b.png"}),
    ("dir\\a.png", "dir/b.png", {"dir/a.png": "dir/b.png"}), # Mixed separators
    ("/dir/a.png", "dir/b.png", {"dir/a.png": "dir/b.png"}), # Leading slash
    ("src", "dst", {"src": "dst"}), # Folder move intent
])
def test_path_mapping_matrix(old_path, new_path, expected_mapping):
    assert compute_move_mapping(old_path, new_path) == expected_mapping

# -- Reference Scanning Matrix --

SCAN_MATRIX_CASES = [
    (
        # 1. Simple Entity
        {"entities": [{"id": "e1", "sprite": "assets/hero.png"}]},
        [("e1", "sprite", "assets/hero.png")]
    ),
    (
        # 2. Nested Field
        {"entities": [{"id": "e2", "sprite_sheet": {"image": "assets/sheet.png"}}]},
        [("e2", "sprite_sheet.image", "assets/sheet.png")]
    ),
    (
        # 3. Multiple Entities & Fields
        {
            "entities": [
                {"id": "e3", "sound": "sfx/jump.wav"},
                {"id": "e4", "light": {"texture": "tex/glow.png"}}
            ]
        },
        [
            ("e3", "sound", "sfx/jump.wav"),
            ("e4", "light.texture", "tex/glow.png")
        ]
    ),
    (
        # 4. No References
        {"entities": [{"id": "e5", "name": "Just metadata"}]},
        []
    )
]

@pytest.mark.parametrize("payload,expected_refs", SCAN_MATRIX_CASES)
def test_scan_references_matrix(payload, expected_refs: List[tuple]):
    refs = scan_scene_references(payload)
    # Convert AssetReference to tuple for easier comparison
    ref_tuples = [(r.entity_id, r.field_path, r.value) for r in refs]
    # Sort for determinism
    ref_tuples.sort()
    sorted_expected = sorted(expected_refs)
    assert ref_tuples == sorted_expected


# -- Replacement Matrix --

REPLACEMENT_MATRIX_CASES = [
    # Case: File Move (Exact Match)
    (
        {"assets/old.png": "assets/new.png"},
        [AssetReference("e1", "sprite", "assets/old.png", "k1")],
        [("e1", "sprite", "assets/new.png")]
    ),
    # Case: File Move (No Match)
    (
        {"assets/old.png": "assets/new.png"},
        [AssetReference("e1", "sprite", "assets/other.png", "k1")],
        []
    ),
    # Case: Folder Move (Prefix Match)
    (
        {"assets/chars": "assets/legacy"},
        [
            AssetReference("e1", "sprite", "assets/chars/hero.png", "k1"),
            AssetReference("e2", "sound", "assets/chars/sfx/jump.wav", "k2"),
            AssetReference("e3", "image", "assets/other/ui.png", "k3")
        ],
        [
            ("e1", "sprite", "assets/legacy/hero.png"),
            ("e2", "sound", "assets/legacy/sfx/jump.wav")
        ]
    ),
    # Case: Folder Move (Prefix Match - False Positive Check)
    (
        {"assets/ch": "assets/ch2"},
        [AssetReference("e1", "sprite", "assets/chars/hero.png", "k1")],
        # Should NOT match because 'chars' does not start with 'ch/'
        # Assuming asset_refactor_model handles directory separator check
        []
    )
]

@pytest.mark.parametrize("mapping,refs,expected_replacements_tuples", REPLACEMENT_MATRIX_CASES)
def test_compute_replacements_matrix(mapping, refs, expected_replacements_tuples):
    reps = compute_replacements(refs, mapping)
    result_tuples = [(r.entity_id, r.field_path, r.new_value) for r in reps]
    assert sorted(result_tuples) == sorted(expected_replacements_tuples)


def test_apply_replacements():
    """Verify application of changes returns correct deep copy."""
    original = {"entities": [{"id": "e1", "sprite": "old.png"}]}
    reps = [Replacement("e1", "sprite", "old.png", "new.png", "k")]
    
    new_scene = apply_replacements(original, reps)
    
    # Check modification
    assert new_scene["entities"][0]["sprite"] == "new.png"
    # Check original unmodified
    assert original["entities"][0]["sprite"] == "old.png"
