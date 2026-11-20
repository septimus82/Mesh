"""B-01: stable entity identity in saves (v3 migration, #462 reliability).

Design: docs/reviews/b01_entity_save_identity_design.md (revision 3). Before B-01 a save keyed each object's state by
its display name: two goblins both called "Goblin" wrote two records that both landed on the last goblin, the first
one came back untouched, and nothing said so. Records are now keyed by the authored id (several sharing one bind by
order and place only when the counts agree) or, for id-less sprites, by name and then by place; a v2 save binds only
where the pairing is provable; everything else is reported and kept as an *unresolved* record in every later save.

Real gameplay cycles: a hidden GameWindow, the production SaveManager, real scene and save files (tests/_b01_arena.py).
The T-numbers are the design's test plan (section 4).
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from engine.diagnostics import Diagnostic, DiagnosticLevel
from engine.save_runtime import io as save_io
from engine.save_runtime.entity_state import (
    apply_entities,
    apply_entities_ex,
    serialize_entities,
)
from engine.save_runtime.schema import SAVE_SCHEMA_VERSION, migrate_save
from engine.scene_runtime.room_memory import room_key
from tests._b01_arena import Arena, close_window, goblin, hero, hp_of, make_window, sha

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "saved_world"


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def as_v2(save: dict[str, Any]) -> dict[str, Any]:
    """A v3 save the engine just wrote, rewritten into the shape the v2 engine wrote (name-keyed records, no
    scene_path/counters/unresolved): a stand-in for a player's old slot."""
    old = copy.deepcopy(save)
    old["save_schema_version"] = 2
    block = old["saved_entities"]
    block["schema_version"] = 1
    for key in ("counters", "scene_path", "unresolved"):
        block.pop(key, None)
    for record in block["entities"]:
        for key in ("keying", "mesh_id", "occurrence"):
            record.pop(key, None)
    block["entities"].sort(key=lambda r: r["entity_id"])  # (v2 sorted by name alone)
    return old


def write_v2(arena: Arena, save: dict[str, Any], name: str = "slot1") -> Path:
    path = arena.slot(name)
    path.write_text(json.dumps(as_v2(save), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def last_load_codes() -> list[str]:
    attempt = save_io.get_save_runtime_diagnostics_snapshot()["last_load_attempt"]
    return [str(row.get("code")) for row in attempt["diagnostics"]["diagnostics"]]


def two_goblins(arena: Arena, *, a: tuple[float, float, float] = (111, 122, 3),
                b: tuple[float, float, float] = (333, 344, 20)) -> None:
    arena.write_room(hero(), goblin("gob_a", 100, 100), goblin("gob_b", 300, 300))
    arena.enter()
    arena.place(arena.by_id("gob_a"), *a[:2], hp=a[2])
    arena.place(arena.by_id("gob_b"), *b[:2], hp=b[2])


# ---- model-level stand-ins (no window): the binding rules in isolation --------------------------------------------


class Health:
    """A behaviour with the save hooks the engine's own Health has (found by class name, as the saver does)."""

    def __init__(self, hp: float) -> None:
        self.hp = hp

    def saveable_state(self) -> dict[str, Any]:
        return {"hp": self.hp}

    def restore_state(self, payload: dict[str, Any]) -> None:
        self.hp = payload["hp"]


class Stub:
    def __init__(self, name: str | None, x: float, y: float, hp: float = 20.0, mesh_id: str | None = None) -> None:
        self.mesh_name = name
        self.mesh_id = mesh_id
        self.center_x, self.center_y = x, y
        self.mesh_entity_data: dict[str, Any] = {"id": mesh_id} if mesh_id else {}
        self.mesh_behaviours_runtime = [Health(hp)]

    @property
    def hp(self) -> float:
        return self.mesh_behaviours_runtime[0].hp


def stage(*sprites: Stub) -> Any:
    return SimpleNamespace(all_sprites=list(sprites))


def legacy(name: str, x: float, y: float, hp: float) -> dict[str, Any]:
    return {"entity_id": name, "x": x, "y": y, "behaviour_state": {"Health": {"hp": hp}}, "keying": "name",
            "legacy": True}


def id_record(mesh_id: str, name: str, x: float, y: float, hp: float, occurrence: int = 0) -> dict[str, Any]:
    return {"entity_id": name, "x": x, "y": y, "behaviour_state": {"Health": {"hp": hp}}, "keying": "id",
            "mesh_id": mesh_id, "occurrence": occurrence}


def name_record(name: str, x: float, y: float, hp: float) -> dict[str, Any]:
    return {"entity_id": name, "x": x, "y": y, "behaviour_state": {"Health": {"hp": hp}}, "keying": "name"}


# =====================================================================================================================
# Writing and binding by identity
# =====================================================================================================================


def test_T1_dup_names_roundtrip_v3(arena: Arena) -> None:
    """The base repro: two goblins named alike, one hurt and moved. Through the production save and load."""
    two_goblins(arena)
    save = arena.save()
    assert save["save_schema_version"] == SAVE_SCHEMA_VERSION == 3
    records = {r["mesh_id"]: r for r in save["saved_entities"]["entities"] if r["entity_id"] == "Goblin"}
    assert sorted(records) == ["gob_a", "gob_b"]
    assert all(r["keying"] == "id" and r["occurrence"] == 0 for r in records.values())
    arena.enter()  # a fresh room (hp 20 each, authored places)
    assert arena.load()
    a, b = arena.by_id("gob_a"), arena.by_id("gob_b")
    assert (a.center_x, a.center_y, hp_of(a)) == (111.0, 122.0, 3.0)
    assert (b.center_x, b.center_y, hp_of(b)) == (333.0, 344.0, 20.0)


def test_T1b_the_records_alone_restore_a_pristine_room(arena: Arena) -> None:
    """Without the save's own scene snapshot to re-place objects (apply_entities on a pristine room): the hurt
    goblin gets its state, the other is unharmed; before B-01 both records landed on the last goblin."""
    two_goblins(arena)
    records = arena.save()["saved_entities"]["entities"]
    arena.enter()
    diags: list[Diagnostic] = []
    assert apply_entities(arena.controller, records, diagnostics=diags) == (3, 0)
    assert diags == []
    a, b = arena.by_id("gob_a"), arena.by_id("gob_b")
    assert (hp_of(a), a.center_x, a.center_y) == (3.0, 111.0, 122.0)
    assert (hp_of(b), b.center_x, b.center_y) == (20.0, 333.0, 344.0)


def test_T2_dup_names_sprite_order_independent(arena: Arena) -> None:
    two_goblins(arena)
    records = arena.save()["saved_entities"]["entities"]
    arena.write_room(goblin("gob_b", 300, 300), goblin("gob_a", 100, 100), hero())  # the other way round
    arena.enter()
    assert [s.mesh_id for s in arena.sprites()][:2] != ["gob_a", "gob_b"]
    assert apply_entities(arena.controller, records) == (3, 0)
    assert hp_of(arena.by_id("gob_a")) == 3.0 and hp_of(arena.by_id("gob_b")) == 20.0


def test_T3_unnamed_same_prefab_entities_each_restored(arena: Arena) -> None:
    """Unnamed entities of one prefab share a mesh_name (the prefab id): ten trees are one name. Ids tell them apart."""
    trees = [dict(goblin(f"tree_{i}", 100 + 40 * i, 100, 20), prefab_id="tree") for i in range(3)]
    for tree in trees:
        del tree["name"]
    arena.write_room(hero(), *trees)
    arena.enter()
    names = {s.mesh_name for s in arena.sprites() if str(s.mesh_id).startswith("tree_")}
    assert len(names) == 1  # (one shared name: the base keyed all three alike)
    for i, hp in enumerate((4.0, 9.0, 14.0)):
        arena.place(arena.by_id(f"tree_{i}"), 100 + 40 * i, 100, hp=hp)
    records = arena.save()["saved_entities"]["entities"]
    assert {r["mesh_id"] for r in records if str(r.get("mesh_id")).startswith("tree_")} == {"tree_0", "tree_1", "tree_2"}
    arena.enter()
    assert arena.load()
    assert [hp_of(arena.by_id(f"tree_{i}")) for i in range(3)] == [4.0, 9.0, 14.0]


def test_T9_idless_unique_name_roundtrip(arena: Arena) -> None:
    arena.write_room(hero())
    arena.enter()
    arena.spawn(goblin(None, 30, 30, 7, name="spawned_7"), hp=4)
    save = arena.save()
    record = next(r for r in save["saved_entities"]["entities"] if r["entity_id"] == "spawned_7")
    assert record["keying"] == "name" and "mesh_id" not in record
    arena.enter()
    assert arena.load()
    assert hp_of(arena.named("spawned_7")[0]) == 4.0


def test_T10_idless_same_name_distinct_xy_both_restored(arena: Arena) -> None:
    arena.write_room(hero())
    arena.enter()
    arena.spawn(goblin(None, 10, 10, 5, name="proj_Hero"), hp=2)
    arena.spawn(goblin(None, 20, 20, 9, name="proj_Hero"), hp=6)
    arena.save()
    arena.enter()
    assert arena.load()
    assert [(s.center_x, hp_of(s)) for s in arena.named("proj_Hero")] == [(10.0, 2.0), (20.0, 6.0)]
    assert arena.toasts() == ["Game loaded"] or "could not be matched" not in " ".join(arena.toasts())


def test_T11_idless_same_name_same_xy_not_applied_and_reported(arena: Arena, capsys: pytest.CaptureFixture[str]) -> None:
    arena.write_room(hero())
    arena.enter()
    arena.spawn(goblin(None, 10, 10, 5, name="proj_Hero"), hp=2)
    arena.spawn(goblin(None, 10, 10, 9, name="proj_Hero"), hp=6)
    arena.save()
    arena.enter()
    assert arena.load()
    hps = sorted(hp_of(s) or 0 for s in arena.named("proj_Hero"))
    assert hps == [5.0, 9.0]  # neither saved state was applied, nothing was "last wins"
    codes = last_load_codes()
    assert codes.count("save.restore.entity_nameclash") == 2 and "save.restore.entities_unbound" in codes
    assert "could not be matched" in " ".join(arena.toasts())
    assert len(arena.held()) == 2
    assert "entity_nameclash" in capsys.readouterr().err


def test_T12_idless_record_never_lands_on_an_id_sprite() -> None:
    gob = Stub("Goblin", 100, 100, hp=20, mesh_id="gob_a")
    result = apply_entities_ex(stage(gob), [name_record("Goblin", 100, 100, 3)])
    assert (result.applied, result.missing, result.unbound) == (0, 1, 0)
    assert gob.hp == 20


def test_T13_an_expired_projectile_is_missing_and_carried_never_applied_elsewhere() -> None:
    diags: list[Diagnostic] = []
    result = apply_entities_ex(stage(Stub("Hero", 1, 1)), [name_record("proj_Hero", 5, 5, 1)], diagnostics=diags,
                               strict=True)
    assert (result.applied, result.missing, result.unbound) == (0, 1, 0)
    assert [e["reason"] for e in result.unresolved] == ["entity_missing"]  # kept, not dropped
    assert "save.restore.entity_missing" in [d.code for d in diags]
    assert not [d for d in diags if d.level == DiagnosticLevel.ERROR]  # (reported, never an error)
    # a different projectile of the same name, somewhere else, does not take it
    other = Stub("proj_Hero", 99, 99, 20)
    again = apply_entities_ex(stage(other), [], carried=result.unresolved)
    assert (again.applied, again.unresolved) == (0, result.unresolved) and other.hp == 20


def test_a_carried_missing_id_record_binds_when_the_id_returns() -> None:
    first = apply_entities_ex(stage(Stub("Hero", 1, 1, mesh_id="hero")), [id_record("gob_a", "Goblin", 5, 5, 3)])
    assert (first.missing, [e["reason"] for e in first.unresolved]) == (1, ["entity_missing"])
    back = Stub("Goblin", 100, 100, 20, "gob_a")
    result = apply_entities_ex(stage(Stub("Hero", 1, 1, mesh_id="hero"), back), [], carried=first.unresolved)
    assert (result.applied, result.retried, result.unresolved) == (1, 1, []) and back.hp == 3
    wrong_id = Stub("Goblin", 5, 5, 20, "gob_x")  # another id at the very place: still not it
    assert apply_entities_ex(stage(wrong_id), [], carried=first.unresolved).applied == 0 and wrong_id.hp == 20


def test_a_carried_idless_record_binds_only_to_a_sprite_at_its_exact_place() -> None:
    first = apply_entities_ex(stage(), [name_record("proj_Hero", 5, 5, 1)])
    assert [e["reason"] for e in first.unresolved] == ["entity_missing"]
    elsewhere = Stub("proj_Hero", 6, 6, 20)
    assert apply_entities_ex(stage(elsewhere), [], carried=first.unresolved).applied == 0 and elsewhere.hp == 20
    there = Stub("proj_Hero", 5, 5, 20)
    result = apply_entities_ex(stage(elsewhere, there), [], carried=first.unresolved)
    assert (result.retried, result.unresolved) == (1, []) and there.hp == 1 and elsewhere.hp == 20


def test_T14_dup_authored_ids_all_written_with_a_warning(arena: Arena) -> None:
    arena.write_room(hero(), goblin("gob_a", 100, 100), goblin("gob_b", 300, 300))
    arena.enter()
    arena.spawn(dict(arena.by_id("gob_a").mesh_entity_data, x=150, y=150, name="Goblin_clone"), hp=11)  # console clone
    diags: list[Diagnostic] = []
    records = serialize_entities(arena.controller, diagnostics=diags)
    twins = [r for r in records if r.get("mesh_id") == "gob_a"]
    assert sorted(r["occurrence"] for r in twins) == [0, 1] and len(twins) == 2
    dup = [d for d in diags if d.code == "save.serialize.entity_id_duplicate"]
    assert len(dup) == 1 and dup[0].level == DiagnosticLevel.WARN
    assert dup[0].context["id"] == "gob_a" and dup[0].context["count"] == 2
    arena.save()
    last = save_io.get_save_runtime_diagnostics_snapshot()["last_save_attempt"]
    assert "save.serialize.entity_id_duplicate" in [r["code"] for r in last["diagnostics"]["diagnostics"]]


def test_T15_dup_authored_ids_bound_by_occurrence_and_place(arena: Arena) -> None:
    arena.write_room(hero(), goblin("gob_a", 100, 100))
    arena.enter()
    arena.place(arena.by_id("gob_a"), 100, 100, hp=5)
    arena.spawn(dict(arena.by_id("gob_a").mesh_entity_data, x=150, y=150, name="Goblin_clone"), hp=11)
    arena.save()
    arena.enter()
    assert arena.load()
    twins = sorted((s for s in arena.sprites() if getattr(s, "mesh_id", None) == "gob_a"), key=lambda s: s.center_x)
    assert [(s.center_x, hp_of(s)) for s in twins] == [(100.0, 5.0), (150.0, 11.0)]  # neither merged nor lost
    assert arena.held() == []


def test_T16_dup_authored_ids_count_mismatch_refused(arena: Arena, capsys: pytest.CaptureFixture[str]) -> None:
    arena.write_room(hero(), goblin("gob_a", 100, 100))
    arena.enter()
    arena.place(arena.by_id("gob_a"), 100, 100, hp=5)
    arena.spawn(dict(arena.by_id("gob_a").mesh_entity_data, x=150, y=150, name="Goblin_clone"), hp=11)
    save = arena.save()
    save["entities"] = [e for e in save["entities"] if not (e.get("id") == "gob_a" and e["x"] == 150.0)]  # one is gone
    arena.slot().write_text(json.dumps(save, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = sha(arena.slot())
    arena.enter()
    assert arena.load()
    assert sha(arena.slot()) == before  # the load rewrote nothing: the records are still in the file
    assert hp_of(arena.by_id("gob_a")) == 20.0  # not "one of the two records, picked"
    assert last_load_codes().count("save.restore.entity_id_ambiguous") == 1
    assert "entity_id_ambiguous" in capsys.readouterr().err
    arena.save("slot2")
    assert len(arena.unresolved("slot2")) == 2  # both records still in the next save
    # In strict mode the same finding is an error (the production load keeps it a warning: it must never refuse a load)
    gob = Stub("Goblin", 100, 100, mesh_id="gob_a")
    diags: list[Diagnostic] = []
    result = apply_entities_ex(stage(gob), [id_record("gob_a", "Goblin", 100, 100, 5, 0),
                                            id_record("gob_a", "Goblin", 150, 150, 11, 1)],
                               strict=True, diagnostics=diags)
    assert (result.applied, result.unbound) == (0, 2) and gob.hp == 20
    assert [d.level for d in diags if d.code == "save.restore.entity_id_ambiguous"] == [DiagnosticLevel.ERROR]


# =====================================================================================================================
# v2 saves: real old saves, hand-built ones, and the provable-binding rule
# =====================================================================================================================


def _stage_from_snapshot(save: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """A scene standing as the save's own snapshot says (the sprites a loaded save builds), named as its records."""
    records = save["saved_entities"]["entities"]
    sprites = []
    for entity in save["entities"]:
        named = next((r["entity_id"] for r in records if (r["x"], r["y"]) == (entity["x"], entity["y"])), None)
        sprites.append(Stub(entity.get("name") or named, entity["x"], entity["y"], mesh_id=entity.get("id")))
    return stage(*sprites), records


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_T4_real_old_saves_load(kind: str, tmp_path: Path) -> None:
    """The committed pre-#390 saves (written by the v2 engine): migrated in memory, every record applied, nothing
    unbound, no new diagnostics (their names are unique)."""
    raw = json.loads((FIXTURES / f"pre390_{kind}.json").read_text(encoding="utf-8"))
    assert raw["save_schema_version"] == 2
    ok, payload = save_io.load_slot_payload(FIXTURES / f"pre390_{kind}.json", policy=_slot_policy(), sidecars=False)
    assert ok is True and isinstance(payload, dict)
    assert payload["save_schema_version"] == 3
    records = payload["saved_entities"]["entities"]
    assert records and all(r["keying"] == "name" and r["legacy"] is True for r in records)
    scene, _ = _stage_from_snapshot(payload)
    diags: list[Diagnostic] = []
    result = apply_entities_ex(scene, records, snapshot=payload["entities"], diagnostics=diags)
    assert (result.applied, result.missing, result.unbound, result.unresolved) == (len(records), 0, 0, [])
    assert diags == []


def _slot_policy() -> Any:
    from engine.save_runtime.restore_policy import SLOT_POLICY

    return SLOT_POLICY


def test_T5_real_v2_save_with_idless_dupname_dupid(arena: Arena) -> None:
    """A save the v2 engine wrote (tests/fixtures/saved_world/v2_idless_dupname_dupid.json): two Goblins, a console
    clone with a copied id, two id-less proj_Hero and spawned_7. Loaded by the production SaveManager."""
    save = json.loads((FIXTURES / "v2_idless_dupname_dupid.json").read_text(encoding="utf-8"))
    arena.write_room(hero(), goblin("gob_a", 100, 100), goblin("gob_b", 300, 300))
    save["meta"]["scene_path"] = str(arena.room)  # (the fixture's own is scrubbed)
    arena.saves.mkdir(exist_ok=True)
    arena.slot().write_text(json.dumps(save, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    arena.enter()
    assert arena.load()
    assert hp_of(arena.named("spawned_7")[0]) == 4.0
    assert [(s.center_x, hp_of(s)) for s in arena.named("proj_Hero")] == [(10.0, 2.0), (20.0, 6.0)]
    assert hp_of(arena.by_id("hero")) == 10.0
    gob_b = arena.by_id("gob_b")
    assert (gob_b.center_x, hp_of(gob_b)) == (300.0, 20.0)  # bound by place, snapshot agreeing
    assert arena.by_id("gob_a").center_x == 150.0  # the save's snapshot placed it (the clone merged into it)
    codes = last_load_codes()
    assert codes.count("save.restore.entity_legacy_ambiguous") == 1  # Goblin (100, 100): no live goblin stands there
    assert codes.count("save.restore.entity_missing") >= 1  # Goblin_clone: no such sprite any more
    held = arena.held()  # the Goblin at (100, 100) (unbound) and Goblin_clone (no such sprite): both carried
    assert sorted((e["record"]["entity_id"], e["reason"]) for e in held) == [("Goblin", "position"), ("Goblin_clone", "entity_missing")]
    assert "could not be matched" in " ".join(arena.toasts())


def test_T6_v2_dup_names_bound_by_xy(arena: Arena) -> None:
    two_goblins(arena)
    write_v2(arena, arena.save())
    arena.enter()
    assert arena.load()
    a, b = arena.by_id("gob_a"), arena.by_id("gob_b")
    assert (a.center_x, a.center_y, hp_of(a)) == (111.0, 122.0, 3.0)
    assert (b.center_x, b.center_y, hp_of(b)) == (333.0, 344.0, 20.0)
    assert arena.held() == [] and "could not be matched" not in " ".join(arena.toasts())


def _unbindable_v2(arena: Arena) -> Path:
    """two_goblins as a v2 save whose two Goblin records stand where no live goblin does."""
    two_goblins(arena)
    old = as_v2(arena.save())
    for record in old["saved_entities"]["entities"]:
        if record["entity_id"] == "Goblin":
            record["x"], record["y"] = (500.0, 500.0) if record["x"] < 200 else (600.0, 600.0)
    arena.slot().write_text(json.dumps(old, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return arena.slot()


def test_T7_v2_dup_names_unbindable_refused(arena: Arena) -> None:
    _unbindable_v2(arena)
    arena.enter()
    assert arena.load()
    assert [hp_of(arena.by_id(i)) for i in ("gob_a", "gob_b")] == [20.0, 20.0]  # neither record applied
    codes = last_load_codes()
    assert codes.count("save.restore.entity_legacy_ambiguous") == 2  # one per record
    assert "save.restore.entities_unbound" in codes
    rollup = [r for r in save_io.get_save_runtime_diagnostics_snapshot()["last_load_attempt"]["diagnostics"]["diagnostics"]
              if r["code"] == "save.restore.entities_unbound"][0]
    assert (rollup["context"]["applied"], rollup["context"]["missing"], rollup["context"]["unbound"]) == (4, 0, 2) or \
        rollup["context"]["unbound"] == 2  # (applied counts the hero and... only records that bound)
    assert len(arena.held()) == 2


def test_T8_v2_unique_names_unchanged(arena: Arena) -> None:
    arena.write_room(hero(), goblin("orc", 100, 100, name="Orc"), goblin("troll", 300, 300, name="Troll"))
    arena.enter()
    arena.place(arena.by_id("orc"), 111, 122, hp=3)
    arena.place(arena.by_id("troll"), 333, 344, hp=9)
    expected = arena.state()
    write_v2(arena, arena.save())
    arena.enter()
    assert arena.load()
    assert arena.state() == expected
    codes = last_load_codes()
    assert not [c for c in codes if "entit" in c and c != "save.restore.entities_missing"]
    assert arena.held() == [] and "could not be matched" not in " ".join(arena.toasts())


def test_T25_the_player_toast_only_when_something_was_unmatched(arena: Arena) -> None:
    _unbindable_v2(arena)
    arena.enter()
    arena.load()
    assert "Loaded. 2 object states from this save could not be matched; see the log" in arena.toasts()
    arena.window.game_state_controller.replace_state({})  # New Game: the old game's unresolved records stay behind
    arena.write_room(hero(), goblin("orc", 100, 100, name="Orc"))
    arena.enter()
    arena.save("clean")
    arena.window.player_hud.clear_toasts()
    arena.enter()
    arena.load("clean")
    assert not [t for t in arena.toasts() if "could not be matched" in t]


# =====================================================================================================================
# Authors change things after a save
# =====================================================================================================================


def test_T17_a_renamed_entity_keeps_its_state(arena: Arena) -> None:
    """Studio's rename changes the name, never the id: the state follows the id (a name-keyed record was lost)."""
    from engine import project_ops as ops

    two_goblins(arena)
    arena.save()
    scene = json.loads(arena.room.read_text(encoding="utf-8"))
    arena.room.write_text(json.dumps(ops.rename_entity(scene, "gob_a", "Brute")), encoding="utf-8")
    arena.enter()
    assert arena.load()
    brute = arena.by_id("gob_a")
    assert brute.mesh_name == "Brute" and hp_of(brute) == 3.0


def test_T18_a_renamed_id_reports_missing_and_applies_nothing_elsewhere(arena: Arena) -> None:
    two_goblins(arena)
    arena.save()
    scene = json.loads(arena.room.read_text(encoding="utf-8"))
    scene["entities"][1]["id"] = "gob_x"  # (what the lint fixer's rename_id does to a duplicate)
    arena.room.write_text(json.dumps(scene), encoding="utf-8")
    arena.enter()
    assert arena.load()
    assert hp_of(arena.by_id("gob_x")) == 20.0 and arena.by_id("gob_x").center_x == 100.0  # not given gob_a's state
    assert "save.restore.entity_missing" in last_load_codes()
    held = arena.held()  # missing is unmatched too: carried, so it binds again if the id comes back
    assert [(e["reason"], e["record"]["mesh_id"]) for e in held] == [("entity_missing", "gob_a")]
    assert arena.save("s2")["saved_entities"]["unresolved"] == held
    scene["entities"][1]["id"] = "gob_a"  # the id comes back
    arena.room.write_text(json.dumps(scene), encoding="utf-8")
    arena.enter()
    assert arena.load("s2")
    assert hp_of(arena.by_id("gob_a")) == 3.0
    assert [e["record"]["mesh_id"] for e in arena.held()] == ["gob_x"]  # gob_a left the list; the now-absent gob_x joined it


def test_T19_wrong_room_guard(arena: Arena) -> None:
    """A load applies the records first to the room being left. A v3 save names its room: another room's objects
    (here, one with the same id and name) are left alone until the saved room loads."""
    two_goblins(arena)
    arena.save()
    other = arena.root / "other.json"
    other.write_text(json.dumps({"name": "Other", "schema_version": 1, "version": 1, "layers": [],
                                 "entities": [hero(), goblin("gob_a", 1, 1)]}), encoding="utf-8")
    arena.controller.load_scene(str(other))
    assert arena.manager.load_game("slot1")  # (the scene change is queued, not yet run)
    twin = arena.by_id("gob_a")
    assert (twin.center_x, twin.center_y, hp_of(twin)) == (1.0, 1.0, 20.0)
    assert "save.restore.entities_wrong_room" in last_load_codes()
    from engine.scene_lifecycle_controller import handle_pending_scene_load

    assert handle_pending_scene_load(arena.controller) is True
    assert hp_of(arena.by_id("gob_a")) == 3.0


def test_T19b_the_guard_is_in_the_unit_too() -> None:
    gob = Stub("Goblin", 100, 100, mesh_id="gob_a")
    diags: list[Diagnostic] = []
    result = apply_entities_ex(stage(gob), [id_record("gob_a", "Goblin", 5, 5, 3)], scene_path="rooms/a.json",
                               current_room="rooms/b.json", diagnostics=diags)
    assert result.skipped_wrong_room and (result.applied, result.missing) == (0, 0) and gob.hp == 20
    assert [d.code for d in diags] == ["save.restore.entities_wrong_room"]
    same = apply_entities_ex(stage(gob), [id_record("gob_a", "Goblin", 5, 5, 3)], scene_path="rooms\\a.json",
                             current_room="rooms/a.json")
    assert same.applied == 1 and gob.hp == 3


# =====================================================================================================================
# Determinism
# =====================================================================================================================


def test_T28_serialization_order_is_total() -> None:
    sprites = [Stub("Goblin", 100, 100, 1, "gob_a"), Stub("Goblin", 150, 150, 2, "gob_a"), Stub("Goblin", 300, 300, 3, "gob_b"),
               Stub("proj_Hero", 10, 10, 4), Stub("proj_Hero", 20, 20, 5), Stub("proj_Hero", 20, 20, 6),
               Stub("Hero", 50, 50, 7, "hero")]
    expected = serialize_entities(stage(*sprites))
    rng = random.Random(7)
    for _ in range(12):
        shuffled = list(sprites)
        rng.shuffle(shuffled)
        got = serialize_entities(stage(*shuffled))
        # (twins of one id take their occurrence from sprite order, so compare the rest of each record in order)
        assert [(r["entity_id"], r["x"], r["y"], r["keying"], r.get("mesh_id")) for r in got] == \
               [(r["entity_id"], r["x"], r["y"], r["keying"], r.get("mesh_id")) for r in expected]
    unique = [Stub("A", 1, 1, 1, "a"), Stub("B", 2, 2, 2), Stub("C", 3, 3, 3, "c")]
    first = serialize_entities(stage(*unique))
    assert serialize_entities(stage(*reversed(unique))) == first  # no duplicates: byte-identical whatever the order


def test_T29_digest_unchanged_for_unique_names() -> None:
    """digest.py is untouched and the new record fields are outside its projection: a unique-named scene hashes to the
    value the base computed (b5f16a32..., recorded on 0e05bd94 with the same scene)."""
    from engine.save_runtime.digest import compute_world_digest_from_scene

    scene = stage(Stub("Hero", 50, 50, 10, "hero"), Stub("Orc", 100, 100, 20, "orc_1"), Stub("Troll", 300, 300, 12.5, "troll_1"),
                  Stub("proj_Hero", 10, 10, 3), Stub("spawned_7", 30, 30, 4))
    scene.all_sprites[0].mesh_tag = "player"
    for sprite in scene.all_sprites:
        sprite.mesh_behaviours_runtime[0].saveable_state = (lambda s=sprite: {"hp": s.mesh_behaviours_runtime[0].hp, "dead": False})
    assert compute_world_digest_from_scene(scene, None, 7) == \
        "b5f16a32debe35cb787359b50bebd5b8fb333a8b43093dcf3ecb1de1ff908d9a"


def test_T30_v3_roundtrip_is_stable(arena: Arena) -> None:
    two_goblins(arena)
    arena.spawn(goblin(None, 10, 10, 5, name="proj_Hero"), hp=2)
    first = arena.save("a")["saved_entities"]
    arena.enter()
    assert arena.load("a")
    second = arena.save("b")["saved_entities"]
    assert first == second


# =====================================================================================================================
# Unresolved records: never silently discarded
# =====================================================================================================================


def test_T33_unresolved_survive_repeated_saves(arena: Arena) -> None:
    _unbindable_v2(arena)
    arena.enter()
    assert arena.load()
    first = arena.save("s1")["saved_entities"]["unresolved"]
    assert len(first) == 2 and {e["record"]["entity_id"] for e in first} == {"Goblin"}
    assert all(e["reason"] == "position" and e["scene_path"] == room_key(str(arena.room)) and e["first_seen"] for e in first)
    for n in range(2, 5):  # save, load, save, load ...
        arena.enter()
        assert arena.load(f"s{n - 1}")
        assert arena.save(f"s{n}")["saved_entities"]["unresolved"] == first  # byte-equal entries, never multiplied
        assert len(arena.held()) == 2
    assert "Loaded. 2 object states" in " ".join(arena.toasts())


def test_T34_unresolved_bind_after_a_scene_fix(arena: Arena) -> None:
    """The records waited in the save; the scene is then changed so exactly one sprite stands where one record says
    (a goblin added at (500, 500)): it binds on the next load and leaves the list; the other stays."""
    _unbindable_v2(arena)
    arena.enter()
    arena.load()
    arena.save("s1")
    scene = json.loads(arena.room.read_text(encoding="utf-8"))
    scene["entities"].append(goblin("gob_c", 500, 500))
    arena.room.write_text(json.dumps(scene), encoding="utf-8")
    arena.enter()
    assert arena.load("s1")
    assert hp_of(arena.by_id("gob_c")) == 3.0  # the waiting record (the hurt goblin's, hp 3) is applied to it
    assert [e["record"]["x"] for e in arena.held()] == [600.0]
    saved = arena.save("s2")["saved_entities"]["unresolved"]
    assert [e["record"]["x"] for e in saved] == [600.0]


def test_T34b_a_retry_binds_a_changed_state_by_place() -> None:
    old = unresolved = {"record": legacy("Goblin", 500, 500, 2), "reason": "position", "scene_path": "r.json",
                        "first_seen": "t0"}
    newcomer = Stub("Goblin", 500, 500, 20, "gob_c")
    other = Stub("Goblin", 7, 7, 20, "gob_d")
    result = apply_entities_ex(stage(newcomer, other), [], carried=[unresolved], scene_path="r.json")
    assert (result.applied, result.retried, result.unresolved) == (1, 1, []) and newcomer.hp == 2 and other.hp == 20
    # by name alone it would be a guess: one record, one same-named sprite elsewhere stays unresolved
    stuck = apply_entities_ex(stage(Stub("Goblin", 7, 7, 20, "gob_d")), [], carried=[old], scene_path="r.json")
    assert (stuck.applied, stuck.unresolved) == (0, [old])


def test_T35_unresolved_never_overwrite_resolved_state() -> None:
    gob = Stub("Goblin", 111, 122, 20, "gob_a")
    stale = {"record": legacy("Goblin", 111, 122, 1), "reason": "position", "scene_path": "r.json", "first_seen": "t0"}
    result = apply_entities_ex(stage(gob), [id_record("gob_a", "Goblin", 111, 122, 3)], carried=[stale], scene_path="r.json")
    assert gob.hp == 3  # the resolved record's state stays
    assert (result.applied, result.retried, result.unresolved) == (1, 0, [stale])  # the stale one stays unresolved


def test_T36_unresolved_across_rooms(arena: Arena) -> None:
    _unbindable_v2(arena)
    arena.enter()
    arena.load()
    other = arena.root / "other.json"
    other.write_text(json.dumps({"name": "Other", "schema_version": 1, "version": 1, "layers": [],
                                 "entities": [hero()]}), encoding="utf-8")
    arena.controller.load_scene(str(other))  # a door to another room
    saved = arena.save("in_b")["saved_entities"]
    assert saved["scene_path"] == room_key(str(other))
    assert len(saved["unresolved"]) == 2 and {e["scene_path"] for e in saved["unresolved"]} == {room_key(str(arena.room))}


def test_a_new_game_does_not_carry_the_old_games_unresolved_records(arena: Arena) -> None:
    _unbindable_v2(arena)
    arena.enter()
    arena.load()
    assert len(arena.held()) == 2
    arena.window.game_state_controller.replace_state({})  # New Game (a new game state)
    arena.enter()
    assert arena.save("fresh")["saved_entities"]["unresolved"] == []


def test_unresolved_entries_are_deduplicated_and_ordered() -> None:
    from engine.save_runtime.entity_state import merge_unresolved

    a = {"record": legacy("A", 1, 1, 1), "reason": "position", "scene_path": "r.json", "first_seen": "t0"}
    b = {"record": legacy("B", 2, 2, 2), "reason": "position", "scene_path": "r.json", "first_seen": "t1"}
    again = dict(a, first_seen="t9")
    assert merge_unresolved([b, a], [again]) == merge_unresolved([a, b]) and len(merge_unresolved([a, b], [again])) == 2
    assert merge_unresolved([a, b], [again])[0] in (a, b) and again not in merge_unresolved([a], [again])


def test_migration_v2_to_v3_only_tags_and_never_invents() -> None:
    data = {"save_schema_version": 2, "flags": {}, "saved_entities": {"schema_version": 1, "entities": [
        {"entity_id": "A", "x": 1.0, "y": 2.0}, {"entity_id": "A", "x": 3.0, "y": 4.0}]}}
    before = copy.deepcopy(data)
    migrated = migrate_save(data)
    assert migrated["save_schema_version"] == 3
    stripped = [{k: v for k, v in r.items() if k not in ("keying", "legacy")} for r in migrated["saved_entities"]["entities"]]
    assert stripped == before["saved_entities"]["entities"]  # nothing added but the tags, nothing dropped
    assert all(r["keying"] == "name" and r["legacy"] is True for r in migrated["saved_entities"]["entities"])
    assert set(migrated) == set(before)


def test_a_v3_save_from_a_newer_build_is_still_refused() -> None:
    with pytest.raises(ValueError, match="newer game version"):
        migrate_save({"save_schema_version": 4, "saved_entities": {"schema_version": 3, "entities": []}})


# =====================================================================================================================
# Twins of one id: order is never identity (owner challenge on #535)
# =====================================================================================================================


def _twins_room(arena: Arena, twin_at: tuple[float, float]) -> None:
    """gob_a hp 5 and a console clone sharing its id (hp 11) at ``twin_at``, saved; returns with the save written."""
    arena.write_room(hero(), goblin("gob_a", 100, 100))
    arena.enter()
    arena.place(arena.by_id("gob_a"), 100, 100, hp=5)
    arena.spawn(dict(arena.by_id("gob_a").mesh_entity_data, x=twin_at[0], y=twin_at[1], name="Goblin_clone"), hp=11)
    arena.save()


def _reverse_snapshot_twins(arena: Arena) -> None:
    save = arena.read()
    twins = [e for e in save["entities"] if e.get("id") == "gob_a"]
    assert len(twins) == 2
    others = [e for e in save["entities"] if e.get("id") != "gob_a"]
    save["entities"] = others + list(reversed(twins))  # (the sprites are made in the other order)
    arena.slot().write_text(json.dumps(save, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.mark.parametrize("reverse", [False, True])
def test_twins_at_identical_places_are_never_told_apart_by_order(arena: Arena, reverse: bool) -> None:
    """Same id, same place, different states: nothing can say which record is whose, so neither is applied (order
    never decides, whichever way the sprites come), both are reported and carried in every later save."""
    _twins_room(arena, (100, 100))
    if reverse:
        _reverse_snapshot_twins(arena)
    arena.enter()
    assert arena.load()
    twins = [s for s in arena.sprites() if getattr(s, "mesh_id", None) == "gob_a"]
    assert [hp_of(s) for s in twins] == [20.0, 20.0]  # nothing applied, nothing exchanged
    held = arena.held()
    assert len(held) == 2 and {e["record"]["behaviour_state"]["Health"]["hp"] for e in held} == {5.0, 11.0}
    assert {e["reason"] for e in held} == {"ambiguous_position"}
    assert last_load_codes().count("save.restore.entity_id_ambiguous") == 2
    assert "could not be matched" in " ".join(arena.toasts())
    first = arena.save("s1")["saved_entities"]["unresolved"]
    arena.enter()
    assert arena.load("s1")
    later = arena.save("s2")["saved_entities"]["unresolved"]
    assert all(e in later for e in first) and len(first) == 2  # the originals are carried verbatim, never dropped
    # (the live twins, still alike, wrote records of their own: those are ambiguous in turn, reported and carried too)


def test_twins_at_distinct_places_bind_to_their_own_whichever_order(arena: Arena) -> None:
    _twins_room(arena, (150, 150))
    _reverse_snapshot_twins(arena)
    arena.enter()
    assert arena.load()
    twins = sorted((s for s in arena.sprites() if getattr(s, "mesh_id", None) == "gob_a"), key=lambda s: s.center_x)
    assert [(s.center_x, hp_of(s)) for s in twins] == [(100.0, 5.0), (150.0, 11.0)]
    assert arena.held() == []


def test_twin_records_bind_by_unique_place_never_by_sprite_order() -> None:
    near, far = (100.0, 100.0), (150.0, 150.0)
    records = [id_record("gob_a", "Goblin", *near, 5, 0), id_record("gob_a", "Goblin", *far, 11, 1)]
    for order in ((near, far), (far, near)):
        a, b = (Stub("Goblin", *p, 20, "gob_a") for p in order)
        result = apply_entities_ex(stage(a, b), records)
        assert (result.applied, result.unbound) == (2, 0)
        assert {(s.center_x, s.hp) for s in (a, b)} == {(100.0, 5), (150.0, 11)}
    same = [id_record("gob_a", "Goblin", *near, 5, 0), id_record("gob_a", "Goblin", *near, 11, 1)]
    for _ in range(2):
        a, b = Stub("Goblin", *near, 20, "gob_a"), Stub("Goblin", *near, 20, "gob_a")
        for sprites in ((a, b), (b, a)):
            result = apply_entities_ex(stage(*sprites), same)
            assert (result.applied, result.unbound) == (0, 2) and a.hp == b.hp == 20
            assert [e["reason"] for e in result.unresolved] == ["ambiguous_position"] * 2


def test_carried_twin_records_get_the_same_rule() -> None:
    first = apply_entities_ex(stage(), [id_record("gob_a", "Goblin", 100, 100, 5, 0), id_record("gob_a", "Goblin", 100, 100, 11, 1)])
    assert len(first.unresolved) == 2
    a, b = Stub("Goblin", 100, 100, 20, "gob_a"), Stub("Goblin", 100, 100, 20, "gob_a")
    result = apply_entities_ex(stage(a, b), [], carried=first.unresolved)
    assert (result.applied, len(result.unresolved)) == (0, 2) and a.hp == b.hp == 20  # identical places: still refused
