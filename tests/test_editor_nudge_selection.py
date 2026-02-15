"""Fast-tier tests for Selection: Nudge… editor authoring action.

Validates:
- explicit dx/dy with count
- step scaling
- invalid count/step → ok=false, no mutation
- skip player and no-position entities
- deterministic sorted-ID order
- zero-delta no-op returns ok=true, moved=0
- command palette key/value parsing
- command palette direction-token parsing
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

def _make_entities(*specs: dict[str, Any]) -> list[dict[str, Any]]:
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
    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self._authored: dict[str, Any] = {"entities": entities}
        self._applied: dict[str, Any] | None = None

    def get_authored_scene_payload(self) -> dict[str, Any]:
        return self._authored

    def apply_authored_scene_payload(self, payload: dict[str, Any]) -> None:
        self._applied = payload
        self._authored = payload

    def debug_nudge_selection(
        self,
        entity_ids: list[str],
        dx: float,
        dy: float,
        count: int = 1,
        step: float | None = None,
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_nudge_selection(
            self, entity_ids, dx, dy, count=count, step=step,
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
# Core nudge tests
# ---------------------------------------------------------------------------

class TestNudgeBasic:
    def test_nudge_dx_dy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities(
            {"id": "a", "x": 100.0, "y": 50.0},
            {"id": "b", "x": 200.0, "y": 60.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a", "b"], dx=10.0, dy=-5.0)
        assert result["ok"] is True
        assert result["moved"] == 2
        assert result["dx"] == pytest.approx(10.0)
        assert result["dy"] == pytest.approx(-5.0)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(110.0)
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(45.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(210.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(55.0)

    def test_nudge_with_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a"], dx=5.0, dy=0.0, count=3)
        assert result["ok"] is True
        assert result["dx"] == pytest.approx(15.0)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(15.0)

    def test_nudge_with_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        # dx=1 (direction), step=16, count=2 → eff_dx = 1*16*2 = 32
        result = debug_nudge_selection(sc, ["a"], dx=1.0, dy=0.0, count=2, step=16.0)
        assert result["ok"] is True
        assert result["dx"] == pytest.approx(32.0)
        assert result["dy"] == pytest.approx(0.0)
        assert result["step"] == pytest.approx(16.0)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(32.0)

    def test_nudge_negative_direction_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities({"id": "a", "x": 100.0, "y": 100.0})
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a"], dx=-1.0, dy=0.0, count=1, step=8.0)
        assert result["ok"] is True
        assert result["dx"] == pytest.approx(-8.0)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(92.0)

    def test_zero_delta_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities({"id": "a", "x": 50.0, "y": 50.0})
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a"], dx=0.0, dy=0.0)
        assert result["ok"] is True
        assert result["moved"] == 0
        # Entity unchanged
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

class TestNudgeValidation:
    def test_invalid_count_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities({"id": "a", "x": 50.0, "y": 50.0})
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a"], dx=1.0, dy=0.0, count=0)
        assert result["ok"] is False
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(50.0)

    def test_invalid_count_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities({"id": "a", "x": 50.0, "y": 50.0})
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a"], dx=1.0, dy=0.0, count=-2)
        assert result["ok"] is False

    def test_invalid_step_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities({"id": "a", "x": 50.0, "y": 50.0})
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a"], dx=1.0, dy=0.0, step=0.0)
        assert result["ok"] is False

    def test_invalid_step_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities({"id": "a", "x": 50.0, "y": 50.0})
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a"], dx=1.0, dy=0.0, step=-5.0)
        assert result["ok"] is False

    def test_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        sc = _FakeSceneController([])
        result = debug_nudge_selection(sc, [], dx=1.0, dy=0.0)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Skip cases
# ---------------------------------------------------------------------------

class TestNudgeSkips:
    def test_skip_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities(
            {"id": "a", "x": 50.0, "y": 50.0, "player": True},
            {"id": "b", "x": 100.0, "y": 100.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a", "b"], dx=10.0, dy=0.0)
        assert result["ok"] is True
        assert result["moved"] == 1
        assert result["skipped"] == 1
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(50.0)  # unchanged
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(110.0)

    def test_skip_no_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities(
            {"id": "a"},  # no x/y
            {"id": "b", "x": 100.0, "y": 100.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a", "b"], dx=10.0, dy=0.0)
        assert result["skipped"] == 1
        assert result["moved"] == 1


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------

class TestNudgeDeterministic:
    def test_sorted_id_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities(
            {"id": "c", "x": 30.0, "y": 0.0},
            {"id": "a", "x": 10.0, "y": 0.0},
            {"id": "b", "x": 20.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["c", "a", "b"], dx=5.0, dy=0.0)
        assert result["ok"] is True
        assert result["moved"] == 3
        # All moved by same delta regardless of order
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(15.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(25.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(35.0)


# ---------------------------------------------------------------------------
# Command palette action wiring
# ---------------------------------------------------------------------------

class TestNudgeCommandPaletteAction:
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

    def test_kv_parsing(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_nudge_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_nudge_selection(w, "dx=10|dy=-5|count=2")
        captured = capsys.readouterr().out
        assert "action=nudge_selection" in captured
        assert "moved=1" in captured

    def test_kv_with_step(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_nudge_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_nudge_selection(w, "dx=1|dy=0|count=3|step=8")
        captured = capsys.readouterr().out
        assert "action=nudge_selection" in captured
        assert "dx=24.0" in captured

    def test_direction_token_right(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_nudge_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_nudge_selection(w, "right")
        captured = capsys.readouterr().out
        assert "action=nudge_selection" in captured

    def test_direction_token_with_count_and_step(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_nudge_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_nudge_selection(w, "left x2 step=16")
        captured = capsys.readouterr().out
        assert "action=nudge_selection" in captured
        assert "dx=-32.0" in captured

    def test_empty_arg_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_nudge_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_nudge_selection(w, "")
        captured = capsys.readouterr().out
        assert "noop" in captured

    def test_no_selection_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_nudge_selection

        w = SimpleNamespace(
            entity_select_state=SimpleNamespace(selected_ids=[], primary_id=""),
        )
        action_nudge_selection(w, "dx=10|dy=0")
        captured = capsys.readouterr().out
        assert "noop" in captured
        assert "no_selection" in captured
