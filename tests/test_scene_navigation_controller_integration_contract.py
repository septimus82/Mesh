from __future__ import annotations

from types import SimpleNamespace

from engine.scene_navigation_controller import SceneNavigationController


def test_nav_controller_cache_rebuild_on_revision_change() -> None:
    controller = SceneNavigationController()
    calls: list[tuple[str | None, int]] = []

    def _build(_tilemap: object) -> object:
        calls.append((scene_path, revision))
        return SimpleNamespace(tag=f"grid:{scene_path}:{revision}")

    tilemap = object()

    scene_path = "scenes/a.json"
    revision = 1
    grid1 = controller.get_nav_grid(scene_path=scene_path, revision=revision, tilemap_instance=tilemap, build_fn=_build)
    grid2 = controller.get_nav_grid(scene_path=scene_path, revision=revision, tilemap_instance=tilemap, build_fn=_build)
    assert grid1 is grid2
    assert len(calls) == 1

    revision = 2
    grid3 = controller.get_nav_grid(scene_path=scene_path, revision=revision, tilemap_instance=tilemap, build_fn=_build)
    assert grid3 is not grid1
    assert len(calls) == 2


def test_nav_controller_cache_rebuild_on_scene_change() -> None:
    controller = SceneNavigationController()
    calls: list[tuple[str | None, int]] = []

    def _build(_tilemap: object) -> object:
        calls.append((scene_path, revision))
        return SimpleNamespace(tag=f"grid:{scene_path}:{revision}")

    tilemap = object()
    revision = 1

    scene_path = "scenes/a.json"
    controller.get_nav_grid(scene_path=scene_path, revision=revision, tilemap_instance=tilemap, build_fn=_build)

    scene_path = "scenes/b.json"
    controller.get_nav_grid(scene_path=scene_path, revision=revision, tilemap_instance=tilemap, build_fn=_build)

    assert calls == [("scenes/a.json", 1), ("scenes/b.json", 1)]


def test_nav_controller_invalidate_forces_rebuild() -> None:
    controller = SceneNavigationController()
    calls: list[int] = []

    def _build(_tilemap: object) -> object:
        calls.append(1)
        return object()

    tilemap = object()
    controller.get_nav_grid(scene_path="scenes/a.json", revision=1, tilemap_instance=tilemap, build_fn=_build)
    controller.invalidate()
    controller.get_nav_grid(scene_path="scenes/a.json", revision=1, tilemap_instance=tilemap, build_fn=_build)
    assert len(calls) == 2
