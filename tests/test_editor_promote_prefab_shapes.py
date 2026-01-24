from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController


class _StubSceneController:
    def __init__(self, sprites: list) -> None:
        self.tilemap_instance = None
        self._sprites = sprites

    def _ensure_entity_data_dict(self, sprite):
        if not isinstance(getattr(sprite, "mesh_entity_data", None), dict):
            sprite.mesh_entity_data = {}
        return sprite.mesh_entity_data

    def _apply_collision_poly(self, *_args, **_kwargs):
        return None

    def build_scene_snapshot(self):
        return {}

    @property
    def all_sprites(self):
        return list(self._sprites)


class _StubSprite:
    def __init__(self, data: dict) -> None:
        self.mesh_entity_data = data
        self.mesh_name = data.get("name", "entity")
        self.center_x = float(data.get("x", 0.0))
        self.center_y = float(data.get("y", 0.0))


class _StubPrefabs:
    def __init__(self, prefab_sources: dict[str, str]) -> None:
        self.prefab_sources = prefab_sources
        self.loaded = False

    def load(self, force: bool = False) -> None:  # noqa: ARG002
        self.loaded = True


def _build_controller(monkeypatch, scene_controller: _StubSceneController) -> EditorModeController:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    window = SimpleNamespace()
    window.strict_mode = False
    window.paused = False
    window.width = 800
    window.height = 600
    window.scene_controller = scene_controller
    window.screen_to_world = lambda x, y: (float(x), float(y))
    window.camera_controller = SimpleNamespace(zoom=1.0)

    controller = EditorModeController(window)  # type: ignore[arg-type]
    controller.active = True
    return controller


def test_promote_prefab_shapes_updates_pack_and_undo_redo(tmp_path: Path, monkeypatch) -> None:
    assets_dir = tmp_path / "assets"
    pack_dir = tmp_path / "packs" / "beta" / "data"
    assets_dir.mkdir(parents=True)
    pack_dir.mkdir(parents=True)

    assets_prefabs = assets_dir / "prefabs.json"
    pack_prefabs = pack_dir / "prefabs.json"

    assets_prefabs.write_text(json.dumps([{"id": "p_other", "entity": {"sprite": "a.png"}}]), encoding="utf-8")
    pack_payload = [
        {"id": "z_last", "entity": {"sprite": "z.png"}},
        {"id": "p_wall", "entity": {"sprite": "wall.png"}},
    ]
    pack_prefabs.write_text(json.dumps(pack_payload), encoding="utf-8")
    original_payload = json.loads(pack_prefabs.read_text(encoding="utf-8"))
    original_sorted = sorted(original_payload, key=lambda e: str(e.get("id") or ""))

    def fake_resolve_path(path: str) -> Path:
        if path == "assets/prefabs.json":
            return assets_prefabs
        if path == "packs/beta/data/prefabs.json":
            return pack_prefabs
        return tmp_path / path

    monkeypatch.setattr("engine.paths.resolve_path", fake_resolve_path)
    prefabs_stub = _StubPrefabs({"p_wall": "packs/beta/data/prefabs.json"})
    monkeypatch.setattr("engine.prefabs.get_prefab_manager", lambda: prefabs_stub)

    sprite = _StubSprite(
        {
            "name": "shape_entity",
            "prefab_id": "p_wall",
            "x": 10.0,
            "y": 20.0,
            "collision_poly": [[0, 0], [8, 0], [0, 8]],
            "occluder_poly": [[-4, -4], [4, -4], [4, 4], [-4, 4]],
        }
    )
    scene_controller = _StubSceneController([sprite])
    controller = _build_controller(monkeypatch, scene_controller)
    controller.selected_entity = sprite

    ok = controller._promote_prefab_shapes()
    assert ok is True
    assert "packs/beta/data/prefabs.json" in (controller._status_message or "")
    assert "(fallback)" not in (controller._status_message or "")

    updated = json.loads(pack_prefabs.read_text(encoding="utf-8"))
    ids = [entry.get("id") for entry in updated]
    assert ids == sorted(ids)
    entry = next(e for e in updated if e.get("id") == "p_wall")
    assert entry["entity"]["collision_poly"] == [[0, 0], [8, 0], [0, 8]]
    assert entry["entity"]["occluder_poly"] == [[-4, -4], [4, -4], [4, 4], [-4, 4]]

    controller.undo_last()
    reverted = json.loads(pack_prefabs.read_text(encoding="utf-8"))
    assert reverted == original_sorted

    controller.redo_last()
    redone = json.loads(pack_prefabs.read_text(encoding="utf-8"))
    assert redone != original_sorted


def test_promote_prefab_shapes_fallback_to_assets(tmp_path: Path, monkeypatch) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    assets_prefabs = assets_dir / "prefabs.json"
    assets_prefabs.write_text(json.dumps([{"id": "p_wall", "entity": {"sprite": "wall.png"}}]), encoding="utf-8")

    def fake_resolve_path(path: str) -> Path:
        if path == "assets/prefabs.json":
            return assets_prefabs
        return tmp_path / path

    monkeypatch.setattr("engine.paths.resolve_path", fake_resolve_path)
    prefabs_stub = _StubPrefabs({})
    monkeypatch.setattr("engine.prefabs.get_prefab_manager", lambda: prefabs_stub)

    sprite = _StubSprite(
        {
            "name": "shape_entity",
            "prefab_id": "p_wall",
            "collision_poly": [[0, 0], [8, 0], [0, 8]],
        }
    )
    scene_controller = _StubSceneController([sprite])
    controller = _build_controller(monkeypatch, scene_controller)
    controller.selected_entity = sprite

    ok = controller._promote_prefab_shapes()
    assert ok is True
    message = controller._status_message or ""
    assert "assets/prefabs.json" in message
    assert "(fallback)" in message

    updated = json.loads(assets_prefabs.read_text(encoding="utf-8"))
    entry = next(e for e in updated if e.get("id") == "p_wall")
    assert entry["entity"]["collision_poly"] == [[0, 0], [8, 0], [0, 8]]
