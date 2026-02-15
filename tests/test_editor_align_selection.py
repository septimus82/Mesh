"""Fast-tier tests for Selection: Align… editor authoring action.

Validates:
- deterministic sorted-ID application
- correct moved/skipped counts
- left/center/right (x-axis) and top/middle/bottom (y-axis) alignment
- primary vs group reference
- entities without position/bounds are skipped
- selection < 2 returns ok=false
- command palette action wiring + input parsing
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

def _make_entities(*specs: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a list of entity dicts from compact specs.

    Each spec may contain: id, name, x, y, width, height, tags, player.
    """
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

    def debug_align_selection(
        self,
        entity_ids: list[str],
        axis: str,
        mode: str,
        reference: str = "primary",
        primary_id: str = "",
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_align_selection(
            self, entity_ids, axis, mode, reference=reference, primary_id=primary_id,
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
# Core alignment tests
# ---------------------------------------------------------------------------

class TestAlignSelectionX:
    """X-axis alignment tests."""

    def test_align_left_to_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        # Entity widths default to 32 (half=16).  left edge = x - 16.
        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},   # left=84
            {"id": "b", "x": 200.0, "y": 60.0},   # left=184
            {"id": "c", "x": 150.0, "y": 70.0},   # left=134
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b", "c"], "x", "left", reference="primary", primary_id="a")
        assert result["ok"] is True
        assert result["moved"] == 2  # b and c move, a stays
        assert result["skipped"] == 0
        # All should have left edge == 84 => x == 100
        for eid in ("a", "b", "c"):
            assert _ent_by_id(sc, eid)["x"] == pytest.approx(100.0)

    def test_align_right_to_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},   # right=116
            {"id": "b", "x": 200.0, "y": 60.0},   # right=216
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "x", "right", reference="primary", primary_id="b")
        assert result["ok"] is True
        assert result["moved"] == 1
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(200.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(200.0)

    def test_align_center_to_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        sc = _FakeSceneController(entities)
        # center anchor = x.  group center = (100+200)/2 = 150
        result = debug_align_selection(sc, ["a", "b"], "x", "center", reference="group")
        assert result["ok"] is True
        assert result["moved"] == 2
        for eid in ("a", "b"):
            assert _ent_by_id(sc, eid)["x"] == pytest.approx(150.0)

    def test_align_left_to_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        # left edges: a=84, b=184.  group left = min(84,184) = 84 => target x = 100
        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "x", "left", reference="group")
        assert result["ok"] is True
        assert result["moved"] == 1  # only b moves
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(100.0)


class TestAlignSelectionY:
    """Y-axis alignment tests."""

    def test_align_top_to_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        # top edge = y + 16 (default half-height = 16).
        entities = _make_entities(
            {"id": "a", "x": 50.0, "y": 100.0},   # top=116
            {"id": "b", "x": 60.0, "y": 200.0},   # top=216
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "y", "top", reference="primary", primary_id="b")
        assert result["ok"] is True
        assert result["moved"] == 1
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(200.0)

    def test_align_bottom_to_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 50.0, "y": 100.0},   # bottom=84
            {"id": "b", "x": 60.0, "y": 200.0},   # bottom=184
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "y", "bottom", reference="group")
        assert result["ok"] is True
        assert result["moved"] == 1  # only b moves down
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(100.0)

    def test_align_middle_to_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 50.0, "y": 100.0},
            {"id": "b", "x": 60.0, "y": 200.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "y", "middle", reference="group")
        assert result["ok"] is True
        assert result["moved"] == 2
        for eid in ("a", "b"):
            assert _ent_by_id(sc, eid)["y"] == pytest.approx(150.0)


class TestAlignSelectionWithBounds:
    """Tests with explicit entity width/height."""

    def test_align_left_with_different_widths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0, "width": 40.0},   # left=80
            {"id": "b", "x": 200.0, "y": 60.0, "width": 20.0},   # left=190
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "x", "left", reference="primary", primary_id="a")
        assert result["ok"] is True
        # b's left edge should become 80 => b.x = 80 + 10 = 90
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(90.0)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(100.0)

    def test_align_top_with_different_heights(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 50.0, "y": 100.0, "height": 40.0},  # top=120
            {"id": "b", "x": 60.0, "y": 200.0, "height": 60.0},  # top=230
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "y", "top", reference="primary", primary_id="a")
        assert result["ok"] is True
        # b's top should become 120 => b.y = 120 - 30 = 90
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(90.0)


class TestAlignSelectionEdgeCases:
    """Edge cases and validation."""

    def test_selection_less_than_two_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        sc = _FakeSceneController(_make_entities({"id": "a", "x": 100.0, "y": 50.0}))
        result = debug_align_selection(sc, ["a"], "x", "left")
        assert result["ok"] is False
        assert result["moved"] == 0

    def test_empty_selection_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        sc = _FakeSceneController(_make_entities({"id": "a", "x": 100.0, "y": 50.0}))
        result = debug_align_selection(sc, [], "x", "left")
        assert result["ok"] is False

    def test_skip_entity_without_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b"},  # no x/y
            {"id": "c", "x": 200.0, "y": 60.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b", "c"], "x", "left", reference="group")
        assert result["ok"] is True
        assert result["moved"] == 1  # only c moves
        assert result["skipped"] == 1  # b skipped

    def test_skip_player_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "player1", "x": 300.0, "y": 70.0, "player": True},
            {"id": "c", "x": 200.0, "y": 60.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "player1", "c"], "x", "left", reference="group")
        assert result["ok"] is True
        assert result["skipped"] == 1
        # player should not have moved
        assert _ent_by_id(sc, "player1")["x"] == pytest.approx(300.0)

    def test_unknown_axis_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "z", "left")
        assert result["ok"] is False

    def test_unknown_mode_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], "x", "top")  # top is y-axis mode
        assert result["ok"] is False

    def test_primary_fallback_to_group_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        sc = _FakeSceneController(entities)
        # reference=primary but primary_id isn't in selection — falls back to group
        result = debug_align_selection(sc, ["a", "b"], "x", "left", reference="primary", primary_id="missing")
        assert result["ok"] is True
        # group left = min(84,184) = 84 => both x = 100
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(100.0)

    def test_deterministic_sorted_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Entities are processed in sorted-ID order."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "z", "x": 300.0, "y": 50.0},
            {"id": "m", "x": 200.0, "y": 50.0},
            {"id": "a", "x": 100.0, "y": 50.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["z", "m", "a"], "x", "center", reference="group")
        assert result["ok"] is True
        # group center = (100+200+300)/3 = 200
        for eid in ("a", "m", "z"):
            assert _ent_by_id(sc, eid)["x"] == pytest.approx(200.0)

    def test_y_axis_not_affected_by_x_align(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """X-axis alignment must not alter y positions."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 150.0},
        )
        sc = _FakeSceneController(entities)
        debug_align_selection(sc, ["a", "b"], "x", "left", reference="group")
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(50.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# Command palette action wiring
# ---------------------------------------------------------------------------

class TestCommandPaletteAlignAction:
    """Verify command palette action_align_selection wiring."""

    def _make_window(self, entities: list[dict[str, Any]], selected_ids: list[str]) -> SimpleNamespace:
        sc = _FakeSceneController(copy.deepcopy(entities))
        w = SimpleNamespace()
        w.entity_select_state = SimpleNamespace(
            selected_ids=list(selected_ids),
            primary_id=selected_ids[0] if selected_ids else "",
        )
        w.scene_controller = sc
        w.push_undo_frame = lambda reason: None
        w.mark_scene_dirty = lambda reason: None
        w.scene_dirty_counter = 0
        return w

    def test_simple_left_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        w = self._make_window(entities, ["a", "b"])
        action_align_selection(w, "left")
        # primary is "a" (first in selection).  All align to a's left edge.
        assert _ent_by_id(w.scene_controller, "b")["x"] == pytest.approx(100.0)

    def test_key_value_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        w = self._make_window(entities, ["a", "b"])
        action_align_selection(w, "axis=y|mode=top|reference=group")
        # top edges: a=66, b=76.  group max = 76 => target.  a.y should become 60.
        assert _ent_by_id(w.scene_controller, "a")["y"] == pytest.approx(60.0)

    def test_simple_bottom_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_align_selection

        entities = _make_entities(
            {"id": "a", "x": 50.0, "y": 100.0},
            {"id": "b", "x": 60.0, "y": 200.0},
        )
        w = self._make_window(entities, ["a", "b"])
        action_align_selection(w, "bottom")
        # primary=a, bottom=84.  b should move to y = 84 + 16 = 100.
        assert _ent_by_id(w.scene_controller, "b")["y"] == pytest.approx(100.0)

    def test_unknown_token_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        w = self._make_window(entities, ["a", "b"])
        action_align_selection(w, "diagonal")  # should not raise
        # Positions unchanged
        assert _ent_by_id(w.scene_controller, "a")["x"] == pytest.approx(100.0)
        assert _ent_by_id(w.scene_controller, "b")["x"] == pytest.approx(200.0)

    def test_empty_arg_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        w = self._make_window(entities, ["a", "b"])
        action_align_selection(w, "")  # should not raise

    def test_ref_shorthand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_align_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        w = self._make_window(entities, ["a", "b"])
        action_align_selection(w, "axis=x|mode=center|ref=group")
        for eid in ("a", "b"):
            assert _ent_by_id(w.scene_controller, eid)["x"] == pytest.approx(150.0)
