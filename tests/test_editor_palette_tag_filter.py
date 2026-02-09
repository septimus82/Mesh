from __future__ import annotations

from engine.editor.prefab_palette_panel import filter_prefab_palette_items as _filter_prefab_palette_items


def test_palette_tag_filter_syntax_and_matching() -> None:
    prefabs = [
        {"id": "p_barrel", "display_name": "Barrel", "tags": ["scenery", "prop"]},
        {"id": "p_tree", "display_name": "Tree", "tags": ["scenery"]},
        {"id": "p_sword", "display_name": "Sword", "tags": ["weapon"]},
        {"id": "p_blank", "display_name": "Blank"},
    ]

    out = _filter_prefab_palette_items(prefabs, "#scenery")
    assert [p["id"] for p in out] == ["p_barrel", "p_tree"]

    out = _filter_prefab_palette_items(prefabs, "#sce")
    assert [p["id"] for p in out] == ["p_barrel", "p_tree"]

    out = _filter_prefab_palette_items(prefabs, "bar #scenery")
    assert [p["id"] for p in out] == ["p_barrel"]

    out = _filter_prefab_palette_items(prefabs, "#scenery #prop")
    assert [p["id"] for p in out] == ["p_barrel"]

    out = _filter_prefab_palette_items(prefabs, "t:weapon")
    assert [p["id"] for p in out] == ["p_sword"]

    out = _filter_prefab_palette_items(prefabs, "#missing")
    assert out == []
