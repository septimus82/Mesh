"""Creator Mode selected-entity duplicate proposal contracts."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

from engine.editor.creator_mode import (
    ENTITY_DUPLICATE_STAGE_ACTION_ID,
    CreatorModeController,
    build_creator_entity_duplicate_live_ops,
    build_creator_entity_duplicate_request,
    build_creator_overlay_model,
    build_duplicate_entity_payload,
    next_duplicate_entity_id,
)
from engine.editor.creator_mode.creator_entity_duplicate_request import (
    creator_entity_duplicate_request_key,
)
from engine.editor.creator_mode.creator_overlay_renderer import (
    build_creator_overlay_draw_commands,
    hit_test_creator_overlay_click,
)
from engine.editor.editor_command_dispatch_controller import EditorCommandDispatchController
from engine.editor.editor_live_ops_controller import EditorLiveOpsController

pytestmark = pytest.mark.fast


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []
        self._pending: list[dict[str, Any]] = []
        self._counter = 0

    def stage_pending_proposal(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(copy.deepcopy(ops))
        self._counter += 1
        proposal_id = f"duplicate-proposal-{self._counter}"
        proposal = {
            "proposal_id": proposal_id,
            "id": proposal_id,
            "preview_summary": f"Duplicate {ops[0].get('source_entity_id')}",
            "ops": copy.deepcopy(ops),
            "dry_run": {
                "ok": True,
                "warnings": [],
                "affected_ids": [str(ops[0].get("duplicate_entity_id"))],
            },
        }
        self._pending.append(proposal)
        return {"ok": True, "proposal_id": proposal_id, "proposal": proposal}

    def list_pending_proposals(self) -> list[dict[str, Any]]:
        return list(self._pending)

    def clear(self) -> None:
        self._pending.clear()


class _Sprite:
    def __init__(self, data: dict[str, Any]) -> None:
        self.mesh_entity_data = data
        self.mesh_name = data.get("name", "")
        self.center_x = float(data.get("x", 0.0) or 0.0)
        self.center_y = float(data.get("y", 0.0) or 0.0)
        self.alpha = int(round(float(data.get("alpha", 1.0)) * 255.0))


def _crate(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "crate_01",
        "name": "Crate",
        "x": 320.0,
        "y": 192.0,
        "solid": True,
        "alpha": 0.75,
        "tags": ["loot"],
        "layer": "Props",
        "prefab_id": "prefabs/crate",
        "behaviours": ["StaticSprite"],
        "behaviour_config": {"StaticSprite": {"asset": "crate.png"}},
        "custom": {"loot_table": "basic"},
    }
    data.update(overrides)
    return data


def _door(**overrides: Any) -> dict[str, Any]:
    data = _crate(
        id="FieldDoor",
        name="Field Door",
        behaviours=["SceneTransition", "Interactable"],
        behaviour_config={
            "SceneTransition": {
                "target_scene": "scenes/door_interior.json",
                "spawn_id": "from_field",
            },
            "Interactable": {"event": "use"},
        },
    )
    data.update(overrides)
    return data


def _editor(
    selected: dict[str, Any] | None,
    *,
    bridge: Any = None,
    width: float = 1280.0,
    height: float = 720.0,
    entities: list[dict[str, Any]] | None = None,
    snap_to_tile: bool = False,
) -> SimpleNamespace:
    scene_entities = entities if entities is not None else ([selected] if selected is not None else [])
    sprites = [_Sprite(entity) for entity in scene_entities]
    selected_sprite = sprites[0] if selected is not None and sprites else None
    scene = {
        "tilemap": {"width": 20, "height": 20, "tilewidth": 32, "tileheight": 48},
        "entities": scene_entities,
    }
    scene_controller = SimpleNamespace(
        current_scene_path="scenes/door_field.json",
        _loaded_scene_data=scene,
        _loaded_scene_source_data=scene,
        all_sprites=sprites,
        get_authored_scene_payload=lambda: scene,
        _ensure_entity_data_dict=lambda sprite: sprite.mesh_entity_data,
    )
    window = SimpleNamespace(
        width=width,
        height=height,
        scene_controller=scene_controller,
        entity_snap_to_tile=snap_to_tile,
    )
    return SimpleNamespace(
        selected_entity=selected_sprite,
        live_bridge=bridge if bridge is not None else FakeBridge(),
        grid_size=32.0,
        window=window,
        proposal_inbox=object(),
        dock=SimpleNamespace(
            right_tab="Inspector",
            get_right_collapsed=lambda: False,
            toggle_right_dock=lambda _e: None,
            apply_tab_change=lambda _e, _side, _tab: True,
            get_viewport_maximized=lambda: False,
            toggle_viewport_maximized=lambda _e: None,
        ),
    )


def _controller(
    selected: dict[str, Any] | None,
    *,
    bridge: Any = None,
    width: float = 1280.0,
    height: float = 720.0,
    entities: list[dict[str, Any]] | None = None,
    snap_to_tile: bool = False,
) -> CreatorModeController:
    controller = CreatorModeController(
        _editor(
            selected,
            bridge=bridge,
            width=width,
            height=height,
            entities=entities,
            snap_to_tile=snap_to_tile,
        )
    )
    controller.show()
    return controller


def _commands(controller: CreatorModeController, width: float = 1280.0, height: float = 720.0):
    model = build_creator_overlay_model(controller.build_snapshot())
    return build_creator_overlay_draw_commands(model, width, height)


def test_duplicate_request_uses_canonical_id_offset_and_copies_authored_payload() -> None:
    source = _crate()
    request = build_creator_entity_duplicate_request(
        source,
        source_scene="scenes/door_field.json",
        authored_scene={"entities": [source]},
        duplicate_offset=(16.0, 16.0),
    )

    assert request.ok is True
    assert request.source_entity_id == "crate_01"
    assert request.duplicate_entity_id == "crate_01__dup1"
    assert (request.from_x, request.from_y) == (320.0, 192.0)
    assert (request.to_x, request.to_y) == (336.0, 208.0)
    duplicate = build_duplicate_entity_payload(
        source,
        source_id=request.source_entity_id,
        duplicate_id=request.duplicate_entity_id,
        x=request.to_x,
        y=request.to_y,
    )
    assert duplicate["id"] == "crate_01__dup1"
    assert duplicate["x"] == 336.0
    assert duplicate["y"] == 208.0
    for key in ("name", "solid", "alpha", "tags", "layer", "prefab_id", "behaviours", "behaviour_config", "custom"):
        assert duplicate[key] == source[key]
    assert source["id"] == "crate_01"
    assert source["x"] == 320.0


def test_id_generation_uses_smallest_free_canonical_suffix() -> None:
    assert next_duplicate_entity_id("a", {"a", "a__dup1"}) == "a__dup2"
    assert next_duplicate_entity_id("a", {"a", "a__dup2"}) == "a__dup1"


@pytest.mark.parametrize(
    ("selected", "authored", "reason"),
    [
        (None, {"entities": []}, "Select one"),
        ({"name": "Only Name", "x": 1, "y": 2}, {"entities": []}, "stable authored ID"),
        ({"id": "runtime", "_runtime_generated": True}, {"entities": []}, "Runtime-generated"),
        ({"id": "missing", "x": 1, "y": 2}, {"entities": []}, "authored scene"),
        ({"id": "bad", "x": "nope", "y": 2}, {"entities": [{"id": "bad", "x": "nope", "y": 2}]}, "position"),
        ({"id": "self", "x": 1, "y": 2}, {"entities": [{"id": "self", "x": 1, "y": 2, "target": "self"}]}, "self-references"),
    ],
)
def test_duplicate_request_fails_closed_for_ineligible_selection(
    selected: dict[str, Any] | None,
    authored: dict[str, Any],
    reason: str,
) -> None:
    request = build_creator_entity_duplicate_request(
        selected,
        source_scene="scenes/door_field.json",
        authored_scene=authored,
        duplicate_offset=(16.0, 16.0),
    )
    assert request.ok is False
    assert reason in request.reason


def test_entity_id_fallback_is_supported_but_name_only_is_not() -> None:
    entity = _crate(id="", entity_id="entity-2")
    request = build_creator_entity_duplicate_request(
        entity,
        source_scene="scenes/door_field.json",
        authored_scene={"entities": [entity]},
        duplicate_offset=(16, 16),
    )
    assert request.ok is True
    assert request.source_entity_id == "entity-2"
    assert request.duplicate_entity_id == "entity-2__dup1"

    name_only = build_creator_entity_duplicate_request(
        {"name": "Entity Two", "x": 1, "y": 2},
        source_scene="scenes/door_field.json",
        authored_scene={"entities": []},
        duplicate_offset=(16, 16),
    )
    assert name_only.ok is False


def test_snap_tile_offset_is_exposed_by_controller_panel() -> None:
    source = _crate()
    controller = _controller(source, entities=[source], snap_to_tile=True)

    panel = controller.build_snapshot().duplicate_panel

    assert panel is not None
    assert panel.duplicate_position_text == "(352, 240)"
    assert panel.offset_text == "Offset: 32, 48"


def test_overlay_model_and_click_stage_duplicate_without_mutating_scene() -> None:
    bridge = FakeBridge()
    source = _door()
    before = copy.deepcopy(source)
    controller = _controller(source, bridge=bridge, entities=[source])
    snapshot = controller.build_snapshot()
    panel = snapshot.duplicate_panel
    assert panel is not None
    assert panel.action.enabled is True
    assert panel.source_entity_id == "FieldDoor"
    assert panel.duplicate_entity_id == "FieldDoor__dup1"

    commands = _commands(controller)
    stage = next(c for c in commands if c.action_id == ENTITY_DUPLICATE_STAGE_ACTION_ID)
    assert hit_test_creator_overlay_click(
        commands,
        (stage.hit_left + stage.hit_right) / 2,
        (stage.hit_bottom + stage.hit_top) / 2,
    ) == ENTITY_DUPLICATE_STAGE_ACTION_ID
    result = controller.handle_overlay_click(
        (stage.hit_left + stage.hit_right) / 2,
        (stage.hit_bottom + stage.hit_top) / 2,
    )

    assert result is not None
    assert result.ok is True
    assert source == before
    assert len(controller._editor.window.scene_controller._loaded_scene_data["entities"]) == 1
    assert len(bridge.calls) == 1
    op = bridge.calls[0][0]
    assert op["type"] == "duplicate_entity"
    assert op["source_entity_id"] == "FieldDoor"
    assert op["duplicate_entity_id"] == "FieldDoor__dup1"
    assert "entity" not in op


@pytest.mark.parametrize(("width", "height"), [(1660, 895), (1280, 720), (1024, 600), (800, 600)])
def test_duplicate_layout_keeps_stage_hitbox_reachable(width: int, height: int) -> None:
    source = _door()
    controller = _controller(source, width=float(width), height=float(height), entities=[source])
    commands = _commands(controller, width=float(width), height=float(height))
    duplicate_cmds = [c for c in commands if c.action_id == ENTITY_DUPLICATE_STAGE_ACTION_ID]
    assert len(duplicate_cmds) == 1
    stage = duplicate_cmds[0]
    assert stage.region == "right"
    assert 0.0 <= stage.hit_bottom <= stage.hit_top <= float(height)
    assert stage.hit_left >= 0.0
    assert stage.hit_right <= float(width)
    assert hit_test_creator_overlay_click(
        commands,
        (stage.hit_left + stage.hit_right) / 2,
        (stage.hit_bottom + stage.hit_top) / 2,
    ) == ENTITY_DUPLICATE_STAGE_ACTION_ID


def test_disabled_duplicate_stage_emits_no_hitbox() -> None:
    controller = _controller(_crate(), bridge=object(), entities=[_crate()])
    commands = _commands(controller)
    assert [c.action_id for c in commands].count(ENTITY_DUPLICATE_STAGE_ACTION_ID) == 0


def test_duplicate_staging_guard_blocks_until_pending_removed() -> None:
    bridge = FakeBridge()
    source = _crate()
    controller = _controller(source, bridge=bridge, entities=[source])
    first = controller.stage_selected_entity_duplicate()
    second = controller.stage_selected_entity_duplicate()
    assert first.ok is True
    assert second.ok is False
    assert "already staged" in second.errors[0]
    assert len(bridge.calls) == 1

    bridge.clear()
    controller._prune_stale_duplicate_keys()
    assert controller.stage_selected_entity_duplicate().ok is True


def test_changed_source_state_creates_distinct_duplicate_key() -> None:
    a = build_creator_entity_duplicate_request(
        _crate(name="Crate"),
        source_scene="scenes/door_field.json",
        authored_scene={"entities": [_crate(name="Crate")]},
        duplicate_offset=(16, 16),
    )
    b = build_creator_entity_duplicate_request(
        _crate(name="Box"),
        source_scene="scenes/door_field.json",
        authored_scene={"entities": [_crate(name="Box")]},
        duplicate_offset=(16, 16),
    )
    assert creator_entity_duplicate_request_key(a) != creator_entity_duplicate_request_key(b)


def test_live_ops_preview_summary_and_payload_are_narrow() -> None:
    source = _crate()
    request = build_creator_entity_duplicate_request(
        source,
        source_scene="scenes/door_field.json",
        authored_scene={"entities": [source]},
        duplicate_offset=(16, 16),
    )
    live = build_creator_entity_duplicate_live_ops(request)
    assert live.ok is True
    op = live.ops[0]
    assert op["type"] == "duplicate_entity"
    assert op["source_entity_id"] == "crate_01"
    assert op["duplicate_entity_id"] == "crate_01__dup1"
    assert "Duplicate crate_01 as crate_01__dup1" in live.preview_summary


class _LiveEditor:
    def __init__(self, entity: dict[str, Any]) -> None:
        self.content_revision = 0
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []
        self.refreshes: list[str] = []
        self._selected_entity_ids = {_stable_id(entity)}
        self._primary_entity_id = _stable_id(entity)
        self.sprites = [_Sprite(entity)]
        scene_controller = SimpleNamespace(
            current_scene_path="scenes/door_field.json",
            _loaded_scene_data={"entities": [entity]},
            all_sprites=self.sprites,
            _ensure_entity_data_dict=lambda sprite: sprite.mesh_entity_data,
        )
        self.window = SimpleNamespace(scene_controller=scene_controller)
        self.selected_entity = self.sprites[0]
        self.command_dispatch = EditorCommandDispatchController(self)
        self.live_ops = EditorLiveOpsController(self)

    def _find_entity_by_id(self, entity_id: str) -> Any:
        for sprite in self.sprites:
            data = sprite.mesh_entity_data
            if data.get("id") == entity_id or data.get("entity_id") == entity_id:
                return sprite
        return None

    def _find_entity_by_name(self, name: str) -> Any:
        for sprite in self.sprites:
            if sprite.mesh_name == name:
                return sprite
        return None

    def _create_entity_internal(self, entity_def: dict[str, Any]) -> _Sprite:
        sprite = _Sprite(entity_def)
        self.sprites.append(sprite)
        self.window.scene_controller.all_sprites = self.sprites
        return sprite

    def _delete_entity_internal(self, sprite: _Sprite) -> None:
        self.sprites = [item for item in self.sprites if item is not sprite]
        self.window.scene_controller.all_sprites = self.sprites
        if self.selected_entity is sprite:
            self.selected_entity = self.sprites[0] if self.sprites else None

    def _push_command(self, command: dict[str, Any]) -> None:
        self.undo_stack.append(copy.deepcopy(command))
        self.redo_stack.clear()
        self.content_revision += 1

    def _refresh_hierarchy_list(self) -> None:
        self.refreshes.append("hierarchy")

    def _refresh_inspector_items(self) -> None:
        self.refreshes.append("inspector")

    def _refresh_entity_panels_list(self, *, sync_selected: bool = False) -> None:
        self.refreshes.append(f"entity_panels:{sync_selected}")

    def stage_proposal(self, ops: list[dict[str, Any]]) -> Any:
        return self.live_ops.stage_proposal(ops)

    def accept_proposal(self, proposal: Any) -> dict[str, Any]:
        return self.live_ops.accept_proposal(proposal)

    def reject_proposal(self, proposal: Any) -> dict[str, Any]:
        return self.live_ops.reject_proposal(proposal)


def _stable_id(entity: dict[str, Any]) -> str:
    return str(entity.get("id") or entity.get("entity_id") or "")


def _duplicate_op(source: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    request = build_creator_entity_duplicate_request(
        source,
        source_scene="scenes/door_field.json",
        authored_scene={"entities": [source]},
        duplicate_offset=(16, 16),
    )
    live = build_creator_entity_duplicate_live_ops(request)
    op = copy.deepcopy(live.ops[0])
    op.update(overrides)
    return op


def test_accept_duplicates_once_selects_duplicate_and_pushes_one_undoable_batch() -> None:
    source = _door()
    before = copy.deepcopy(source)
    editor = _LiveEditor(source)
    proposal = editor.stage_proposal([_duplicate_op(source)])
    assert proposal.dry_run["ok"] is True

    result = editor.accept_proposal(proposal)

    entities = editor.window.scene_controller._loaded_scene_data["entities"]
    assert result["ok"] is True
    assert len(entities) == 2
    duplicate = entities[1]
    assert source == before
    assert duplicate["id"] == "FieldDoor__dup1"
    assert duplicate["x"] == 336.0
    assert duplicate["y"] == 208.0
    for key in ("name", "solid", "alpha", "prefab_id", "behaviour_config"):
        assert duplicate[key] == source[key]
    assert editor.selected_entity.mesh_entity_data is duplicate
    assert editor._selected_entity_ids == {"FieldDoor__dup1"}
    assert len(editor.undo_stack) == 1
    assert editor.undo_stack[0]["children"][0]["type"] == "DuplicateEntity"


def test_reject_leaves_scene_and_selection_unchanged() -> None:
    source = _crate()
    editor = _LiveEditor(source)
    proposal = editor.stage_proposal([_duplicate_op(source)])

    result = editor.reject_proposal(proposal)

    assert result["ok"] is True
    assert editor.window.scene_controller._loaded_scene_data["entities"] == [source]
    assert editor.selected_entity.mesh_entity_data is source
    assert editor.undo_stack == []


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda source, op, scene: source.update(name="Changed"), "changed"),
        (lambda source, op, scene: source.update(x=321.0), "moved"),
        (lambda source, op, scene: scene["entities"].append(_crate(id=op["duplicate_entity_id"])), "already in use"),
        (lambda source, op, scene: op.update(scene_path="other.json"), "targets"),
        (lambda source, op, scene: op.update(duplicate_entity_id="crate_01__dup9"), "stale"),
    ],
)
def test_stale_duplicate_proposals_fail_closed(mutate: Any, message: str) -> None:
    source = _crate()
    editor = _LiveEditor(source)
    op = _duplicate_op(source)
    proposal = editor.stage_proposal([op])
    mutate(source, op, editor.window.scene_controller._loaded_scene_data)
    entity_count_after_external_change = len(editor.window.scene_controller._loaded_scene_data["entities"])
    proposal.ops[0] = op

    result = editor.accept_proposal(proposal)

    assert result["ok"] is False
    assert message in result["message"]
    assert len(editor.window.scene_controller._loaded_scene_data["entities"]) == entity_count_after_external_change


def test_arbitrary_payload_in_op_is_ignored() -> None:
    source = _crate()
    editor = _LiveEditor(source)
    op = _duplicate_op(source, entity={"id": "evil", "x": 999, "y": 999})
    result = editor.live_ops.apply_live_op(op)

    assert result["ok"] is True
    duplicate = editor.window.scene_controller._loaded_scene_data["entities"][1]
    assert duplicate["id"] == "crate_01__dup1"
    assert duplicate["x"] == 336.0
    assert duplicate["y"] == 208.0


def test_undo_and_redo_restore_exact_duplicate_id_payload_and_selection() -> None:
    source = _crate()
    editor = _LiveEditor(source)
    result = editor.live_ops.apply_live_op(_duplicate_op(source))
    assert result["ok"] is True
    command = editor.undo_stack[0]

    editor.command_dispatch.revert_command(command)
    entities = editor.window.scene_controller._loaded_scene_data["entities"]
    assert entities == [source]
    assert editor.selected_entity.mesh_entity_data is source

    editor.command_dispatch.apply_command(command)
    entities = editor.window.scene_controller._loaded_scene_data["entities"]
    assert len(entities) == 2
    assert entities[1]["id"] == "crate_01__dup1"
    assert entities[1]["x"] == 336.0
    assert editor.selected_entity.mesh_entity_data["id"] == "crate_01__dup1"
