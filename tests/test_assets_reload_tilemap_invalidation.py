from __future__ import annotations

from engine.assets_reload import reload_render_assets


class _StubSceneController:
    def __init__(self) -> None:
        self.calls = 0

    def invalidate_tilemap_batches(self) -> int:
        self.calls += 1
        return 4


class _StubWindow:
    def __init__(self) -> None:
        self.scene_controller = _StubSceneController()


def test_assets_reload_tilemap_invalidation() -> None:
    window = _StubWindow()
    counts = reload_render_assets(window)
    assert counts["tilemap_batches_invalidated"] == 4
    assert window.scene_controller.calls == 1
