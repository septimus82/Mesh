from __future__ import annotations


def test_entity_paint_prefab_list_sorted_and_filter_cycles() -> None:
    from engine.entity_paint_mode import EntityPaintState, cycle_filter_mode, load_prefab_infos

    prefabs = load_prefab_infos()
    ids = [p.prefab_id for p in prefabs]
    assert ids == sorted(ids)
    assert "player" not in ids

    state = EntityPaintState(enabled=True, prefabs=prefabs, filter_mode="all", selected_index=0)
    cycle_filter_mode(state, direction=1)
    assert state.filter_mode == "enemy"

    # Next filters may not exist; cycling should fall back deterministically.
    cycle_filter_mode(state, direction=1)
    assert state.filter_mode in {"all", "enemy"}

