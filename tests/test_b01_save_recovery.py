"""B-01: a v2 save is never lost to the v3 migration.

Loading never rewrites a v2 slot; before the first v3 save overwrites one, a copy is written and verified (SHA-256 of a
fresh read) or the save is refused with the slot byte-identical; an existing backup is never replaced; a v3 save is
refused by a v2-only build (the existing newer-version error). Real saves through the production SaveManager and a
hidden GameWindow (tests/_b01_arena.py); the T-numbers are the design's test plan.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from engine.save_runtime import io as save_io
from tests._b01_arena import Arena, close_window, hp_of, make_window, sha
from tests.test_b01_save_identity import as_v2, last_load_codes, two_goblins, write_v2

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def v2_slot(arena: Arena, name: str = "slot1") -> Path:
    """A player's old slot: two goblins (one hurt and moved) saved by the v2 engine."""
    two_goblins(arena)
    return write_v2(arena, arena.save(name), name)


def backups(arena: Arena) -> list[Path]:
    return sorted(arena.saves.glob("*.bak"))


def test_T20_loading_a_v2_save_never_rewrites_it(arena: Arena) -> None:
    slot = v2_slot(arena)
    before = sha(slot)
    arena.enter()
    assert arena.load()
    assert sha(slot) == before
    assert sorted(p.name for p in arena.saves.iterdir()) == ["slot1.json"]  # no sidecar, no backup, nothing
    assert hp_of(arena.by_id("gob_a")) == 3.0  # (and it did load)


def test_T20b_loading_an_unmatched_v2_save_leaves_it_byte_identical(arena: Arena) -> None:
    slot = v2_slot(arena)
    old = json.loads(slot.read_text(encoding="utf-8"))
    for record in old["saved_entities"]["entities"]:
        if record["entity_id"] == "Goblin":
            record["x"] += 1000.0  # no live goblin stands there
    slot.write_text(json.dumps(old, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = sha(slot)
    arena.enter()
    assert arena.load() and len(arena.held()) == 2
    assert sha(slot) == before and [p.name for p in arena.saves.iterdir()] == ["slot1.json"]


def test_T21_first_v3_save_makes_a_verified_v2_bak(arena: Arena) -> None:
    slot = v2_slot(arena)
    original = slot.read_bytes()
    arena.enter()
    arena.load()
    assert arena.manager.save_game("slot1")
    backup = arena.saves / "slot1.json.v2.bak"
    assert backup.read_bytes() == original
    assert json.loads(slot.read_text(encoding="utf-8"))["save_schema_version"] == 3
    assert [r["keying"] for r in arena.records()][0] in ("id", "name")


def test_T22_the_second_save_keeps_the_first_backup(arena: Arena) -> None:
    slot = v2_slot(arena)
    original = slot.read_bytes()
    arena.enter()
    arena.load()
    assert arena.manager.save_game("slot1")
    arena.place(arena.by_id("gob_a"), 5, 5, hp=1)  # play on
    assert arena.manager.save_game("slot1") and arena.manager.save_game("slot1")
    assert backups(arena) == [arena.saves / "slot1.json.v2.bak"]
    assert (arena.saves / "slot1.json.v2.bak").read_bytes() == original  # progress made since is not in it, by design


def test_T23_a_backup_that_cannot_be_written_refuses_the_save(arena: Arena, capsys: pytest.CaptureFixture[str]) -> None:
    slot = v2_slot(arena)
    before = sha(slot)
    (arena.saves / "slot1.json.v2.bak").mkdir()  # something the backup can't replace or read
    arena.enter()
    arena.load()
    arena.window.player_hud.clear_toasts()
    assert arena.manager.save_game("slot1") is False
    assert sha(slot) == before  # the v2 slot is byte-identical
    assert "save.write.v2_backup_failed" in capsys.readouterr().err
    assert any("wasn't saved over the old save" in t for t in arena.toasts())
    assert "Game saved" not in arena.toasts()
    assert arena.manager.save_game("other_slot")  # saving elsewhere still works
    (arena.saves / "slot1.json.v2.bak").rmdir()  # the fault clears: the retry backs up and saves
    assert arena.manager.save_game("slot1")
    assert (arena.saves / "slot1.json.v2.bak").exists() and json.loads(slot.read_text(encoding="utf-8"))["save_schema_version"] == 3


def test_T31_a_backup_that_does_not_verify_refuses_the_save(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    slot = v2_slot(arena)
    before = sha(slot)

    def corrupt_copy(target: Path, data: bytes) -> None:
        target.write_bytes(data[:-1] + b"!")  # (a copy that silently differs)

    monkeypatch.setattr(save_io, "_write_backup_bytes", corrupt_copy)
    arena.enter()
    arena.load()
    assert arena.manager.save_game("slot1") is False
    assert sha(slot) == before
    assert backups(arena) == []  # the bad copy was removed: no backup name is left holding wrong bytes
    monkeypatch.undo()
    assert arena.manager.save_game("slot1") and (arena.saves / "slot1.json.v2.bak").read_bytes() != b""


def test_T32_an_existing_different_backup_is_never_replaced(arena: Arena) -> None:
    slot = v2_slot(arena)
    original = slot.read_bytes()
    older = arena.saves / "slot1.json.v2.bak"
    older.write_bytes(b'{"an": "older backup"}')
    arena.enter()
    arena.load()
    assert arena.manager.save_game("slot1")
    assert older.read_bytes() == b'{"an": "older backup"}'
    import hashlib

    named = arena.saves / f"slot1.json.v2.{hashlib.sha256(original).hexdigest()[:8]}.bak"
    assert named.read_bytes() == original and json.loads(slot.read_text(encoding="utf-8"))["save_schema_version"] == 3


def test_a_failed_write_after_the_backup_leaves_the_v2_slot_untouched(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    slot = v2_slot(arena)
    before = sha(slot)

    def fail(*_a: Any, **_k: Any) -> None:
        raise OSError("disk full")

    arena.enter()
    arena.load()
    monkeypatch.setattr(save_io, "write_json_atomic", fail)
    assert arena.manager.save_game("slot1") is False
    assert sha(slot) == before  # the slot is still the v2 original; the backup exists beside it
    assert (arena.saves / "slot1.json.v2.bak").read_bytes() == slot.read_bytes()
    monkeypatch.undo()
    assert arena.manager.save_game("slot1")  # rollback complete: a retry succeeds and finds its backup already verified
    assert backups(arena) == [arena.saves / "slot1.json.v2.bak"]


def test_a_save_that_is_already_v3_is_not_backed_up(arena: Arena) -> None:
    two_goblins(arena)
    assert arena.manager.save_game("slot1") and arena.manager.save_game("slot1")
    assert backups(arena) == []


def test_a_slot_that_cannot_be_read_as_a_save_is_backed_up_too(arena: Arena) -> None:
    two_goblins(arena)
    arena.saves.mkdir(exist_ok=True)
    (arena.saves / "slot1.json").write_bytes(b"not json at all")
    assert arena.manager.save_game("slot1")
    assert (arena.saves / "slot1.json.v2.bak").read_bytes() == b"not json at all"


def test_T24_a_legacy_installation_save_is_never_touched(arena: Arena, tmp_path: Path) -> None:
    """An older export's save in its installation folder is read, never written: a v3 save goes to the player's own
    folder, and no backup is made beside the installed file."""
    install = tmp_path / "install_saves"
    install.mkdir()
    two_goblins(arena)
    legacy = install / "slot1.json"
    legacy.write_text(json.dumps(as_v2(arena.save("scratch")), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (arena.saves / "scratch.json").unlink()
    arena.manager.legacy_dir = install
    before = sha(legacy)
    arena.enter()
    assert arena.load()
    assert hp_of(arena.by_id("gob_a")) == 3.0
    assert arena.manager.save_game("slot1")
    assert sha(legacy) == before and sorted(p.name for p in install.iterdir()) == ["slot1.json"]
    assert backups(arena) == []  # (there was no per-player v2 file to overwrite)
    assert json.loads((arena.saves / "slot1.json").read_text(encoding="utf-8"))["save_schema_version"] == 3


def test_T26_a_save_from_a_newer_build_is_refused_and_nothing_changes(arena: Arena) -> None:
    two_goblins(arena)
    save = arena.save()
    save["save_schema_version"] = 4
    arena.slot().write_text(json.dumps(save, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before, state = sha(arena.slot()), arena.state()
    assert arena.manager.load_game("slot1") is False
    assert sha(arena.slot()) == before and arena.state() == state  # nothing half-loaded
    assert "save.load.schema_migration_error" in last_load_codes() or "save.load.schema_validation_error" in last_load_codes()
    assert backups(arena) == []


def test_T27_the_v2_bak_is_a_loadable_save(arena: Arena) -> None:
    slot = v2_slot(arena)
    arena.enter()
    arena.load()
    first = arena.state()
    arena.manager.save_game("slot1")
    shutil.copyfile(arena.saves / "slot1.json.v2.bak", arena.saves / "restored.json")  # a player's manual recovery
    assert sha(arena.saves / "restored.json") != sha(slot)  # (the slot is v3 now)
    arena.enter()
    assert arena.load("restored")
    assert arena.state() == first


def test_recovering_from_the_bak_then_saving_again_does_not_lose_either(arena: Arena) -> None:
    """Copy the backup over the slot, play on, save: the slot is v2 again, so it is backed up again, under a new name
    when it differs from the backup already there."""
    slot = v2_slot(arena)
    first_bytes = slot.read_bytes()
    arena.enter()
    arena.load()
    arena.manager.save_game("slot1")
    v3_bytes = slot.read_bytes()
    shutil.copyfile(arena.saves / "slot1.json.v2.bak", slot)
    assert slot.read_bytes() == first_bytes
    arena.enter()
    arena.load()
    arena.place(arena.by_id("gob_a"), 9, 9, hp=2)
    assert arena.manager.save_game("slot1")
    assert (arena.saves / "slot1.json.v2.bak").read_bytes() == first_bytes  # (same bytes: that backup is reused)
    assert v3_bytes != slot.read_bytes() and len(backups(arena)) == 1
