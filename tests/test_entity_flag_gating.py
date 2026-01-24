from __future__ import annotations


def test_entity_flag_gating_filters_entities() -> None:
    from engine.scene_entity_gating import filter_entities_by_flags

    entities = [
        {"id": "p", "tag": "player", "require_flags": ["demo.never"]},
        {"id": "b", "forbid_flags": ["demo.y"]},
        {"id": "a", "require_flags": ["demo.x"]},
    ]

    def get_flag(name: str, default: bool = False) -> bool:
        return {"demo.x": False, "demo.y": False}.get(name, default)

    ids = [e["id"] for e in filter_entities_by_flags(entities, get_flag=get_flag)]
    assert ids == ["p", "b"]

    def get_flag_x(name: str, default: bool = False) -> bool:
        return {"demo.x": True, "demo.y": False}.get(name, default)

    ids = [e["id"] for e in filter_entities_by_flags(entities, get_flag=get_flag_x)]
    assert ids == ["p", "b", "a"]

    def get_flag_y(name: str, default: bool = False) -> bool:
        return {"demo.x": False, "demo.y": True}.get(name, default)

    ids = [e["id"] for e in filter_entities_by_flags(entities, get_flag=get_flag_y)]
    assert ids == ["p"]


def test_entity_flag_gating_is_deterministic_order() -> None:
    from engine.scene_entity_gating import filter_entities_by_flags

    entities = [
        {"id": "p", "tag": "player"},
        {"id": "b", "forbid_flags": ["demo.y"]},
        {"id": "a", "require_flags": ["demo.x"]},
    ]

    def get_flag(name: str, default: bool = False) -> bool:
        return {"demo.x": True, "demo.y": True}.get(name, default)

    out1 = filter_entities_by_flags(entities, get_flag=get_flag)
    out2 = filter_entities_by_flags(entities, get_flag=get_flag)
    assert [e["id"] for e in out1] == ["p", "a"]
    assert [e["id"] for e in out2] == ["p", "a"]

