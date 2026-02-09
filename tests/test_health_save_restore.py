"""Tests for Health behaviour save/restore.

Covers:
- saveable_state() returns correct fields with STATE_VERSION
- restore_state() roundtrip preserves all fields
- restore_state() clamps hp to [0, max_hp]
- Damaged entity roundtrip preserves HP
- Dead entity roundtrip preserves dead flag
- Missing fields use sensible defaults
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from engine.behaviours.health import Health


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_health(**config: Any) -> Health:
    """Create a Health behaviour with a minimal mock entity + window."""
    entity = MagicMock()
    entity.mesh_entity_data = {}
    entity.mesh_tag = "enemy"
    entity.mesh_name = "goblin"

    window = MagicMock()
    window.engine_config = None  # Disable player stats lookup

    return Health(entity, window, **config)


# --------------------------------------------------------------------------- #
# saveable_state
# --------------------------------------------------------------------------- #


class TestHealthSaveableState:
    def test_returns_dict_with_version(self):
        h = _make_health(max_hp=10, hp=10)
        state = h.saveable_state()
        assert isinstance(state, dict)
        assert state["version"] == Health.STATE_VERSION

    def test_contains_all_fields(self):
        h = _make_health(max_hp=20, hp=15, invulnerable=True)
        state = h.saveable_state()
        assert state["hp"] == 15.0
        assert state["max_hp"] == 20.0
        assert state["invulnerable"] is True
        assert state["dead"] is False

    def test_dead_flag_after_lethal_damage(self):
        h = _make_health(max_hp=5, hp=5)
        h.apply_damage(100)
        state = h.saveable_state()
        assert state["dead"] is True
        assert state["hp"] <= 0


# --------------------------------------------------------------------------- #
# restore_state roundtrip
# --------------------------------------------------------------------------- #


class TestHealthRestoreRoundtrip:
    def test_full_roundtrip(self):
        h1 = _make_health(max_hp=50, hp=50)
        h1.apply_damage(15)
        saved = h1.saveable_state()

        h2 = _make_health(max_hp=1, hp=1)
        h2.restore_state(saved)

        assert h2.hp == h1.hp
        assert h2.max_hp == h1.max_hp
        assert h2.invulnerable == h1.invulnerable
        assert h2._dead == h1._dead

    def test_roundtrip_dead_entity(self):
        h1 = _make_health(max_hp=3, hp=3)
        h1.apply_damage(999)
        saved = h1.saveable_state()

        h2 = _make_health(max_hp=100, hp=100)
        h2.restore_state(saved)

        assert h2._dead is True
        assert h2.hp <= 0

    def test_roundtrip_invulnerable(self):
        h1 = _make_health(max_hp=10, hp=10, invulnerable=True)
        saved = h1.saveable_state()

        h2 = _make_health()
        h2.restore_state(saved)
        assert h2.invulnerable is True


# --------------------------------------------------------------------------- #
# restore_state edge cases
# --------------------------------------------------------------------------- #


class TestHealthRestoreEdgeCases:
    def test_hp_clamped_to_max(self):
        h = _make_health(max_hp=5, hp=5)
        h.restore_state({"max_hp": 10, "hp": 999})
        assert h.hp == 10.0  # clamped to max_hp

    def test_hp_clamped_to_zero(self):
        h = _make_health(max_hp=5, hp=5)
        h.restore_state({"max_hp": 10, "hp": -50})
        assert h.hp == 0.0

    def test_missing_hp_defaults_to_max(self):
        h = _make_health(max_hp=5, hp=5)
        h.restore_state({"max_hp": 20})
        assert h.hp == 20.0
        assert h.max_hp == 20.0

    def test_missing_invulnerable_defaults_false(self):
        h = _make_health(max_hp=5, hp=5, invulnerable=True)
        h.restore_state({"max_hp": 5, "hp": 5})
        assert h.invulnerable is False

    def test_missing_dead_inferred_from_hp(self):
        h = _make_health(max_hp=5, hp=5)
        h.restore_state({"max_hp": 5, "hp": 0})
        assert h._dead is True

    def test_empty_state_preserves_max_hp(self):
        h = _make_health(max_hp=42, hp=42)
        h.restore_state({})
        assert h.max_hp == 42.0


# --------------------------------------------------------------------------- #
# STATE_VERSION constant exists
# --------------------------------------------------------------------------- #


def test_state_version_is_positive_int():
    assert isinstance(Health.STATE_VERSION, int)
    assert Health.STATE_VERSION >= 1
