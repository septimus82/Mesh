"""Tests for save serialization strictness (no silent swallowing).

Covers:
- serialize_entity collects warnings for failed saveable_state()
- serialize_entity strict mode raises SaveSerializationError
- apply_entity_state logs warnings (does not silently swallow)
- serialize_entities propagates strict flag
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from engine.save_runtime.entity_state import (
    SavedEntityState,
    SaveSerializationError,
    apply_entity_state,
    serialize_entities,
    serialize_entity,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@dataclass
class _Sprite:
    mesh_name: str = "test_npc"
    center_x: float = 10.0
    center_y: float = 20.0
    mesh_tag: str | None = None
    mesh_tags: list[str] = field(default_factory=list)
    mesh_entity_data: dict[str, Any] = field(default_factory=dict)
    mesh_animator: Any = None
    mesh_behaviours_runtime: list[Any] = field(default_factory=list)


class _GoodBehaviour:
    def saveable_state(self) -> dict[str, Any]:
        return {"hp": 10}

    def restore_state(self, state: dict[str, Any]) -> None:
        pass


class _BadBehaviour:
    """Behaviour whose saveable_state() always raises."""

    def saveable_state(self) -> dict[str, Any]:
        raise RuntimeError("serialize boom")

    def restore_state(self, state: dict[str, Any]) -> None:
        raise RuntimeError("restore boom")


class _BadRestoreBehaviour:
    """Behaviour whose restore_state() always raises."""

    def saveable_state(self) -> dict[str, Any]:
        return {"val": 42}

    def restore_state(self, state: dict[str, Any]) -> None:
        raise RuntimeError("restore boom")


# --------------------------------------------------------------------------- #
# serialize_entity: error collection
# --------------------------------------------------------------------------- #


class TestSerializeEntityErrorCollection:
    def test_bad_behaviour_collects_error_and_continues(self):
        sprite = _Sprite(
            mesh_behaviours_runtime=[_GoodBehaviour(), _BadBehaviour()],
        )
        errors: list[str] = []
        result = serialize_entity(sprite, errors=errors)

        assert result is not None
        # Good behaviour state should be captured
        assert "_GoodBehaviour" in result.behaviour_state
        # Error collected
        assert len(errors) == 1
        assert "serialize boom" in errors[0]
        assert "_BadBehaviour" in errors[0]

    def test_bad_behaviour_writes_to_stderr(self, capsys):
        sprite = _Sprite(
            mesh_behaviours_runtime=[_BadBehaviour()],
        )
        serialize_entity(sprite)
        captured = capsys.readouterr()
        assert "serialize boom" in captured.err
        assert "_BadBehaviour" in captured.err

    def test_no_error_on_healthy_behaviours(self):
        sprite = _Sprite(
            mesh_behaviours_runtime=[_GoodBehaviour()],
        )
        errors: list[str] = []
        result = serialize_entity(sprite, errors=errors)
        assert result is not None
        assert errors == []
        assert "_GoodBehaviour" in result.behaviour_state

    def test_errors_none_default_still_logs(self, capsys):
        """When errors=None (default), stderr warning still emitted."""
        sprite = _Sprite(mesh_behaviours_runtime=[_BadBehaviour()])
        result = serialize_entity(sprite)
        assert result is not None
        assert "serialize boom" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# serialize_entity: strict mode
# --------------------------------------------------------------------------- #


class TestSerializeEntityStrictMode:
    def test_strict_raises_on_bad_behaviour(self):
        sprite = _Sprite(mesh_behaviours_runtime=[_BadBehaviour()])
        with pytest.raises(SaveSerializationError, match="serialize boom"):
            serialize_entity(sprite, strict=True)

    def test_strict_includes_entity_id(self):
        sprite = _Sprite(
            mesh_name="my_goblin",
            mesh_behaviours_runtime=[_BadBehaviour()],
        )
        with pytest.raises(SaveSerializationError, match="my_goblin"):
            serialize_entity(sprite, strict=True)

    def test_strict_ok_with_good_behaviours(self):
        sprite = _Sprite(mesh_behaviours_runtime=[_GoodBehaviour()])
        result = serialize_entity(sprite, strict=True)
        assert result is not None
        assert "_GoodBehaviour" in result.behaviour_state


# --------------------------------------------------------------------------- #
# serialize_entities propagates strict
# --------------------------------------------------------------------------- #


class TestSerializeEntitiesStrict:
    def _make_controller(self, sprites):
        class _SC:
            all_sprites = sprites
        return _SC()

    def test_strict_raises_through_serialize_entities(self):
        sprites = [_Sprite(mesh_behaviours_runtime=[_BadBehaviour()])]
        with pytest.raises(SaveSerializationError, match="serialize boom"):
            serialize_entities(self._make_controller(sprites), strict=True)

    def test_non_strict_collects_and_continues(self, capsys):
        sprites = [
            _Sprite(mesh_name="a", mesh_behaviours_runtime=[_BadBehaviour()]),
            _Sprite(mesh_name="b", mesh_behaviours_runtime=[_GoodBehaviour()]),
        ]
        result = serialize_entities(self._make_controller(sprites))
        # Both entities serialized (b has good state, a has empty behaviour_state)
        ids = [e["entity_id"] for e in result]
        assert "a" in ids
        assert "b" in ids
        assert "serialize boom" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# apply_entity_state: warning on restore failure
# --------------------------------------------------------------------------- #


class TestApplyEntityStateWarnings:
    def test_restore_failure_logs_warning(self, capsys):
        sprite = _Sprite(
            mesh_behaviours_runtime=[_BadRestoreBehaviour()],
        )
        state = SavedEntityState(
            entity_id="test_npc",
            x=50.0,
            y=60.0,
            behaviour_state={"_BadRestoreBehaviour": {"val": 42}},
        )
        result = apply_entity_state(sprite, state)
        assert result is True  # Position etc still applied
        captured = capsys.readouterr()
        assert "restore boom" in captured.err
        assert "_BadRestoreBehaviour" in captured.err

    def test_position_applied_despite_restore_failure(self):
        sprite = _Sprite(
            mesh_behaviours_runtime=[_BadRestoreBehaviour()],
        )
        state = SavedEntityState(
            entity_id="test_npc",
            x=99.0,
            y=88.0,
            behaviour_state={"_BadRestoreBehaviour": {"val": 1}},
        )
        apply_entity_state(sprite, state)
        assert sprite.center_x == 99.0
        assert sprite.center_y == 88.0

    def test_apply_fully_broken_sprite_logs_warning(self, capsys):
        """A sprite that raises on center_x assignment."""

        class _BrokenSprite:
            mesh_name = "oops"

            @property
            def center_x(self):
                return 0.0

            @center_x.setter
            def center_x(self, _):
                raise AttributeError("frozen")

        state = SavedEntityState(entity_id="oops", x=1.0, y=2.0)
        result = apply_entity_state(_BrokenSprite(), state)
        assert result is False
        assert "frozen" in capsys.readouterr().err
