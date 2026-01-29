from __future__ import annotations

from engine.editor_prefab_variant_ops import (
    apply_override_delta,
    clear_all_overrides,
    compute_prefab_override_diff,
    revert_override_key,
)


def test_compute_prefab_override_diff_deterministic() -> None:
    base = {"scale": 1.0, "name": "Base"}
    effective = {"scale": 1.2, "name": "Base"}
    overrides = {"scale": 1.2, "name": "Base"}

    rows = compute_prefab_override_diff(base, effective, overrides)
    assert [row.key for row in rows] == ["name", "scale"]

    scale_row = rows[1]
    assert scale_row.base_value == 1.0
    assert scale_row.override_value == 1.2
    assert scale_row.effective_value == 1.2


def test_apply_override_delta_is_immutable() -> None:
    entity = {"id": "e1", "prefab_overrides": {"scale": 1.0}}
    result = apply_override_delta(entity, "scale", 1.2)

    assert result is not entity
    assert entity["prefab_overrides"]["scale"] == 1.0
    assert result["prefab_overrides"]["scale"] == 1.2


def test_revert_override_key_removes_entry() -> None:
    entity = {"prefab_overrides": {"scale": 1.2, "tag": "npc"}}
    result = revert_override_key(entity, "scale")

    assert result is not entity
    assert "scale" in entity["prefab_overrides"]
    assert "scale" not in result["prefab_overrides"]


def test_clear_all_overrides_removes_block() -> None:
    entity = {"prefab_overrides": {"scale": 1.2}}
    result = clear_all_overrides(entity)

    assert result is not entity
    assert "prefab_overrides" in entity
    assert "prefab_overrides" not in result
