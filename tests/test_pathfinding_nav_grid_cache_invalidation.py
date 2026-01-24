from __future__ import annotations


def test_nav_grid_cache_invalidates_on_revision_change_and_explicit_invalidate() -> None:
    from engine.pathfinding import NavGridCache

    cache: NavGridCache[object] = NavGridCache()

    created: list[object] = []

    def _build() -> object:
        value = object()
        created.append(value)
        return value

    v1 = cache.get_or_build(scene_path="scenes/a.json", revision=1, build=_build)
    v2 = cache.get_or_build(scene_path="scenes/a.json", revision=1, build=_build)
    assert v1 is v2

    v3 = cache.get_or_build(scene_path="scenes/a.json", revision=2, build=_build)
    assert v3 is not v1

    cache.invalidate()
    v4 = cache.get_or_build(scene_path="scenes/a.json", revision=2, build=_build)
    assert v4 is not v3
    assert len(created) == 3

