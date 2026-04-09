from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import engine.editor_controller as editor_module
from engine.command_palette import filter_options
from engine.editor_controller import EditorModeController
from engine.scene_index import list_pack_scene_listings
from tests._typing import as_any


def _build_controller(monkeypatch, request_scene_change=None) -> EditorModeController:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    scene_controller = SimpleNamespace(current_scene_path="")
    window = SimpleNamespace(
        strict_mode=False,
        scene_controller=scene_controller,
        width=800,
        height=600,
    )
    if request_scene_change is not None:
        window.request_scene_change = request_scene_change
    controller = EditorModeController(as_any(window))
    controller.active = True
    return controller


def test_scene_switcher_filtering_top_match(tmp_path: Path) -> None:
    packs_root = tmp_path / "packs"
    scene_a = packs_root / "core_regions" / "scenes" / "alpha_outpost.json"
    scene_b = packs_root / "bonus" / "scenes" / "beta_base.json"
    scene_a.parent.mkdir(parents=True, exist_ok=True)
    scene_b.parent.mkdir(parents=True, exist_ok=True)
    scene_a.write_text(json.dumps({"name": "Alpha Outpost"}), encoding="utf-8")
    scene_b.write_text(json.dumps({"name": "Beta Base"}), encoding="utf-8")

    listings = list_pack_scene_listings(packs_root=packs_root)
    options = [(entry.path, entry.display_name) for entry in listings]
    filtered = filter_options(options, "beta")

    assert filtered
    assert filtered[0][0].endswith("packs/bonus/scenes/beta_base.json")


def test_scene_switcher_recent_order_stable(monkeypatch) -> None:
    controller = _build_controller(monkeypatch)

    controller.record_recent_scene("packs/a/scenes/alpha.json")
    controller.record_recent_scene("packs/b/scenes/beta.json")
    controller.record_recent_scene("packs/a/scenes/alpha.json")

    assert controller.scene_switcher_recent == [
        "packs/a/scenes/alpha.json",
        "packs/b/scenes/beta.json",
    ]


def test_scene_switcher_confirm_guard_invoked(monkeypatch) -> None:
    calls: list[str] = []
    controller = _build_controller(monkeypatch, request_scene_change=calls.append)
    controller._scene_switcher_cached = [("packs/a/scenes/alpha.json", "Alpha")]
    controller.scene_switcher_active = True
    controller.scene_switcher_index = 0
    controller._mark_dirty()

    opened = controller._scene_switcher_open_selected()

    assert opened is False
    assert controller.confirm_open is True
    assert calls == []


def test_scene_switcher_open_updates_recent(monkeypatch) -> None:
    calls: list[str] = []
    controller = _build_controller(monkeypatch, request_scene_change=calls.append)
    controller._scene_switcher_cached = [("packs/a/scenes/alpha.json", "Alpha")]
    controller.scene_switcher_active = True
    controller.scene_switcher_index = 0

    opened = controller._scene_switcher_open_selected()

    assert opened is True
    assert calls == ["packs/a/scenes/alpha.json"]
    assert controller.scene_switcher_recent[0] == "packs/a/scenes/alpha.json"
