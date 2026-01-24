from __future__ import annotations

from engine.scene_runtime.index_build import build_scene_index_from_sprites


class _StubSprite:
    def __init__(
        self,
        *,
        mesh_name: str | None = None,
        entity_id: str | None = None,
        zone_id: str | None = None,
    ) -> None:
        self.mesh_name = mesh_name
        if entity_id is None and zone_id is None:
            self.mesh_entity_data = {}
        else:
            behaviour_config: dict = {}
            if zone_id is not None:
                behaviour_config["TriggerZone"] = {"zone_id": zone_id}
            self.mesh_entity_data = {"id": entity_id, "behaviour_config": behaviour_config}


def test_build_scene_index_preserves_first_wins_deterministically() -> None:
    first = _StubSprite(mesh_name="Thing", entity_id="A", zone_id="Z")
    second = _StubSprite(mesh_name="Thing", entity_id="A", zone_id="Z")

    idx = build_scene_index_from_sprites([first, second])

    assert idx.get_by_id("a") is first
    assert idx.get_by_zone_id("z") is first
    assert idx.get_first_by_mesh_name("thing") is first

