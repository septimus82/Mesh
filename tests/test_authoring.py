"""engine.authoring: one batch API for Studio, AI clients and the CLI, over project_ops."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import authoring
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.fast


@pytest.fixture
def project(tmp_path: Path) -> Project:
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    import json

    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    return Project(root, world_file)


NPC_BATCH = [
    {"op": "place_prefab", "prefab": "person", "x": 320, "y": 224},
    {"op": "rename_entity", "entity_id": "@0", "name": "Sexton"},
    {"op": "set_dialogue_text", "entity_id": "Sexton", "text": "Who goes there?"},
    {"op": "set_show_when", "entity_id": "@0", "require": "lantern_lit", "forbid": ""},
]


def test_the_operation_list_comes_from_project_ops_and_every_op_says_what_it_does() -> None:
    described = {d["op"]: d for d in authoring.describe()}
    assert {"place_prefab", "paint_tiles", "set_choice", "add_room", "link_rooms", "paste_entity"} <= set(described)
    assert "find_entity" not in described and "map_info" not in described  # reads are not edits
    assert all(d["summary"] for d in described.values())
    params = {p["name"]: p for p in described["move_entity"]["params"]}
    assert params["entity_id"]["required"] and params["room"]["required"] is False


def test_a_batch_is_one_undo_step_and_refers_to_what_it_made(project: Project) -> None:
    result = authoring.apply(project, NPC_BATCH)
    sexton = next(e for e in project.scene()["entities"] if e.get("name") == "Sexton")
    assert result["created"] == {0: sexton["id"]}
    assert sexton["behaviour_config"]["ConditionalActivator"]["require_flags"] == ["lantern_lit"]
    assert project.undo() and not any(e.get("name") == "Sexton" for e in project.scene()["entities"])
    assert not project.can_undo()  # the whole batch was one step


def test_a_refused_change_leaves_everything_as_it_was(project: Project) -> None:
    before = project.all_documents()
    with pytest.raises(authoring.ChangeError) as err:
        authoring.apply(project, [*NPC_BATCH, {"op": "move_entity", "entity_id": "Nobody", "x": 1, "y": 2}])
    assert err.value.index == 4 and "no object 'Nobody'" in str(err.value)
    assert project.all_documents() == before and not project.can_undo()
    with pytest.raises(authoring.ChangeError, match="no operation 'teleport'"):
        authoring.apply(project, [{"op": "teleport"}])
    with pytest.raises(authoring.ChangeError, match="unknown setting"):
        authoring.apply(project, [{"op": "move_entity", "entity_id": "Player", "x": 1, "y": 2, "z": 3}])
    with pytest.raises(authoring.ChangeError, match="no object type 'dragon'"):
        authoring.apply(project, [{"op": "place_prefab", "prefab": "dragon", "x": 1, "y": 2}])


def test_rooms_doors_and_tiles_through_the_same_api_and_a_dry_run_writes_nothing(project: Project) -> None:
    start = project.current
    batch = [{"op": "add_room", "label": "Crypt"},
             {"op": "link_rooms", "key_a": start, "at_a": [400, 300], "key_b": "crypt", "at_b": [256, 224]},
             {"op": "paint_tiles", "layer": "walls", "cells": [[3, 3], [4, 3]], "tile": 9}]
    before, after = authoring.dry_run(project, batch)
    assert "crypt" in after["rooms"] and not (project.root / "packs/core_regions/maps/crypt.json").exists()
    lines = authoring.summarize(before, after)
    assert "New room: Crypt" in lines and any("repaints 2 tile(s)" in line for line in lines)
    assert any("adds 'Door to Crypt'" in line for line in lines)
    authoring.apply(project, batch)
    assert (project.root / "packs/core_regions/maps/crypt.json").exists()


def test_separate_edits_dont_conflict_and_the_same_property_does() -> None:
    base = {"rooms": {"r": {"entities": [{"id": "a", "name": "Guard", "x": 1}], "tilemap": {"tile_layers": [
        {"id": "ground", "tiles": [1, 1, 1, 1]}]}}}}
    painted = {"rooms": {"r": {"entities": [{"id": "a", "name": "Guard", "x": 1}], "tilemap": {"tile_layers": [
        {"id": "ground", "tiles": [1, 5, 1, 1]}]}}}}
    npc_added = {"rooms": {"r": {"entities": [{"id": "a", "name": "Guard", "x": 1}, {"id": "b", "name": "Sexton"}],
                                 "tilemap": {"tile_layers": [{"id": "ground", "tiles": [1, 1, 1, 5]}]}}}}
    renamed = {"rooms": {"r": {"entities": [{"id": "a", "name": "Captain", "x": 1}], "tilemap": base["rooms"]["r"]["tilemap"]}}}
    renamed_same = {"rooms": {"r": {"entities": [{"id": "a", "name": "Captain", "x": 1}], "tilemap": base["rooms"]["r"]["tilemap"]}}}
    renamed_other = {"rooms": {"r": {"entities": [{"id": "a", "name": "Warden", "x": 1}], "tilemap": base["rooms"]["r"]["tilemap"]}}}
    studio = authoring.changes_between(base, painted)
    assert authoring.conflicts(studio, authoring.changes_between(base, npc_added)) == []
    ours = authoring.changes_between(base, renamed)
    assert authoring.conflicts(ours, authoring.changes_between(base, renamed_same)) == []  # both agree
    clash = authoring.conflicts(ours, authoring.changes_between(base, renamed_other))
    assert clash == [{"path": "rooms/r/entities/#a/name", "what": "r: object a name", "studio": "Captain", "ai": "Warden"}]
