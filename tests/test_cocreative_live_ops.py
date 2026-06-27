from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import engine.optional_arcade as optional_arcade
from engine.editor_controller import EditorModeController
from engine.scene_runtime.persistence import build_scene_snapshot


class _FakeSprite:
    def __init__(self, entity: dict[str, Any]) -> None:
        self.mesh_entity_data = entity
        self.mesh_name = str(entity.get("name") or "")
        self.center_x = float(entity.get("x", 0.0))
        self.center_y = float(entity.get("y", 0.0))
        self.scale = float(entity.get("scale", 1.0))
        self.angle = float(entity.get("rotation", 0.0))
        self.mesh_behaviours_runtime: list[Any] = []
        self.mesh_behaviour_configs: list[dict[str, Any]] = []


class _FakeTilemap:
    def __init__(self) -> None:
        self.tile_size = (16, 16)
        self.layer_dimensions = (2, 2)
        self.layer_data = {"ground": [0, 0, 0, 0]}
        self.layer_lookup = {"ground": []}
        self.layer_offsets = {"ground": (0.0, 0.0)}
        self.tilesets: list[Any] = []


class _FakeSceneController:
    def __init__(self, window: Any) -> None:
        self.window = window
        self.current_scene_path = "scenes/live.json"
        self._loaded_scene_data: dict[str, Any] = {"settings": {}, "entities": []}
        self.layers: dict[str, list[_FakeSprite]] = {"entities": []}
        self.solid_sprites: list[_FakeSprite] = []
        self.tilemap_instance = None

    @property
    def all_sprites(self) -> list[_FakeSprite]:
        sprites: list[_FakeSprite] = []
        for layer in self.layers.values():
            sprites.extend(layer)
        return sprites

    def _create_sprite(self, entity: dict[str, Any]) -> _FakeSprite:
        return _FakeSprite(entity)

    def add_sprite_to_layer(self, sprite: _FakeSprite, layer_name: str = "entities") -> None:
        self.layers.setdefault(layer_name, []).append(sprite)

    def _apply_entity_mutation(
        self,
        sprite: _FakeSprite,
        *,
        x: float | None = None,
        y: float | None = None,
        scale: float | None = None,
        tag: str | None = None,
    ) -> None:
        if x is not None:
            sprite.center_x = float(x)
            sprite.mesh_entity_data["x"] = float(x)
        if y is not None:
            sprite.center_y = float(y)
            sprite.mesh_entity_data["y"] = float(y)
        if scale is not None:
            sprite.scale = float(scale)
            sprite.mesh_entity_data["scale"] = float(scale)
        if tag is not None:
            sprite.mesh_entity_data["tag"] = tag

    def _ensure_entity_data_dict(self, sprite: _FakeSprite) -> dict[str, Any]:
        return sprite.mesh_entity_data

    def _ensure_behaviour_config_root(self, entity_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        root = entity_data.setdefault("behaviour_config", {})
        if not isinstance(root, dict):
            entity_data["behaviour_config"] = {}
            root = entity_data["behaviour_config"]
        return root

    def _get_behaviour_configs_for_sprite(self, sprite: _FakeSprite) -> list[dict[str, Any]]:
        return sprite.mesh_behaviour_configs

    def set_tile(self, layer_name: str, col: int, row: int, gid: int) -> tuple[int, int] | None:
        tilemap = self.tilemap_instance
        if tilemap is None:
            return None
        width, height = tilemap.layer_dimensions
        if not (0 <= col < width and 0 <= row < height):
            return None
        data = tilemap.layer_data.setdefault(layer_name, [0] * (width * height))
        index = row * width + col
        before = int(data[index])
        if before == int(gid):
            return None
        data[index] = int(gid)
        return before, int(gid)

    def build_scene_snapshot(self, compact: bool = False) -> dict[str, Any]:
        return build_scene_snapshot(self, compact=compact)


class _FakeWindow:
    def __init__(self) -> None:
        self.scene_controller = _FakeSceneController(self)
        self.strict_mode = False
        self.width = 800
        self.height = 600
        self.paused = False
        self.camera_controller = SimpleNamespace(
            zoom_state=SimpleNamespace(
                current=1.0,
                target=1.0,
                speed=1.0,
                min_zoom=0.5,
                max_zoom=2.0,
            )
        )
        self.game_state = SimpleNamespace(snapshot=lambda: {})
        self.scene_loader = SimpleNamespace(apply_scene_defaults=lambda snapshot: snapshot)
        self.lighting = SimpleNamespace(configure_scene_lights=lambda _lights: None)
        self.screen_to_world = lambda x, y: (x, y)


def _make_controller() -> EditorModeController:
    controller = EditorModeController(_FakeWindow())
    controller.prefab_palette = [
        {
            "id": "crate",
            "display_name": "Crate",
            "entity": {"name": "crate", "sprite": "assets/crate.png", "layer": "entities"},
        }
    ]
    controller.active = True
    controller._selected_entity_ids = []
    controller._primary_entity_id = None
    controller._refresh_hierarchy_list = lambda: None  # type: ignore[method-assign]
    controller._refresh_inspector_items = lambda: None  # type: ignore[method-assign]
    controller._refresh_entity_panels_list = lambda *, sync_selected=False: None  # type: ignore[method-assign]
    return controller


def _entity_names(snapshot: dict[str, Any]) -> list[str]:
    return [str(entity.get("name")) for entity in snapshot.get("entities", []) if isinstance(entity, dict)]


def _proposal_ops(*names: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "add_entity_from_prefab",
            "prefab_id": "crate",
            "x": 64 + (index * 16),
            "y": 80,
            "name": name,
        }
        for index, name in enumerate(names)
    ]


def _add_entity(controller: EditorModeController, name: str = "ai_crate") -> _FakeSprite:
    result = controller.apply_live_op(
        {"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 64, "y": 80, "name": name}
    )
    assert result["ok"] is True
    sprite = controller.window.scene_controller.all_sprites[-1]
    controller.selected_entity = sprite
    controller._selected_entity_ids = [name]
    controller._primary_entity_id = name
    return sprite


def test_live_add_entity_from_prefab_applies_to_scene_and_pushes_one_undo() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller

    before_sprite_count = len(scene_controller.all_sprites)
    before_entity_count = len(scene_controller._loaded_scene_data["entities"])

    result = controller.apply_live_op({"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 32, "y": 48})

    assert result["ok"] is True
    assert len(scene_controller.all_sprites) == before_sprite_count + 1
    assert len(scene_controller._loaded_scene_data["entities"]) == before_entity_count + 1
    assert controller.scene_dirty is True
    assert len(controller.undo.undo_stack) == 1
    assert controller.undo.undo_stack[0]["type"] == "AddEntity"
    assert not controller.undo.redo_stack


def test_live_add_entity_from_prefab_is_visible_in_snapshot_before_save() -> None:
    controller = _make_controller()

    result = controller.apply_live_op(
        {"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 64, "y": 80, "name": "ai_crate"}
    )

    assert result["ok"] is True
    snapshot = controller.window.scene_controller.build_scene_snapshot(compact=False)
    assert "ai_crate" in _entity_names(snapshot)


def test_live_add_entity_from_prefab_undo_redo_updates_sprite_payload_and_snapshot() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller

    result = controller.apply_live_op(
        {"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 64, "y": 80, "name": "ai_crate"}
    )
    assert result["ok"] is True

    assert controller.undo.undo() is True
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data["entities"] == []
    assert "ai_crate" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))

    assert controller.undo.redo() is True
    assert len(scene_controller.all_sprites) == 1
    assert [entity.get("name") for entity in scene_controller._loaded_scene_data["entities"]] == ["ai_crate"]
    assert "ai_crate" in _entity_names(scene_controller.build_scene_snapshot(compact=False))


def test_live_add_entity_from_prefab_rejects_different_scene_without_mutation() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    before_scene = deepcopy(scene_controller._loaded_scene_data)

    result = controller.apply_live_op(
        {
            "type": "add_entity_from_prefab",
            "scene_path": "scenes/other.json",
            "prefab_id": "crate",
            "x": 32,
            "y": 48,
        }
    )

    assert result["ok"] is False
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data == before_scene
    assert controller.scene_dirty is False
    assert controller.undo.undo_stack == []


def test_read_live_scene_reflects_unsaved_entity_move_without_save() -> None:
    controller = _make_controller()
    _add_entity(controller, "moving_crate")
    revision_after_add = controller.content_revision

    controller.nudge_selected(16, 0)

    payload = controller.read_live_scene()
    entity = next(entity for entity in payload["scene"]["entities"] if entity.get("name") == "moving_crate")
    assert entity["x"] == 80.0
    assert payload["revision"] == revision_after_add + 1
    assert payload["dirty"] is True
    assert payload["current_scene_path"] == "scenes/live.json"
    assert payload["selected_entity_ids"] == ["moving_crate"]


def test_read_live_scene_reflects_unsaved_tile_paint_without_save() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    scene_controller.tilemap_instance = _FakeTilemap()
    scene_controller._loaded_scene_data["tilemap"] = {"overrides": {"layers": {"ground": [0, 0, 0, 0]}}}
    controller.tile_layers = ["ground"]
    controller.tile_layer_index = 0
    revision_before = controller.content_revision

    controller.tile.paint_tile_at(8, 8, 7)

    payload = controller.read_live_scene()
    assert payload["revision"] == revision_before + 1
    assert payload["scene"]["tilemap"]["overrides"]["layers"]["ground"] == [0, 0, 7, 0]


def test_content_revision_bumps_once_for_each_core_live_mutation() -> None:
    controller = _make_controller()

    start = controller.content_revision
    sprite = _add_entity(controller, "revision_crate")
    assert controller.content_revision == start + 1

    controller.nudge_selected(16, 0)
    assert controller.content_revision == start + 2

    scene_controller = controller.window.scene_controller
    scene_controller.tilemap_instance = _FakeTilemap()
    scene_controller._loaded_scene_data["tilemap"] = {"overrides": {"layers": {"ground": [0, 0, 0, 0]}}}
    controller.tile_layers = ["ground"]
    controller.tile_layer_index = 0
    controller.tile.paint_tile_at(8, 8, 7)
    assert controller.content_revision == start + 3

    controller.lights.add_light(32, 32)
    assert controller.content_revision == start + 4
    controller.lights.handle_lights_key_input(optional_arcade.arcade.key.M, 0)
    assert controller.content_revision == start + 5

    controller.selected_entity = sprite
    controller._selected_entity_ids = ["revision_crate"]
    controller._primary_entity_id = "revision_crate"
    controller._update_param("Dialogue", "dialogue", {"start": "intro", "nodes": {}})
    assert controller.content_revision == start + 6


def test_read_live_scene_and_rejected_live_op_do_not_change_revision() -> None:
    controller = _make_controller()
    revision = controller.content_revision

    controller.read_live_scene()
    assert controller.content_revision == revision

    result = controller.apply_live_op(
        {
            "type": "add_entity_from_prefab",
            "scene_path": "scenes/other.json",
            "prefab_id": "crate",
            "x": 32,
            "y": 48,
        }
    )

    assert result["ok"] is False
    assert controller.content_revision == revision


def test_stage_proposal_valid_batch_dry_runs_without_mutation() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    revision = controller.content_revision

    proposal = controller.stage_proposal(_proposal_ops("staged_crate"))

    assert proposal.base_revision == revision
    assert proposal.dry_run["ok"] is True
    assert proposal.dry_run["affected_ids"] == ["staged_crate"]
    assert "staged_crate" in proposal.preview_summary
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data["entities"] == []
    assert controller.content_revision == revision
    assert controller.undo.undo_stack == []


def test_accept_proposal_at_matching_revision_pushes_one_undo_entry() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    revision = controller.content_revision
    proposal = controller.stage_proposal(_proposal_ops("accepted_crate"))

    result = controller.accept_proposal(proposal)

    assert result["ok"] is True
    assert len(scene_controller.all_sprites) == 1
    assert [entity.get("name") for entity in scene_controller._loaded_scene_data["entities"]] == ["accepted_crate"]
    assert "accepted_crate" in _entity_names(scene_controller.build_scene_snapshot(compact=False))
    assert controller.content_revision == revision + 1
    assert len(controller.undo.undo_stack) == 1
    assert controller.undo.undo_stack[0]["type"] == "ApplyAIOpBatch"

    assert controller.undo.undo() is True
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data["entities"] == []
    assert "accepted_crate" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))

    assert controller.undo.redo() is True
    assert len(scene_controller.all_sprites) == 1
    assert [entity.get("name") for entity in scene_controller._loaded_scene_data["entities"]] == ["accepted_crate"]
    assert "accepted_crate" in _entity_names(scene_controller.build_scene_snapshot(compact=False))


def test_accept_multi_op_proposal_is_one_undoable_batch() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    proposal = controller.stage_proposal(_proposal_ops("batch_crate_a", "batch_crate_b"))

    result = controller.accept_proposal(proposal)

    assert result["ok"] is True
    assert len(scene_controller.all_sprites) == 2
    assert _entity_names(scene_controller.build_scene_snapshot(compact=False)) == ["batch_crate_a", "batch_crate_b"]
    assert len(controller.undo.undo_stack) == 1
    assert controller.undo.undo_stack[0]["type"] == "ApplyAIOpBatch"
    assert len(controller.undo.undo_stack[0]["children"]) == 2

    assert controller.undo.undo() is True
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data["entities"] == []
    assert _entity_names(scene_controller.build_scene_snapshot(compact=False)) == []

    assert controller.undo.redo() is True
    assert len(scene_controller.all_sprites) == 2
    assert _entity_names(scene_controller.build_scene_snapshot(compact=False)) == ["batch_crate_a", "batch_crate_b"]


def test_accept_stale_proposal_is_blocked_without_mutation() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    proposal = controller.stage_proposal(_proposal_ops("stale_crate"))

    _add_entity(controller, "human_crate")
    revision_after_human_edit = controller.content_revision
    sprite_count = len(scene_controller.all_sprites)
    entity_payload = deepcopy(scene_controller._loaded_scene_data["entities"])

    result = controller.accept_proposal(proposal)

    assert result["ok"] is False
    assert result["data"]["stale"] is True
    assert len(scene_controller.all_sprites) == sprite_count
    assert scene_controller._loaded_scene_data["entities"] == entity_payload
    assert "stale_crate" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))
    assert controller.content_revision == revision_after_human_edit
    assert len(controller.undo.undo_stack) == 1


def test_reject_proposal_drops_it_without_mutation() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    revision = controller.content_revision
    proposal = controller.stage_proposal(_proposal_ops("rejected_crate"))

    result = controller.reject_proposal(proposal)

    assert result["ok"] is True
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data["entities"] == []
    assert controller.undo.undo_stack == []
    assert controller.content_revision == revision


def test_invalid_proposal_batch_refuses_accept_without_partial_apply() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    revision = controller.content_revision
    proposal = controller.stage_proposal(
        [
            *_proposal_ops("valid_but_not_applied"),
            {"type": "add_entity_from_prefab", "prefab_id": "missing", "x": 64, "y": 80},
        ]
    )

    assert proposal.dry_run["ok"] is False
    assert proposal.dry_run["warnings"]

    result = controller.accept_proposal(proposal)

    assert result["ok"] is False
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data["entities"] == []
    assert "valid_but_not_applied" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))
    assert controller.undo.undo_stack == []
    assert controller.content_revision == revision
