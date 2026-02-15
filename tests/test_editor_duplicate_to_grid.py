"""Fast-tier tests for Selection: Duplicate to Grid… editor authoring action.

Validates:
- correct duplicate count (rows*cols*entities minus originals)
- row-major placement offsets
- deterministic ordering (shuffled selection yields identical result)
- skip player / no-position entities
- name_mode=numbered suffix on duplicates only
- invalid rows/cols → ok=false
- 1x1 include_original → noop (ok=true, created=0)
- include_original=false creates copies even at (0,0)
- command palette parsing (kv + shorthand)
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
        for key in ("name", "x", "y", "width", "height", "rotation", "prefab_id"):
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

    def get_authored_scene_payload(self) -> dict[str, Any]:
        return self._authored

    def apply_authored_scene_payload(self, payload: dict[str, Any]) -> None:
        self._authored = payload

    def debug_duplicate_to_grid(
        self,
        entity_ids: list[str],
        rows: int = 1,
        cols: int = 1,
        dx: float = 0.0,
        dy: float = 0.0,
        origin: str = "selection",
        include_original: bool = True,
        name_mode: str = "none",
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_duplicate_to_grid(
            self, entity_ids, rows=rows, cols=cols, dx=dx, dy=dy,
            origin=origin, include_original=include_original,
            name_mode=name_mode,
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


def _ent_by_id(sc: _FakeSceneController, eid: str) -> dict[str, Any] | None:
    for e in sc.entities_snapshot:
        if e.get("id") == eid:
            return e
    return None


def _duplicates(sc: _FakeSceneController) -> list[dict[str, Any]]:
    return [e for e in sc.entities_snapshot if "__dup" in str(e.get("id", ""))]


# ---------------------------------------------------------------------------
# Basic grid duplication
# ---------------------------------------------------------------------------

class TestDuplicateToGridBasic:
    def test_2x2_single_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 10.0, "y": 20.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a"], rows=2, cols=2, dx=32.0, dy=32.0)
        assert result["ok"] is True
        # 2x2 = 4 cells, minus original at (0,0) = 3 duplicates
        assert result["created"] == 3

        dups = _duplicates(sc)
        assert len(dups) == 3
        positions = sorted([(d["x"], d["y"]) for d in dups])
        # (0,0)=original, (1,0)=col1, (0,1)=row1col0, (1,1)=row1col1
        expected = sorted([
            (10.0 + 32.0, 20.0),         # r=0,c=1
            (10.0, 20.0 + 32.0),         # r=1,c=0
            (10.0 + 32.0, 20.0 + 32.0),  # r=1,c=1
        ])
        assert positions == pytest.approx(expected)

    def test_3x1_vertical_strip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a"], rows=3, cols=1, dx=0.0, dy=16.0)
        assert result["ok"] is True
        assert result["created"] == 2  # 3 rows * 1 col - 1 original = 2
        dups = _duplicates(sc)
        ys = sorted([d["y"] for d in dups])
        assert ys == pytest.approx([16.0, 32.0])

    def test_1x4_horizontal_strip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a"], rows=1, cols=4, dx=10.0, dy=0.0)
        assert result["ok"] is True
        assert result["created"] == 3

    def test_multiple_entities_in_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 5.0, "y": 5.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a", "b"], rows=2, cols=2, dx=32.0, dy=32.0)
        assert result["ok"] is True
        # 3 non-original cells * 2 entities = 6
        assert result["created"] == 6


# ---------------------------------------------------------------------------
# include_original=False
# ---------------------------------------------------------------------------

class TestIncludeOriginalFalse:
    def test_creates_at_0_0_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 10.0, "y": 20.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(
            sc, ["a"], rows=2, cols=2, dx=32.0, dy=32.0, include_original=False,
        )
        assert result["ok"] is True
        # 2x2 = 4 cells, all get duplicates
        assert result["created"] == 4

        dups = _duplicates(sc)
        assert len(dups) == 4
        positions = sorted([(d["x"], d["y"]) for d in dups])
        expected = sorted([
            (10.0, 20.0),                 # r=0,c=0
            (10.0 + 32.0, 20.0),          # r=0,c=1
            (10.0, 20.0 + 32.0),          # r=1,c=0
            (10.0 + 32.0, 20.0 + 32.0),   # r=1,c=1
        ])
        assert positions == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Row-major placement order
# ---------------------------------------------------------------------------

class TestPlacementOrder:
    def test_row_major_offsets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a"], rows=2, cols=3, dx=10.0, dy=20.0)
        assert result["ok"] is True
        # 2*3 - 1 = 5, expected cells: (0,1), (0,2), (1,0), (1,1), (1,2)
        assert result["created"] == 5
        dups = _duplicates(sc)
        positions = sorted([(d["x"], d["y"]) for d in dups])
        expected = sorted([
            (10.0, 0.0),   # (0,1)
            (20.0, 0.0),   # (0,2)
            (0.0, 20.0),   # (1,0)
            (10.0, 20.0),  # (1,1)
            (20.0, 20.0),  # (1,2)
        ])
        assert positions == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------

class TestDeterministic:
    def test_shuffled_selection_same_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        spec = [
            {"id": "c", "x": 20.0, "y": 0.0},
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 10.0, "y": 0.0},
        ]

        # Run 1: shuffled order
        sc1 = _FakeSceneController(_make_entities(*spec))
        debug_duplicate_to_grid(sc1, ["c", "a", "b"], rows=1, cols=2, dx=50.0, dy=0.0)
        ids1 = sorted([e["id"] for e in _duplicates(sc1)])

        # Run 2: different order
        sc2 = _FakeSceneController(_make_entities(*spec))
        debug_duplicate_to_grid(sc2, ["b", "c", "a"], rows=1, cols=2, dx=50.0, dy=0.0)
        ids2 = sorted([e["id"] for e in _duplicates(sc2)])

        assert ids1 == ids2


# ---------------------------------------------------------------------------
# Skip player / no-position
# ---------------------------------------------------------------------------

class TestSkips:
    def test_skip_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities(
            {"id": "p", "x": 0.0, "y": 0.0, "player": True},
            {"id": "a", "x": 10.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["p", "a"], rows=1, cols=2, dx=32.0, dy=0.0)
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["created"] == 1  # only 'a' duplicated
        dups = _duplicates(sc)
        assert len(dups) == 1
        assert dups[0]["x"] == pytest.approx(42.0)

    def test_skip_no_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities(
            {"id": "a"},  # no x/y
            {"id": "b", "x": 0.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a", "b"], rows=1, cols=2, dx=10.0, dy=0.0)
        assert result["skipped"] == 1
        assert result["created"] == 1

    def test_empty_selection_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        sc = _FakeSceneController([])
        result = debug_duplicate_to_grid(sc, [], rows=2, cols=2, dx=10.0, dy=10.0)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# name_mode=numbered
# ---------------------------------------------------------------------------

class TestNameMode:
    def test_numbered_suffix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "name": "Tree"})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(
            sc, ["a"], rows=2, cols=2, dx=10.0, dy=10.0, name_mode="numbered",
        )
        assert result["ok"] is True
        dups = _duplicates(sc)
        names = sorted([d["name"] for d in dups])
        assert "Tree_r0_c1" in names
        assert "Tree_r1_c0" in names
        assert "Tree_r1_c1" in names

    def test_original_name_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "name": "Tree"})
        sc = _FakeSceneController(entities)
        debug_duplicate_to_grid(
            sc, ["a"], rows=1, cols=2, dx=10.0, dy=0.0, name_mode="numbered",
        )
        orig = _ent_by_id(sc, "a")
        assert orig is not None
        assert orig["name"] == "Tree"

    def test_none_mode_keeps_cloned_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "name": "Tree"})
        sc = _FakeSceneController(entities)
        debug_duplicate_to_grid(
            sc, ["a"], rows=1, cols=2, dx=10.0, dy=0.0, name_mode="none",
        )
        dups = _duplicates(sc)
        assert dups[0]["name"] == "Tree"


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------

class TestValidation:
    def test_invalid_rows_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a"], rows=0, cols=2, dx=10.0, dy=10.0)
        assert result["ok"] is False

    def test_invalid_cols_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a"], rows=1, cols=-1, dx=10.0, dy=10.0)
        assert result["ok"] is False

    def test_1x1_include_original_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(sc, ["a"], rows=1, cols=1, dx=10.0, dy=10.0)
        assert result["ok"] is True
        assert result["created"] == 0

    def test_1x1_include_false_creates_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(
            sc, ["a"], rows=1, cols=1, dx=0.0, dy=0.0, include_original=False,
        )
        assert result["ok"] is True
        assert result["created"] == 1

    def test_overlapping_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """dx=0 dy=0 with grid>1 creates overlapping duplicates."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(
            sc, ["a"], rows=2, cols=1, dx=0.0, dy=0.0,
        )
        assert result["ok"] is True
        assert result["created"] == 1  # overlapping at same position


# ---------------------------------------------------------------------------
# Command palette action wiring
# ---------------------------------------------------------------------------

class TestCommandPaletteAction:
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

    def test_kv_format(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_duplicate_to_grid(w, "rows=2|cols=3|dx=16|dy=16")
        captured = capsys.readouterr().out
        assert "action=duplicate_to_grid" in captured
        assert "created=5" in captured

    def test_shorthand_format(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_duplicate_to_grid(w, "2x3 dx=16 dy=16")
        captured = capsys.readouterr().out
        assert "action=duplicate_to_grid" in captured
        assert "created=5" in captured

    def test_empty_arg_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_duplicate_to_grid(w, "")
        captured = capsys.readouterr().out
        assert "noop" in captured

    def test_no_selection_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_duplicate_to_grid

        w = SimpleNamespace(
            entity_select_state=SimpleNamespace(selected_ids=[], primary_id=""),
        )
        action_duplicate_to_grid(w, "2x2 dx=10 dy=10")
        captured = capsys.readouterr().out
        assert "noop" in captured
        assert "no_selection" in captured

    def test_include_false_kv(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_duplicate_to_grid

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        w = self._make_world(entities)
        action_duplicate_to_grid(w, "rows=1|cols=2|dx=10|dy=0|include=0")
        captured = capsys.readouterr().out
        assert "action=duplicate_to_grid" in captured
        assert "created=2" in captured
