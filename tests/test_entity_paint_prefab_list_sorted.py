from __future__ import annotations


def test_entity_paint_prefab_list_sorted_and_filter_cycles() -> None:
    from engine.entity_paint_mode import (
        FILTER_ORDER,
        EntityPaintState,
        PrefabInfo,
        cycle_filter_mode,
        get_available_filters,
        load_prefab_infos,
    )

    prefabs = load_prefab_infos()
    ids = [p.prefab_id for p in prefabs]
    assert ids == sorted(ids), "prefab list must be sorted alphabetically"
    assert "player" not in ids

    # -- available filters follow FILTER_ORDER, "other" always last ----------
    available = get_available_filters(prefabs)
    assert available[0] == "all"
    core = [f for f in available if f != "other"]
    order_idx = {f: i for i, f in enumerate(FILTER_ORDER)}
    assert all(f in order_idx for f in core), "core filters must come from FILTER_ORDER"
    assert core == sorted(core, key=lambda f: order_idx[f]), "core filters must keep FILTER_ORDER ordering"
    if "other" in available:
        assert available[-1] == "other"

    # -- full forward cycle wraps back to "all" ------------------------------
    state = EntityPaintState(enabled=True, prefabs=prefabs, filter_mode="all", selected_index=0)
    visited: list[str] = []
    for _ in range(len(available)):
        cycle_filter_mode(state, direction=1)
        visited.append(state.filter_mode)
    # After cycling through all entries we must be back at "all"
    assert visited[-1] == "all"
    assert ["all"] + visited == available + ["all"]

    # -- backward cycle is the reverse --------------------------------------
    state.filter_mode = "all"
    rev: list[str] = []
    for _ in range(len(available)):
        cycle_filter_mode(state, direction=-1)
        rev.append(state.filter_mode)
    assert rev[-1] == "all"
    assert rev == list(reversed(available[1:])) + ["all"]

    # -- adding unknown tags does NOT change core order ----------------------
    extra = prefabs + (PrefabInfo(prefab_id="zzz_alien", tags=("alien_tag",)),)
    available2 = get_available_filters(extra)
    core2 = [f for f in available2 if f != "other"]
    assert core2 == core, "new tags must not reorder core filters"
    assert "other" in available2, "unknown tag must populate 'other'"
    assert available2[-1] == "other"

