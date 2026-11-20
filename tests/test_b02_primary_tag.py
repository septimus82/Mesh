"""B-02: an entity's primary tag (``mesh_tag``) survives save and load (#462 reliability).

``tags`` is written sorted, and restore used to set ``mesh_tag = tags[0]``: a player tagged "player" + "friendly"
came back as "friendly". The record now carries ``primary_tag`` (an optional v3 field: no version bump); a record
without it keeps the live sprite's primary when that is one of the saved tags, else falls back with a diagnostic.
Real cycles: a hidden GameWindow and the production SaveManager (tests/_b01_arena.py).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from engine.diagnostics import Diagnostic
from engine.save_runtime.digest import compute_entity_digest
from engine.save_runtime.entity_state import apply_entities_ex, serialize_entities
from tests._b01_arena import PIC, Arena, close_window, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

CODE = "save.restore.primary_tag_guessed"


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _room(arena: Arena) -> None:
    arena.write_room(
        {"id": "hero", "name": "Hero", "tag": "player", "tags": ["friendly"], "x": 50, "y": 50, "sprite": PIC},
        {"id": "npc", "name": "Guard", "tag": "guard", "tags": ["alpha", "zeta"], "x": 90, "y": 90, "sprite": PIC},
    )
    arena.enter()


def _primaries(arena: Arena) -> dict[str, Any]:
    return {s.mesh_id: s.mesh_tag for s in arena.sprites()}


def _rewrite(arena: Arena, strip: bool, v2: bool = False) -> None:
    save = arena.read()
    if strip:
        for record in save["saved_entities"]["entities"]:
            record.pop("primary_tag", None)
    if v2:
        save["save_schema_version"] = 2
        block = save["saved_entities"]
        block["schema_version"] = 1
        for key in ("counters", "scene_path", "unresolved"):
            block.pop(key, None)
        for record in block["entities"]:
            for key in ("keying", "mesh_id", "occurrence"):
                record.pop(key, None)
    arena.slot().write_text(json.dumps(save, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_roundtrip_keeps_the_primary_tag(arena: Arena) -> None:
    _room(arena)
    save = arena.save()
    by_id = {r["mesh_id"]: r for r in save["saved_entities"]["entities"]}
    assert by_id["hero"]["primary_tag"] == "player" and by_id["hero"]["tags"] == ["friendly", "player"]
    assert by_id["npc"]["primary_tag"] == "guard" and by_id["npc"]["tags"] == ["alpha", "guard", "zeta"]
    assert save["save_schema_version"] == 3
    arena.enter()
    assert arena.load()
    assert _primaries(arena) == {"hero": "player", "npc": "guard"}
    assert arena.by_id("npc").mesh_tags == ["alpha", "guard", "zeta"]


@pytest.mark.parametrize("v2", [False, True], ids=["v3_before_b02", "v2"])
def test_a_record_without_primary_keeps_the_live_primary(arena: Arena, v2: bool) -> None:
    _room(arena)
    arena.save()
    _rewrite(arena, strip=True, v2=v2)
    arena.enter()
    assert arena.load()
    assert _primaries(arena) == {"hero": "player", "npc": "guard"}


def _stub(tag: str | None) -> Any:
    return SimpleNamespace(mesh_name="Hero", mesh_id="hero", mesh_tag=tag, mesh_tags=[tag] if tag else [],
                           center_x=1.0, center_y=1.0, mesh_entity_data={"id": "hero"}, mesh_behaviours_runtime=[])


def _record(**extra: Any) -> dict[str, Any]:
    return {"entity_id": "Hero", "x": 1, "y": 1, "keying": "id", "mesh_id": "hero", "occurrence": 0,
            "tags": ["friendly", "player"], **extra}


def test_no_primary_and_live_primary_not_saved_falls_back_with_a_diagnostic() -> None:
    sprite = _stub("stranger")
    diags: list[Diagnostic] = []
    apply_entities_ex(SimpleNamespace(all_sprites=[sprite]), [_record()], diagnostics=diags)
    assert sprite.mesh_tag == "friendly"
    assert [d.code for d in diags if isinstance(d, Diagnostic)].count(CODE) == 1


def test_live_primary_among_saved_tags_is_kept_silently() -> None:
    sprite = _stub("player")
    diags: list[Diagnostic] = []
    apply_entities_ex(SimpleNamespace(all_sprites=[sprite]), [_record()], diagnostics=diags)
    assert sprite.mesh_tag == "player" and CODE not in [d.code for d in diags]


def test_primary_tag_wins_over_live_and_sorted_order() -> None:
    sprite = _stub("friendly")
    apply_entities_ex(SimpleNamespace(all_sprites=[sprite]), [_record(primary_tag="player")])
    assert sprite.mesh_tag == "player"


def test_unresolved_records_carry_primary_tag_untouched() -> None:
    record = _record(primary_tag="player")
    record["mesh_id"] = "gone"
    result = apply_entities_ex(SimpleNamespace(all_sprites=[_stub("player")]), [record], diagnostics=[])
    assert [e["record"] for e in result.unresolved] == [record]


def test_digest_ignores_primary_tag() -> None:
    sprite = _stub("player")
    sprite.mesh_tags = ["player", "friendly"]
    recs = serialize_entities(SimpleNamespace(all_sprites=[sprite]))
    assert recs[0]["primary_tag"] == "player"
    plain = copy.deepcopy(recs)
    plain[0].pop("primary_tag")
    assert compute_entity_digest(recs) == compute_entity_digest(plain)
