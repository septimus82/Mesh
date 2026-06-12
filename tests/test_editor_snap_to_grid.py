"""Fast-tier tests for Selection: Snap to Grid… editor authoring action.

Validates:
- nearest (half-up), floor, ceil rounding modes
- axes x, y, xy
- deterministic sorted-ID application
- correct moved/skipped counts
- half-up tie-breaking (ties away from zero)
- negative coordinate symmetry
- entities without position are skipped
- player entities are skipped
- empty selection returns ok=false
- step <= 0 returns ok=false
- command palette action wiring + input parsing
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

def _make_entities(*specs: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a list of entity dicts from compact specs."""
    out: list[dict[str, Any]] = []
    for s in specs:
        ent: dict[str, Any] = {"id": s["id"]}
        if "name" in s:
            ent["name"] = s["name"]
        for key in ("x", "y", "width", "height"):
            if key in s:
                ent[key] = s[key]
        if "tags" in s:
            ent["tags"] = list(s["tags"])
        if s.get("player"):
            ent.setdefault("tags", []).append("player")
        out.append(ent)
    return out


class _FakeSceneController:
    """Mimics the authoring surface of SceneController for tests."""

    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self._authored: dict[str, Any] = {"entities": entities}
        self._applied: dict[str, Any] | None = None

    def get_authored_scene_payload(self) -> dict[str, Any]:
        return self._authored

    def apply_authored_scene_payload(self, payload: dict[str, Any]) -> None:
        self._applied = payload
        self._authored = payload

    def debug_snap_to_grid(
        self,
        entity_ids: list[str],
        step: int,
        axes: str = "xy",
        mode: str = "nearest",
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_snap_to_grid(
            self, entity_ids, step, axes=axes, mode=mode,
        )

    @property
    def entities_snapshot(self) -> list[dict[str, Any]]:
        return self._authored.get("entities", [])


def _patch_authoring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire entity_ops internals to our _FakeSceneController."""
    import engine.scene_runtime.authoring.entity_ops as _ops

    monkeypatch.setattr(
        _ops,
        "get_authored_scene_payload",
        lambda controller: controller.get_authored_scene_payload(),
    )
    monkeypatch.setattr(
        _ops,
        "debug_apply_authored_scene_payload",
        lambda controller, payload: controller.apply_authored_scene_payload(payload),
    )


def _ent_by_id(sc: _FakeSceneController, eid: str) -> dict[str, Any]:
    return next(e for e in sc.entities_snapshot if e["id"] == eid)


# ---------------------------------------------------------------------------
# Core snap tests – nearest (half-up)
# ---------------------------------------------------------------------------

class TestSnapNearest:
    """Nearest-mode snapping with half-up rounding."""

    def test_snap_xy_nearest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities(
            {"id": "a", "x": 17.0, "y": 23.0},
            {"id": "b", "x": 32.0, "y": 48.0},  # already on grid
        )
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a", "b"], step=16, axes="xy", mode="nearest")
        assert result["ok"] is True
        assert result["moved"] == 1  # only a moves; b already on grid
        assert result["skipped"] == 0
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(16.0)
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(16.0)  # 23/16=1.4375 -> round to 1 -> 16
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(32.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(48.0)

    def test_snap_x_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 17.0, "y": 23.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="x", mode="nearest")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(16.0)
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(23.0)  # unchanged

    def test_snap_y_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 17.0, "y": 23.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="y", mode="nearest")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(17.0)  # unchanged
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(16.0)

    def test_half_up_tie_positive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tie at exactly half-step rounds UP (away from zero) for positive."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        # 8 is exactly halfway between 0 and 16 → should round to 16 (away from zero)
        entities = _make_entities({"id": "a", "x": 8.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="x", mode="nearest")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(16.0)

    def test_half_up_tie_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tie at exactly half-step rounds AWAY from zero for negative."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        # -8 is exactly halfway between -16 and 0 → should round to -16 (away from zero)
        entities = _make_entities({"id": "a", "x": -8.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="x", mode="nearest")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(-16.0)


# ---------------------------------------------------------------------------
# Floor / ceil modes
# ---------------------------------------------------------------------------

class TestSnapFloorCeil:
    """Floor and ceil rounding modes."""

    def test_floor_x(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 25.0, "y": 50.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="x", mode="floor")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(16.0)
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(50.0)

    def test_ceil_y(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 50.0, "y": 25.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="y", mode="ceil")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(32.0)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(50.0)

    def test_floor_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": -25.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="x", mode="floor")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(-32.0)  # floor(-1.5625) = -2 → -32

    def test_ceil_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": -25.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="x", mode="ceil")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(-16.0)  # ceil(-1.5625) = -1 → -16


# ---------------------------------------------------------------------------
# Edge cases & skips
# ---------------------------------------------------------------------------

class TestSnapEdgeCases:
    """Skip / failure edge cases."""

    def test_skip_player_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities(
            {"id": "a", "x": 17.0, "y": 23.0, "player": True},
            {"id": "b", "x": 17.0, "y": 23.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a", "b"], step=16, axes="xy", mode="nearest")
        assert result["ok"] is True
        assert result["moved"] == 1  # only b
        assert result["skipped"] == 1
        # Player untouched
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(17.0)

    def test_skip_no_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities(
            {"id": "a"},  # no x/y
            {"id": "b", "x": 17.0, "y": 23.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a", "b"], step=16)
        assert result["skipped"] == 1
        assert result["moved"] == 1

    def test_empty_selection_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        sc = _FakeSceneController([])
        result = debug_snap_to_grid(sc, [], step=16)
        assert result["ok"] is False

    def test_zero_step_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 17.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=0)
        assert result["ok"] is False

    def test_negative_step_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 17.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=-8)
        assert result["ok"] is False

    def test_invalid_axes_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 17.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, axes="z")
        assert result["ok"] is False

    def test_invalid_mode_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 17.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16, mode="round_half_even")
        assert result["ok"] is False

    def test_already_on_grid_no_move(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities({"id": "a", "x": 32.0, "y": 64.0})
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a"], step=16)
        assert result["ok"] is False  # no entities moved
        assert result["moved"] == 0


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------

class TestSnapDeterministic:
    """Ensure sorted-ID deterministic application."""

    def test_sorted_id_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        # Insert entities out of alphabetical order
        entities = _make_entities(
            {"id": "c", "x": 5.0, "y": 5.0},
            {"id": "a", "x": 7.0, "y": 7.0},
            {"id": "b", "x": 3.0, "y": 3.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["c", "a", "b"], step=8, axes="xy", mode="nearest")
        assert result["ok"] is True
        assert result["moved"] == 3
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(8.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Command palette action wiring
# ---------------------------------------------------------------------------

class TestSnapCommandPaletteAction:
    """Validate the action_snap_to_grid registry function."""

    def _make_world(self, entities: list[dict[str, Any]]) -> SimpleNamespace:
        sc = _FakeSceneController(entities)
        non_player_ids = [e["id"] for e in entities if "player" not in (e.get("tags") or [])]

        class World(SimpleNamespace):
            scene_controller = sc
            _undo_pushed: list[str] = []
            _dirty: list[str] = []

            def push_undo_frame(self, label: str) -> None:
                self._undo_pushed.append(label)

            def mark_scene_dirty(self, label: str) -> None:
                self._dirty.append(label)

        w = World()
        w.entity_select_state = SimpleNamespace(
            selected_ids=non_player_ids,
            primary_id=non_player_ids[0] if non_player_ids else "",
        )
        return w

    def test_kv_arg_parsing(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_snap_to_grid

        entities = _make_entities(
            {"id": "a", "x": 17.0, "y": 23.0},
        )
        w = self._make_world(entities)
        action_snap_to_grid(w, "step=16|axes=x|mode=floor")
        captured = capsys.readouterr().out
        assert "action=snap_to_grid" in captured
        assert "moved=1" in captured

    def test_plain_int_arg(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_snap_to_grid

        entities = _make_entities({"id": "a", "x": 17.0, "y": 23.0})
        w = self._make_world(entities)
        action_snap_to_grid(w, "16")
        captured = capsys.readouterr().out
        assert "action=snap_to_grid" in captured

    def test_empty_arg_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_snap_to_grid

        entities = _make_entities({"id": "a", "x": 17.0, "y": 23.0})
        w = self._make_world(entities)
        action_snap_to_grid(w, "")
        captured = capsys.readouterr().out
        assert "noop" in captured

    def test_no_selection_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_snap_to_grid

        w = SimpleNamespace(
            entity_select_state=SimpleNamespace(
                selected_ids=[],
                primary_id="",
            ),
        )
        action_snap_to_grid(w, "step=16")
        captured = capsys.readouterr().out
        assert "noop" in captured
        assert "no_selection" in captured
