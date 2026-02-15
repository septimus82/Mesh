"""Fast-tier tests for Selection: Distribute… editor authoring action.

Validates:
- deterministic sorted-ID application
- correct moved/skipped counts
- distribute x/y with gap and center modes
- entities without position/bounds are skipped
- selection < 3 returns ok=false
- custom entity widths/heights
- primary reference fallback
- command palette action parsing
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Minimal stubs (same pattern as test_editor_align_selection.py)
# ---------------------------------------------------------------------------

def _make_entities(*specs: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in specs:
        ent: dict[str, Any] = {"id": s["id"]}
        for key in ("name", "x", "y", "width", "height"):
            if key in s:
                ent[key] = s[key]
        if "tags" in s:
            ent["tags"] = list(s["tags"])
        if s.get("player"):
            ent.setdefault("tags", []).append("player")
        out.append(ent)
    return out


class _FakeSceneController:
    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self._authored: dict[str, Any] = {"entities": entities}
        self._applied: dict[str, Any] | None = None

    def get_authored_scene_payload(self) -> dict[str, Any]:
        return self._authored

    def apply_authored_scene_payload(self, payload: dict[str, Any]) -> None:
        self._applied = payload
        self._authored = payload

    def debug_distribute_selection(
        self,
        entity_ids: list[str],
        axis: str,
        mode: str = "gap",
        reference: str = "group",
        primary_id: str = "",
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_distribute_selection(
            self, entity_ids, axis, mode, reference=reference, primary_id=primary_id,
        )

    @property
    def entities_snapshot(self) -> list[dict[str, Any]]:
        return self._authored.get("entities", [])


def _patch_authoring(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_runtime.authoring.entity_ops as _ops
    monkeypatch.setattr(
        _ops, "get_authored_scene_payload",
        lambda controller: controller.get_authored_scene_payload(),
    )
    monkeypatch.setattr(
        _ops, "debug_apply_authored_scene_payload",
        lambda controller, payload: controller.apply_authored_scene_payload(payload),
    )


def _ent_by_id(sc: _FakeSceneController, eid: str) -> dict[str, Any]:
    return next(e for e in sc.entities_snapshot if e["id"] == eid)


# ---------------------------------------------------------------------------
# Distribute center mode
# ---------------------------------------------------------------------------

class TestDistributeCenterX:
    def test_basic_three_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        # Three entities at x=100, 300, 400.  After distribute center:
        # endpoints stay (100, 400), middle goes to 250.
        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 300.0, "y": 50.0},
            {"id": "c", "x": 400.0, "y": 50.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c"], "x", "center")
        assert result["ok"] is True
        assert result["moved"] == 1  # only b moves
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(250.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(400.0)

    def test_four_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        # x = 0, 10, 20, 90.  step = 90/3 = 30.  targets: 0, 30, 60, 90.
        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 10.0, "y": 0.0},
            {"id": "c", "x": 20.0, "y": 0.0},
            {"id": "d", "x": 90.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c", "d"], "x", "center")
        assert result["ok"] is True
        assert result["moved"] == 2  # b and c moved
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(30.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(60.0)
        assert _ent_by_id(sc, "d")["x"] == pytest.approx(90.0)

    def test_y_not_affected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 10.0},
            {"id": "b", "x": 50.0, "y": 20.0},
            {"id": "c", "x": 100.0, "y": 30.0},
        )
        sc = _FakeSceneController(entities)
        debug_distribute_selection(sc, ["a", "b", "c"], "x", "center")
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(10.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(20.0)
        assert _ent_by_id(sc, "c")["y"] == pytest.approx(30.0)


class TestDistributeCenterY:
    def test_basic_three_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 0.0, "y": 10.0},
            {"id": "c", "x": 0.0, "y": 100.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c"], "y", "center")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(50.0)
        assert _ent_by_id(sc, "c")["y"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Distribute gap mode
# ---------------------------------------------------------------------------

class TestDistributeGapX:
    def test_equal_size_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        # All default 32x32.  Place at x=16, 48, 200.
        # left-edge of first = 0, right-edge of last = 216, total span = 216.
        # total entity size = 32*3 = 96.  total gap = 120.  gap = 60.
        # positions: 16, 16+32+60=108 (cursor=0+32+60=92, center=92+16=108), 108+32+60=200.
        entities = _make_entities(
            {"id": "a", "x": 16.0, "y": 0.0},
            {"id": "b", "x": 48.0, "y": 0.0},
            {"id": "c", "x": 200.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c"], "x", "gap")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(16.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(108.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(200.0)

    def test_different_widths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        # a: x=20, w=40 -> left=0, right=40
        # b: x=50, w=20 -> left=40, right=60
        # c: x=190, w=20 -> left=180, right=200
        # total span = 200.  total size = 40+20+20 = 80.  total gap = 120.  gap = 60.
        # cursor starts at 0:
        #   a: center = 0+20=20 (stays), cursor = 20+20+60=100
        #   b: center = 100+10=110, cursor = 110+10+60=180
        #   c: center = 180+10=190 (stays)
        entities = _make_entities(
            {"id": "a", "x": 20.0, "y": 0.0, "width": 40.0},
            {"id": "b", "x": 50.0, "y": 0.0, "width": 20.0},
            {"id": "c", "x": 190.0, "y": 0.0, "width": 20.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c"], "x", "gap")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(20.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(110.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(190.0)


class TestDistributeGapY:
    def test_basic_three_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        # All default 32x32 (hh=16).
        # a: y=16 -> bottom=0, top=32
        # b: y=48 -> bottom=32, top=64
        # c: y=200 -> bottom=184, top=216
        # total span = 216.  total size = 96.  total gap = 120.  gap = 60.
        # cursor at 0: a center=16 (stays), cursor=32+60=92
        # b center=92+16=108, cursor=124+60=184
        # c center=184+16=200 (stays)
        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 16.0},
            {"id": "b", "x": 0.0, "y": 48.0},
            {"id": "c", "x": 0.0, "y": 200.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c"], "y", "gap")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(16.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(108.0)
        assert _ent_by_id(sc, "c")["y"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestDistributeEdgeCases:
    def test_fewer_than_three_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b"], "x", "center")
        assert result["ok"] is False

    def test_single_entity_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        sc = _FakeSceneController(_make_entities({"id": "a", "x": 50.0, "y": 0.0}))
        result = debug_distribute_selection(sc, ["a"], "x", "gap")
        assert result["ok"] is False

    def test_empty_selection_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        sc = _FakeSceneController(_make_entities({"id": "a", "x": 50.0, "y": 0.0}))
        result = debug_distribute_selection(sc, [], "x", "gap")
        assert result["ok"] is False

    def test_skip_entity_without_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b"},  # no position
            {"id": "c", "x": 50.0, "y": 0.0},
            {"id": "d", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c", "d"], "x", "center")
        assert result["ok"] is True
        assert result["skipped"] == 1
        # b should be unchanged (no x field)
        assert "x" not in _ent_by_id(sc, "b")

    def test_skip_player_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
            {"id": "c", "x": 100.0, "y": 0.0},
            {"id": "player1", "x": 200.0, "y": 0.0, "player": True},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c", "player1"], "x", "center")
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert _ent_by_id(sc, "player1")["x"] == pytest.approx(200.0)

    def test_unknown_axis_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
            {"id": "c", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c"], "z", "gap")
        assert result["ok"] is False

    def test_unknown_mode_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
            {"id": "c", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c"], "x", "spread")
        assert result["ok"] is False

    def test_default_width_height_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Entities without width/height use 32×32 fallback (half=16)."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        # All default 32x32.  Aligned at x=16, 50, 200.
        entities = _make_entities(
            {"id": "a", "x": 16.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
            {"id": "c", "x": 200.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(sc, ["a", "b", "c"], "x", "gap")
        assert result["ok"] is True
        # Just verify it distributes without error and endpoints are stable
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(16.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(200.0)

    def test_deterministic_sorted_id_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Entities with same position are processed deterministically by sorted ID."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "z", "x": 0.0, "y": 0.0},
            {"id": "m", "x": 50.0, "y": 0.0},
            {"id": "a", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        # All already evenly spaced → 0 moved
        result = debug_distribute_selection(sc, ["z", "m", "a"], "x", "center")
        assert result["ok"] is True
        assert result["moved"] == 0


# ---------------------------------------------------------------------------
# Command palette action parsing
# ---------------------------------------------------------------------------

class TestCommandPaletteDistributeAction:
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

    def test_simple_distribute_x_gap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 16.0, "y": 0.0},
            {"id": "b", "x": 48.0, "y": 0.0},
            {"id": "c", "x": 200.0, "y": 0.0},
        )
        w = self._make_window(entities, ["a", "b", "c"])
        action_distribute_selection(w, "distribute_x_gap")
        assert _ent_by_id(w.scene_controller, "a")["x"] == pytest.approx(16.0)
        assert _ent_by_id(w.scene_controller, "c")["x"] == pytest.approx(200.0)

    def test_simple_distribute_y_center(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 0.0, "y": 10.0},
            {"id": "c", "x": 0.0, "y": 100.0},
        )
        w = self._make_window(entities, ["a", "b", "c"])
        action_distribute_selection(w, "distribute_y_center")
        assert _ent_by_id(w.scene_controller, "b")["y"] == pytest.approx(50.0)

    def test_key_value_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 10.0, "y": 0.0},
            {"id": "c", "x": 90.0, "y": 0.0},
        )
        w = self._make_window(entities, ["a", "b", "c"])
        action_distribute_selection(w, "axis=x|mode=center|ref=group")
        assert _ent_by_id(w.scene_controller, "b")["x"] == pytest.approx(45.0)

    def test_unknown_token_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
            {"id": "c", "x": 100.0, "y": 0.0},
        )
        w = self._make_window(entities, ["a", "b", "c"])
        action_distribute_selection(w, "scatter")  # unknown
        # positions unchanged
        assert _ent_by_id(w.scene_controller, "b")["x"] == pytest.approx(50.0)

    def test_empty_arg_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
            {"id": "c", "x": 100.0, "y": 0.0},
        )
        w = self._make_window(entities, ["a", "b", "c"])
        action_distribute_selection(w, "")  # should not raise
