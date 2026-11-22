"""AS-2: a slot written by a newer build is never overwritten by this one (audit finding).

Real saves through the production SaveManager and a hidden GameWindow (tests/_b01_arena.py).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from engine import optional_arcade
from engine.save_runtime.schema import SAVE_SCHEMA_VERSION
from tests._b01_arena import Arena, close_window, make_window
from tests.test_b01_save_identity import two_goblins

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _newer_slot(arena: Arena, name: str = "slot1", version: int = SAVE_SCHEMA_VERSION + 1) -> Path:
    two_goblins(arena)
    save = arena.save(name)
    save["save_schema_version"] = version
    save["from_the_future"] = {"keep": "me"}
    arena.slot(name).write_text(json.dumps(save, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return arena.slot(name)


@pytest.mark.parametrize("name", ["slot1", "quicksave", "autosave"])
def test_saving_over_a_newer_save_is_refused_and_the_bytes_stay(arena: Arena, name: str) -> None:
    slot = _newer_slot(arena, name)
    before = slot.read_bytes()
    arena.enter()
    assert arena.manager.load_game(name) is False  # (this build can't read it)
    assert arena.manager.save_game(name) is False
    assert slot.read_bytes() == before
    assert not [p for p in arena.saves.iterdir() if p.suffix in (".bak", ".tmp")]  # (diagnostic sidecars aside)
    assert any("newer game version" in t for t in arena.toasts())


def test_a_much_newer_save_is_refused_too(arena: Arena) -> None:
    slot = _newer_slot(arena, version=99)
    before = slot.read_bytes()
    assert arena.manager.save_game("slot1") is False
    assert slot.read_bytes() == before


def test_another_slot_still_saves_after_a_refusal(arena: Arena) -> None:
    slot = _newer_slot(arena)
    before = slot.read_bytes()
    assert arena.manager.save_game("slot1") is False
    assert arena.manager.save_game("slot2") is True
    assert arena.read("slot2")["save_schema_version"] == SAVE_SCHEMA_VERSION
    assert slot.read_bytes() == before


def test_a_current_schema_slot_is_still_overwritten(arena: Arena) -> None:
    two_goblins(arena)
    arena.save()
    first = arena.slot().read_bytes()
    arena.window.save_manager._last_saved_signature = None
    assert arena.manager.save_game("slot1") is True
    assert arena.read()["save_schema_version"] == SAVE_SCHEMA_VERSION
    assert arena.slot().exists() and first
