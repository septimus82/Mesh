"""
Contract tests for asset refactoring model (V2).
"""
from engine.editor.asset_refactor_model import (
    AssetReference,
    Replacement,
    apply_replacements,
    compute_move_mapping,
    compute_replacements,
    normalize_repo_rel,
    scan_prefab_references,
    scan_scene_references,
)


def test_normalize_repo_rel():
    assert normalize_repo_rel("foo\\bar") == "foo/bar"
    assert normalize_repo_rel("/foo/bar") == "foo/bar"
    assert normalize_repo_rel(" foo/bar ") == "foo/bar"
    assert normalize_repo_rel("") == ""

def test_compute_move_mapping_file():
    mapping = compute_move_mapping("assets/old.png", "assets/new.png")
    assert mapping == {"assets/old.png": "assets/new.png"}

def test_compute_move_mapping_folder():
    mapping = compute_move_mapping("assets/chars", "assets/heroes")
    assert mapping == {"assets/chars": "assets/heroes"}

def test_scan_scene_references():
    scene = {
        "entities": [
            {"id": "e1", "sprite": "assets/hero.png"},
            {"id": "e2", "sprite_sheet": {"image": "assets/sheet.png"}}
        ]
    }
    refs = scan_scene_references(scene)
    assert len(refs) == 2
    assert AssetReference("e1", "sprite", "assets/hero.png", "e1|sprite") in refs
    assert AssetReference("e2", "sprite_sheet.image", "assets/sheet.png", "e2|sprite_sheet.image") in refs

def test_scan_prefab_references():
    prefab = {"id": "p1", "sprite": "assets/tree.png"}
    refs = scan_prefab_references(prefab)
    assert len(refs) == 1
    assert refs[0].value == "assets/tree.png"

def test_compute_replacements_exact():
    refs = [AssetReference("e1", "sprite", "assets/hero.png", "k1")]
    mapping = {"assets/hero.png": "assets/hero_v2.png"}
    reps = compute_replacements(refs, mapping)
    assert len(reps) == 1
    assert reps[0].new_value == "assets/hero_v2.png"

def test_compute_replacements_folder_prefix():
    refs = [
        AssetReference("e1", "sprite", "assets/chars/hero.png", "k1"),
        AssetReference("e2", "sprite", "assets/chars/villain.png", "k2"),
        AssetReference("e3", "sprite", "assets/props/box.png", "k3")
    ]
    mapping = {"assets/chars": "assets/unit_v2"}
    reps = compute_replacements(refs, mapping)

    assert len(reps) == 2

    val_map = {r.old_value: r.new_value for r in reps}
    assert val_map["assets/chars/hero.png"] == "assets/unit_v2/hero.png"
    assert val_map["assets/chars/villain.png"] == "assets/unit_v2/villain.png"
    # box.png should not be touched

def test_apply_replacements_scene_immutability():
    scene = {
        "entities": [
            {"id": "e1", "sprite": "old.png"}
        ]
    }
    reps = [Replacement("e1", "sprite", "old.png", "new.png", "k1")]

    new_scene = apply_replacements(scene, reps)

    assert new_scene["entities"][0]["sprite"] == "new.png"
    assert scene["entities"][0]["sprite"] == "old.png" # Immutable

def test_apply_replacements_nested():
    prefab = {"id": "ROOT", "sprite_sheet": {"image": "old_sheet.png"}}
    reps = [Replacement("ROOT", "sprite_sheet.image", "old_sheet.png", "new_sheet.png", "k1")]

    new_prefab = apply_replacements(prefab, reps)
    assert new_prefab["sprite_sheet"]["image"] == "new_sheet.png"

