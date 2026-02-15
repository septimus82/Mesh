"""Fast-tier tests for Selection: Mirror / Flip… editor authoring action.

Validates:
- axis=x group: positions mirrored about centroid (flip left/right)
- axis=y group: positions mirrored about centroid (flip up/down)
- rotation mirroring rules locked
- include_rotation=false: rotations unchanged
- about=primary: uses primary pivot; fails if missing
- skip player + no-position entities
- deterministic sorted-ID order
- command palette parsing: simple + key/value
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

    def debug_mirror_selection(
        self,
        entity_ids: list[str],
        axis: str,
        about: str = "group",
        primary_id: str = "",
        include_rotation: bool = True,
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_mirror_selection(
            self, entity_ids, axis, about=about, primary_id=primary_id,
            include_rotation=include_rotation,
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
# Mirror positions – axis=x (flip left/right about group centroid)
# ---------------------------------------------------------------------------

class TestMirrorAxisX:
    def test_mirror_x_group_two_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        # centroid x = (0+100)/2 = 50
        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 10.0, "rotation": 0.0},
            {"id": "b", "x": 100.0, "y": 20.0, "rotation": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b"], axis="x", about="group")
        assert result["ok"] is True
        assert result["moved"] == 2
        # a: x' = 2*50 - 0 = 100
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(10.0)  # y unchanged
        # b: x' = 2*50 - 100 = 0
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(20.0)

    def test_mirror_x_three_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        # centroid x = (0+50+100)/3 = 50
        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
            {"id": "c", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b", "c"], axis="x")
        assert result["ok"] is True
        assert result["moved"] == 2  # b stays at centroid
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(50.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Mirror positions – axis=y (flip up/down about group centroid)
# ---------------------------------------------------------------------------

class TestMirrorAxisY:
    def test_mirror_y_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        # centroid y = (0+100)/2 = 50
        entities = _make_entities(
            {"id": "a", "x": 10.0, "y": 0.0, "rotation": 0.0},
            {"id": "b", "x": 20.0, "y": 100.0, "rotation": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b"], axis="y")
        assert result["ok"] is True
        assert result["moved"] == 2
        assert _ent_by_id(sc, "a")["y"] == pytest.approx(100.0)
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(10.0)  # x unchanged
        assert _ent_by_id(sc, "b")["y"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Rotation mirroring
# ---------------------------------------------------------------------------

class TestMirrorRotation:
    def test_axis_x_rotation_30_becomes_330(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 30.0},
            {"id": "b", "x": 100.0, "y": 0.0, "rotation": 30.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b"], axis="x")
        assert result["rotated"] == 2
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(330.0)
        assert _ent_by_id(sc, "b")["rotation"] == pytest.approx(330.0)

    def test_axis_y_rotation_30_becomes_150(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 30.0},
            {"id": "b", "x": 0.0, "y": 100.0, "rotation": 30.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b"], axis="y")
        assert result["rotated"] == 2
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(150.0)
        assert _ent_by_id(sc, "b")["rotation"] == pytest.approx(150.0)

    def test_axis_x_rotation_0_becomes_0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """rot=0 → (360-0)%360 = 0, no change counted."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0, "rotation": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b"], axis="x")
        assert result["rotated"] == 0  # rotation didn't change

    def test_include_rotation_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 30.0},
            {"id": "b", "x": 100.0, "y": 0.0, "rotation": 30.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b"], axis="x", include_rotation=False)
        assert result["ok"] is True
        assert result["rotated"] == 0
        assert result["moved"] == 2
        assert _ent_by_id(sc, "a")["rotation"] == pytest.approx(30.0)  # unchanged


# ---------------------------------------------------------------------------
# about=primary
# ---------------------------------------------------------------------------

class TestMirrorAboutPrimary:
    def test_mirror_x_about_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        # Primary = a at (0,0). b at (100,0).
        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0, "rotation": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(
            sc, ["a", "b"], axis="x", about="primary", primary_id="a",
        )
        assert result["ok"] is True
        # a stays at pivot
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(0.0)
        # b: x' = 2*0 - 100 = -100
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(-100.0)

    def test_primary_missing_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a"], axis="x", about="primary", primary_id="")
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Skip cases
# ---------------------------------------------------------------------------

class TestMirrorSkips:
    def test_skip_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "player": True},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        # With only 1 participant, centroid = (100, 0), mirror does nothing
        result = debug_mirror_selection(sc, ["a", "b"], axis="x")
        assert result["skipped"] == 1
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(0.0)

    def test_skip_no_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities(
            {"id": "a"},  # no x/y
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b"], axis="x")
        assert result["skipped"] == 1

    def test_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        sc = _FakeSceneController([])
        result = debug_mirror_selection(sc, [], axis="x")
        assert result["ok"] is True
        assert result["moved"] == 0

    def test_invalid_axis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a"], axis="z")
        assert result["ok"] is False

    def test_invalid_about(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a"], axis="x", about="invalid")
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Deterministic order
# ---------------------------------------------------------------------------

class TestMirrorDeterministic:
    def test_sorted_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities(
            {"id": "c", "x": 0.0, "y": 0.0},
            {"id": "a", "x": 50.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        # centroid x = 50. a at centroid stays, c and b swap.
        result = debug_mirror_selection(sc, ["c", "a", "b"], axis="x")
        assert result["ok"] is True
        assert _ent_by_id(sc, "a")["x"] == pytest.approx(50.0)
        assert _ent_by_id(sc, "b")["x"] == pytest.approx(0.0)
        assert _ent_by_id(sc, "c")["x"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Command palette action wiring
# ---------------------------------------------------------------------------

class TestMirrorCommandPaletteAction:
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

    def test_simple_x(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 30.0},
            {"id": "b", "x": 100.0, "y": 0.0, "rotation": 30.0},
        )
        w = self._make_world(entities)
        action_mirror_selection(w, "x")
        captured = capsys.readouterr().out
        assert "action=mirror_selection" in captured
        assert "moved=2" in captured

    def test_simple_y_norot(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 30.0},
            {"id": "b", "x": 0.0, "y": 100.0, "rotation": 30.0},
        )
        w = self._make_world(entities)
        action_mirror_selection(w, "y no-rot")
        captured = capsys.readouterr().out
        assert "action=mirror_selection" in captured

    def test_kv_parsing(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 45.0},
            {"id": "b", "x": 100.0, "y": 0.0, "rotation": 45.0},
        )
        w = self._make_world(entities)
        action_mirror_selection(w, "axis=x|about=group|rot=0")
        captured = capsys.readouterr().out
        assert "action=mirror_selection" in captured

    def test_empty_arg_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_mirror_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_mirror_selection(w, "")
        captured = capsys.readouterr().out
        assert "noop" in captured

    def test_no_selection_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_mirror_selection

        w = SimpleNamespace(
            entity_select_state=SimpleNamespace(selected_ids=[], primary_id=""),
        )
        action_mirror_selection(w, "x")
        captured = capsys.readouterr().out
        assert "noop" in captured
        assert "no_selection" in captured
