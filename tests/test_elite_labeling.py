from engine.elite_labeling import format_elite_label, is_boss_entity, is_elite_entity
from engine.prefabs import PrefabManager


def test_elite_variant_formats_spawn_label() -> None:
    pm = PrefabManager()
    wrapper = pm.resolve_with_variant("slime_blob", "elite")
    assert wrapper is not None

    # Simulate how a scene entity referencing a variant is represented before sprite creation.
    merged = dict(wrapper)
    merged.update(
        {
            "name": "EliteSlime",
            "x": 0,
            "y": 0,
            "prefab_id": "slime_blob",
            "variant_id": "elite",
        }
    )

    assert is_elite_entity(merged) is True
    assert "ELITE" in format_elite_label("EliteSlime", merged)


def test_base_prefab_does_not_format_spawn_label() -> None:
    pm = PrefabManager()
    resolved = pm.resolve({"name": "Slime", "x": 0, "y": 0, "prefab_id": "slime_blob"})

    assert is_elite_entity(resolved) is False
    assert "ELITE" not in format_elite_label("Slime", resolved)


def test_boss_takes_precedence_over_elite() -> None:
    payload = {"name": "Thing", "is_elite": True, "is_boss": True}
    assert is_boss_entity(payload) is True
    assert is_elite_entity(payload) is True
    assert format_elite_label("Thing", payload).endswith("[BOSS]")
