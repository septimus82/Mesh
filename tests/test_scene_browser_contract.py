from __future__ import annotations

from types import SimpleNamespace

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController
from engine.scene_index import SceneListing, SceneRow, build_scene_rows
from tests._typing import as_any


def _build_controller(monkeypatch) -> EditorModeController:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    scene_controller = SimpleNamespace(_loaded_scene_data={}, current_scene_path="")
    window = SimpleNamespace(strict_mode=False, scene_controller=scene_controller, width=800, height=600)
    controller = EditorModeController(as_any(window))
    controller.active = True
    return controller


def test_scene_browser_filtering_stable(monkeypatch) -> None:
    listings = [
        SceneListing(path="packs/core/scenes/beta.json", display_name="Beta"),
        SceneListing(path="packs/core/scenes/alpha.json", display_name="Alpha"),
        SceneListing(path="packs/core/scenes/alpine.json", display_name="Alpine"),
    ]
    monkeypatch.setattr("engine.scene_index.list_pack_scene_listings", lambda *a, **k: listings)

    rows = build_scene_rows("al", [])
    assert [row.scene_id for row in rows] == [
        "packs/core/scenes/alpha.json",
        "packs/core/scenes/alpine.json",
    ]


def test_scene_browser_recents_pinned_order_stable(monkeypatch) -> None:
    listings = [
        SceneListing(path="packs/core/scenes/beta.json", display_name="Beta"),
        SceneListing(path="packs/core/scenes/alpha.json", display_name="Alpha"),
        SceneListing(path="packs/core/scenes/alpine.json", display_name="Alpine"),
    ]
    monkeypatch.setattr("engine.scene_index.list_pack_scene_listings", lambda *a, **k: listings)

    rows = build_scene_rows("", ["packs/core/scenes/alpine.json", "packs/core/scenes/beta.json"])
    assert [row.scene_id for row in rows] == [
        "packs/core/scenes/alpine.json",
        "packs/core/scenes/beta.json",
        "packs/core/scenes/alpha.json",
    ]
    assert rows[0].is_recent is True
    assert rows[1].is_recent is True
    assert rows[2].is_recent is False


def test_scene_browser_open_uses_same_path_as_switcher(monkeypatch) -> None:
    controller = _build_controller(monkeypatch)

    calls: list[str] = []

    def _record(scene_id: str) -> bool:
        calls.append(scene_id)
        return True

    as_any(controller)._open_scene_by_id = _record

    controller._scene_switcher_cached = [("packs/core/scenes/alpha.json", "Alpha")]
    controller.scene_switcher_index = 0
    controller._scene_switcher_open_selected()

    controller._scene_browser_cached_rows = [
        SceneRow(
            scene_id="packs/core/scenes/alpha.json",
            display_name="Alpha",
            pack_name="core",
            is_recent=False,
        )
    ]
    controller.scene_browser_index = 0
    controller._scene_browser_open_selected()

    assert calls == ["packs/core/scenes/alpha.json", "packs/core/scenes/alpha.json"]
