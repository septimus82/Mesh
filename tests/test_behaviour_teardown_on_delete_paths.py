"""B-05b: the entity-destroy paths that bypass ``remove_from_sprite_lists`` also end the entity's behaviours.

Same real harness as test_behaviour_teardown_on_entity_removal: authoring/MCP delete, the legacy editor's delete and
the entity store's despawn op each remove the sprite from its lists directly; each must run ``on_destroy`` once.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

import pytest

from engine import optional_arcade
from engine.editor.editor_entity_ops_controller import EditorEntityOpsController
from engine.scene_runtime.index_build import build_scene_index_from_sprites
from engine.scene_entity_store_controller import SceneEntityStoreController
from engine.scene_runtime.authoring.entity_ops_parts.delete_ops import debug_remove_entity_by_id
from tests._b01_arena import Arena, close_window, make_window
from tests.test_behaviour_teardown_on_entity_removal import (
    CUTSCENE, EXIT, HERO, QUEST, XP, Probe, _all_four, _baseline_with_hero, listeners)

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _authoring(arena: Arena, sprite: Any) -> None:
    arena.controller._scene_index = build_scene_index_from_sprites(arena.controller.all_sprites)  # runtime spawn: index is stale
    assert debug_remove_entity_by_id(arena.controller, sprite.mesh_entity_data["id"])


def _editor(arena: Arena, sprite: Any) -> None:
    editor = SimpleNamespace(window=SimpleNamespace(scene_controller=arena.controller), selected_entity=None)
    EditorEntityOpsController(editor).delete_entity_internal(sprite)  # type: ignore[arg-type]


def _store(arena: Arena, sprite: Any) -> None:
    store = SceneEntityStoreController()
    store.enqueue_despawn(sprite)
    store.apply_pending_ops(arena.controller)


PATHS: list[Callable[[Arena, Any], None]] = [_authoring, _editor, _store]
IDS = ["authoring", "editor", "store"]


def _count_destroys(sprite: Any) -> list[int]:
    calls = [0]
    for behaviour in sprite.mesh_behaviours_runtime:
        orig = behaviour.on_destroy

        def counted(orig: Callable[[], Any] = orig) -> Any:
            calls[0] += 1
            return orig()

        behaviour.on_destroy = counted
    return calls


@pytest.mark.parametrize("delete", PATHS, ids=IDS)
def test_delete_path_ends_behaviours_once(arena: Arena, delete: Callable[[Arena, Any], None]) -> None:
    base = _baseline_with_hero(arena)
    probe = Probe(arena)
    sprite = arena.spawn(_all_four("npc"))
    assert listeners(arena) == base + 4
    calls = _count_destroys(sprite)

    delete(arena, sprite)

    assert listeners(arena) == base
    assert probe.publish(sprite) == (0, 0, 0, 0)
    assert calls[0] == 4  # one on_destroy per behaviour (xp, quest, cutscene, exit)
    sprite.remove_from_sprite_lists()  # a later removal never ends them again
    assert calls[0] == 4


@pytest.mark.parametrize("delete", PATHS, ids=IDS)
def test_delete_then_recreate_works_again(arena: Arena, delete: Callable[[Arena, Any], None]) -> None:
    """Undo of a delete re-creates the entity from its data (a fresh sprite with fresh behaviours)."""
    base = _baseline_with_hero(arena)
    probe = Probe(arena)
    data = _all_four("npc")
    delete(arena, arena.spawn(data))
    assert listeners(arena) == base

    again = arena.controller._create_sprite(data)
    arena.controller.add_sprite_to_layer(again, "entities")

    assert listeners(arena) == base + 4
    assert probe.publish(again) == (1, 1, 1, 1)
