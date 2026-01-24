from __future__ import annotations

from engine.scene_runtime.spawn import resolve_spawn_target


class _StubSprite:
    def __init__(
        self,
        *,
        mesh_tag: str | None = None,
        mesh_name: str | None = None,
        mesh_entity_data: dict | None = None,
        center_x: float = 0.0,
        center_y: float = 0.0,
    ) -> None:
        self.mesh_tag = mesh_tag
        self.mesh_name = mesh_name
        self.mesh_entity_data = mesh_entity_data or {}
        self.center_x = center_x
        self.center_y = center_y


class _StubIndex:
    def __init__(
        self,
        *,
        id_match: object | None = None,
        zone_match: object | None = None,
        mesh_match: object | None = None,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self._id_match = id_match
        self._zone_match = zone_match
        self._mesh_match = mesh_match

    def get_by_id(self, value: str):
        self.calls.append(("id", value))
        return self._id_match

    def get_by_zone_id(self, value: str):
        self.calls.append(("zone_id", value))
        return self._zone_match

    def get_first_by_mesh_name(self, value: str):
        self.calls.append(("mesh_name", value))
        return self._mesh_match


def test_spawn_resolution_prefers_marker_over_index() -> None:
    marker = _StubSprite(mesh_tag="spawn_point", mesh_entity_data={"spawn_id": "SpawnA"})
    idx = _StubIndex(id_match=object(), zone_match=object(), mesh_match=object())

    res = resolve_spawn_target(
        " spawna ",
        all_sprites=[marker],
        scene_index=idx,  # type: ignore[arg-type]
        scene_data={},
    )

    assert res.resolved == "marker"
    assert res.marker is marker
    assert idx.calls == []


def test_spawn_resolution_order_id_then_zone_then_mesh() -> None:
    idx = _StubIndex(zone_match=object())

    res = resolve_spawn_target(
        "Zone42",
        all_sprites=[],
        scene_index=idx,  # type: ignore[arg-type]
        scene_data={},
    )

    assert res.resolved == "zone_id"
    assert res.marker is not None
    assert idx.calls == [("id", "Zone42"), ("zone_id", "Zone42")]


def test_spawn_resolution_mesh_after_id_and_zone() -> None:
    idx = _StubIndex(mesh_match=object())

    res = resolve_spawn_target(
        "MeshOnly",
        all_sprites=[],
        scene_index=idx,  # type: ignore[arg-type]
        scene_data={},
    )

    assert res.resolved == "mesh_name"
    assert res.marker is not None
    assert idx.calls == [("id", "MeshOnly"), ("zone_id", "MeshOnly"), ("mesh_name", "MeshOnly")]


def test_spawn_resolution_falls_back_to_spawns_dict() -> None:
    idx = _StubIndex()
    scene_data = {"spawns": {"Start": {"x": 1, "y": 2}, "default": {"x": 9, "y": 9}}}

    res = resolve_spawn_target(
        "Start",
        all_sprites=[],
        scene_index=idx,  # type: ignore[arg-type]
        scene_data=scene_data,
    )

    assert res.resolved == "spawns"
    assert res.marker is None
    assert res.spawn == {"x": 1, "y": 2}
    assert idx.calls == [("id", "Start"), ("zone_id", "Start"), ("mesh_name", "Start")]

