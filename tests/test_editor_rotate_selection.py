"""Fast-tier tests for Selection: Rotate… editor authoring action.

Validates:
- rotation-only (about=self): rotation field updates, normalization to [0,360)
- skip player and entities without rotation support
- zero-degree no-op
- invalid about → ok=false
- deterministic sorted-ID application
- about=group: positions rotate around centroid
- about=primary: positions rotate around primary entity
- command palette parsing: cw, ccw, deg=N|about=…
"""
from __future__ import annotations

import math
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
        for key in ("name", "x", "y", "width", "height", "rotation"):
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

    def debug_rotate_selection(
        self,
        entity_ids: list[str],
        deg: float,
        about: str = "self",
        primary_id: str = "",
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_rotate_selection(
            self, entity_ids, deg, about=about, primary_id=primary_id,
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
# Rotation-only (about="self")
# ---------------------------------------------------------------------------

class TestRotateSelf:
    def test_rotate_90_cw(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities(
            {"id": "a", "x": 10.0, "y": 20.0, "rotation": 0.0},
            {"id": "b", "x": 30.0, "y": 40.0, "rotation": 45.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["a", "b"], deg=90.0, about="self")
        assert result["ok"] is True
        assert result["rotated"] == 2
        assert result["moved"] == 0
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(90.0)
        assert _ent_by_id(sc, "b")["rotation"] == pytest.approx(135.0)
        # Positions unchanged.
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(10.0)

    def test_rotate_ccw(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 30.0})
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["a"], deg=-90.0)
        assert result["ok"] is True
        assert result["rotated"] == 1
        # 30 - 90 = -60 → normalized to 300
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(300.0)

    def test_normalize_wraps_360(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 350.0})
        sc = _FakeSceneController(entities)
        debug_rotate_selection(sc, ["a"], deg=20.0)
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(10.0)

    def test_entity_without_rotation_gets_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Entities without an existing rotation field get it set (defaults to 0)."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})  # no rotation key
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["a"], deg=45.0)
        assert result["ok"] is True
        assert result["rotated"] == 1
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(45.0)

    def test_skip_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0, "player": True},
            {"id": "b", "x": 10.0, "y": 10.0, "rotation": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["a", "b"], deg=90.0)
        assert result["rotated"] == 1
        assert result["skipped"] == 1
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "b")["rotation"] == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestRotateEdgeCases:
    def test_zero_deg_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 45.0})
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["a"], deg=0.0)
        assert result["ok"] is True
        assert result["rotated"] == 0
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(45.0)

    def test_empty_selection_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        sc = _FakeSceneController([])
        result = debug_rotate_selection(sc, [], deg=90.0)
        assert result["ok"] is True
        assert result["rotated"] == 0

    def test_invalid_about(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["a"], deg=90.0, about="invalid")
        assert result["ok"] is False

    def test_primary_no_pivot_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0})
        sc = _FakeSceneController(entities)
        # about=primary but no primary_id given
        result = debug_rotate_selection(sc, ["a"], deg=90.0, about="primary", primary_id="")
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Deterministic order
# ---------------------------------------------------------------------------

class TestRotateDeterministic:
    def test_sorted_id_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities(
            {"id": "c", "x": 0.0, "y": 0.0, "rotation": 0.0},
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 100.0},
            {"id": "b", "x": 0.0, "y": 0.0, "rotation": 200.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["c", "a", "b"], deg=45.0)
        assert result["ok"] is True
        assert result["rotated"] == 3
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(145.0)
        assert _ent_by_id(sc, "b")["rotation"] == pytest.approx(245.0)
        assert _ent_by_id(sc, "c")["rotation"] == pytest.approx(45.0)


# ---------------------------------------------------------------------------
# Position rotation (about=group / primary)
# ---------------------------------------------------------------------------

class TestRotateAboutGroup:
    def test_rotate_90_about_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        # Two entities: centroid = (50, 50)
        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 50.0, "rotation": 0.0},
            {"id": "b", "x": 100.0, "y": 50.0, "rotation": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["a", "b"], deg=90.0, about="group")
        assert result["ok"] is True
        assert result["rotated"] == 2
        assert result["moved"] == 2

        # After 90° CW rotation around (50,50):
        # a(0,50) → offset(-50,0) → rotated(0,-50) → (50, 0)
        # b(100,50) → offset(50,0) → rotated(0,50) → (50, 100)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(50.0)
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(50.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(100.0)

    def test_rotate_180_about_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0},
            {"id": "b", "x": 100.0, "y": 100.0, "rotation": 0.0},
        )
        sc = _FakeSceneController(entities)
        # centroid = (50, 50)
        result = debug_rotate_selection(sc, ["a", "b"], deg=180.0, about="group")
        assert result["ok"] is True
        assert result["moved"] == 2
        # 180° swaps them relative to centroid
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(0.0)


class TestRotateAboutPrimary:
    def test_rotate_90_about_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        # Primary = a at (0,0). b at (100,0).
        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0, "rotation": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(
            sc, ["a", "b"], deg=90.0, about="primary", primary_id="a",
        )
        assert result["ok"] is True
        assert result["rotated"] == 2
        # a stays at origin (pivot)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(0.0)
        # b(100,0) rotated 90° CW around (0,0): offset(100,0) → (0,100)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(0.0, abs=1e-6)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Command palette action wiring
# ---------------------------------------------------------------------------

class TestRotateCommandPaletteAction:
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

    def test_cw_token(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0})
        w = self._make_world(entities)
        action_rotate_selection(w, "cw")
        captured = capsys.readouterr().out
        assert "action=rotate_selection" in captured
        assert "rotated=1" in captured
        assert "deg=90.0" in captured

    def test_ccw_token(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0})
        w = self._make_world(entities)
        action_rotate_selection(w, "ccw")
        captured = capsys.readouterr().out
        assert "action=rotate_selection" in captured
        assert "deg=-90.0" in captured

    def test_kv_parsing(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0})
        w = self._make_world(entities)
        action_rotate_selection(w, "deg=180|about=self")
        captured = capsys.readouterr().out
        assert "action=rotate_selection" in captured
        assert "deg=180.0" in captured

    def test_plain_number(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0})
        w = self._make_world(entities)
        action_rotate_selection(w, "45")
        captured = capsys.readouterr().out
        assert "action=rotate_selection" in captured
        assert "deg=45.0" in captured

    def test_empty_arg_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_rotate_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0})
        w = self._make_world(entities)
        action_rotate_selection(w, "")
        captured = capsys.readouterr().out
        assert "noop" in captured

    def test_no_selection_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_rotate_selection

        w = SimpleNamespace(
            entity_select_state=SimpleNamespace(selected_ids=[], primary_id=""),
        )
        action_rotate_selection(w, "cw")
        captured = capsys.readouterr().out
        assert "noop" in captured
        assert "no_selection" in captured
