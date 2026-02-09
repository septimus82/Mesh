import pytest
from engine.editor.asset_refactor_preview_model import (
    group_modifications_by_file,
    flatten_examples,
    format_refactor_preview
)
from engine.editor.asset_refactor_model import Replacement

def test_group_modifications_by_file_deterministic():
    mods = {
        "b.json": [Replacement("e1", "p", "a", "b", 0)],
        "a.json": [Replacement("e2", "p", "a", "b", 0), Replacement("e3", "p", "a", "b", 0)],
        "c.json": []
    }
    
    groups = group_modifications_by_file(mods)
    
    assert len(groups) == 3
    assert groups[0] == ("a.json", 2)
    assert groups[1] == ("b.json", 1)
    assert groups[2] == ("c.json", 0)

def test_flatten_examples_deterministic():
    mods = {
        "x.json": [
            Replacement("e1", "f1", "path/old", "path/new", 0),
            Replacement("e2", "f2", "path/old", "path/new", 0)
        ]
    }
    
    examples = flatten_examples(mods, limit=5)
    assert len(examples) == 2
    # Replacements are sorted by entity_id/field_path inside flatten_examples if we implemented sorting properly
    assert examples[0] == "path/old -> path/new"

def test_truncation():
    long_path = "a" * 100
    mods = {
        "x.json": [Replacement("e1", "f1", long_path, "short", 0)]
    }
    examples = flatten_examples(mods)
    assert "..." in examples[0]

def test_format_refactor_preview():
    mods = {"scene.json": [Replacement("e1", "sprite", "assets/old", "assets/new", 0)]}
    lines = format_refactor_preview("Title", "rename", "Rename A -> B", mods)
    
    assert "Operation: RENAME" in lines
    assert "Rename A -> B" in lines
    assert "Updating References: 1 changes in 1 files." in lines
    assert "  • scene.json: 1" in lines
    assert "Reference Examples:" in lines
    assert "  > assets/old -> assets/new" in lines
