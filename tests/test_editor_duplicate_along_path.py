"""Fast-tier tests for Selection: Duplicate Along Path… editor authoring action.

Validates:
- correct duplicate count with include_original on/off
- linear interpolation positions along line segment
- count=1 single point placement
- from==to yields zero-offset duplicates
- skip player / no-position entities
- name_mode=numbered suffix on duplicates only
- orient sets rotation to segment angle
- deterministic ordering (shuffled selection yields identical result)
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

    def debug_duplicate_along_path(
        self,
        entity_ids: list[str],
        from_x: float = 0.0,
        from_y: float = 0.0,
        to_x: float = 0.0,
        to_y: float = 0.0,
        count: int = 2,
        include_original: bool = True,
        origin: str = "selection",
        name_mode: str = "none",
        orient: bool = False,
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_duplicate_along_path(
            self, entity_ids, from_x=from_x, from_y=from_y,
            to_x=to_x, to_y=to_y, count=count,
            include_original=include_original, origin=origin,
            name_mode=name_mode, orient=orient,
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
# Basic duplication
# ---------------------------------------------------------------------------

class TestDuplicateAlongPathBasic:
    def test_3_points_include_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """count=3, include_original → 2 duplicates (skip i=0)."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 10.0, "y": 20.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=10.0, from_y=20.0, to_x=110.0, to_y=20.0, count=3,
        )
        assert result["ok"] is True
        assert result["created"] == 2

        dups = _duplicates(sc)
        assert len(dups) == 2
        xs = sorted([d["x"] for d in dups])
        # t=0.5 → 60, t=1.0 → 110; offsets from from_x=10 → 50, 100
        # entity at x=10 → 10+50=60, 10+100=110
        assert xs == pytest.approx([60.0, 110.0])

    def test_include_original_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """include_original=False → count duplicates (including at from)."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0.0, from_y=0.0, to_x=100.0, to_y=0.0,
            count=3, include_original=False,
        )
        assert result["ok"] is True
        assert result["created"] == 3

        dups = _duplicates(sc)
        xs = sorted([d["x"] for d in dups])
        assert xs == pytest.approx([0.0, 50.0, 100.0])

    def test_count_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """count=1, include_original → skip i=0 → 0 created."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 5.0, "y": 5.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=5.0, from_y=5.0, to_x=100.0, to_y=100.0, count=1,
        )
        assert result["ok"] is True
        assert result["created"] == 0

    def test_count_1_no_include(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """count=1, include_original=False → 1 duplicate at from."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 5.0, "y": 5.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=5.0, from_y=5.0, to_x=100.0, to_y=100.0,
            count=1, include_original=False,
        )
        assert result["ok"] is True
        assert result["created"] == 1
        dup = _duplicates(sc)[0]
        # t=0 → offset 0,0 → at original position
        assert dup["x"] == pytest.approx(5.0)
        assert dup["y"] == pytest.approx(5.0)

    def test_from_equals_to(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """from==to → all duplicates at same position."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 10.0, "y": 20.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=10.0, from_y=20.0, to_x=10.0, to_y=20.0, count=3,
        )
        assert result["ok"] is True
        assert result["created"] == 2
        for d in _duplicates(sc):
            assert d["x"] == pytest.approx(10.0)
            assert d["y"] == pytest.approx(20.0)

    def test_diagonal_segment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Diagonal segment with count=3 → verify both x and y interpolation."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0.0, from_y=0.0, to_x=100.0, to_y=200.0, count=3,
        )
        assert result["ok"] is True
        assert result["created"] == 2
        dups = sorted(_duplicates(sc), key=lambda e: e["x"])
        assert dups[0]["x"] == pytest.approx(50.0)
        assert dups[0]["y"] == pytest.approx(100.0)
        assert dups[1]["x"] == pytest.approx(100.0)
        assert dups[1]["y"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Skip / validation
# ---------------------------------------------------------------------------

class TestDuplicateAlongPathSkip:
    def test_skip_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities(
            {"id": "p", "x": 0.0, "y": 0.0, "player": True},
            {"id": "a", "x": 10.0, "y": 10.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["p", "a"], from_x=0.0, from_y=0.0, to_x=64.0, to_y=0.0, count=2,
        )
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["created"] == 1

    def test_skip_no_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a"})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0.0, from_y=0.0, to_x=64.0, to_y=0.0, count=2,
        )
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["created"] == 0

    def test_empty_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, [], from_x=0.0, from_y=0.0, to_x=64.0, to_y=0.0, count=2,
        )
        assert result["ok"] is False

    def test_invalid_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0.0, from_y=0.0, to_x=64.0, to_y=0.0, count=0,
        )
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

class TestDuplicateAlongPathNaming:
    def test_name_mode_numbered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "tree", "x": 0.0, "y": 0.0, "name": "Oak"})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["tree"], from_x=0.0, from_y=0.0, to_x=100.0, to_y=0.0,
            count=3, name_mode="numbered",
        )
        assert result["ok"] is True
        assert result["created"] == 2
        dups = sorted(_duplicates(sc), key=lambda e: e["x"])
        assert dups[0]["name"] == "Oak_p001"
        assert dups[1]["name"] == "Oak_p002"

    def test_name_mode_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "name": "Flower"})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0.0, from_y=0.0, to_x=64.0, to_y=0.0, count=2,
        )
        assert result["ok"] is True
        dups = _duplicates(sc)
        # name should be unchanged (deep-copied from original)
        for d in dups:
            assert d.get("name") == "Flower"


# ---------------------------------------------------------------------------
# Orient
# ---------------------------------------------------------------------------

class TestDuplicateAlongPathOrient:
    def test_orient_horizontal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0.0, from_y=0.0, to_x=100.0, to_y=0.0,
            count=2, orient=True,
        )
        assert result["ok"] is True
        dup = _duplicates(sc)[0]
        assert dup["rotation"] == pytest.approx(0.0)

    def test_orient_45_degrees(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0.0, from_y=0.0, to_x=100.0, to_y=100.0,
            count=2, orient=True,
        )
        assert result["ok"] is True
        dup = _duplicates(sc)[0]
        assert dup["rotation"] == pytest.approx(45.0)

    def test_orient_vertical(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0.0, from_y=0.0, to_x=0.0, to_y=100.0,
            count=2, orient=True,
        )
        assert result["ok"] is True
        dup = _duplicates(sc)[0]
        assert dup["rotation"] == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDuplicateAlongPathDeterminism:
    def test_shuffled_ids_produce_same_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        base = [
            {"id": "c", "x": 30.0, "y": 0.0},
            {"id": "a", "x": 10.0, "y": 0.0},
            {"id": "b", "x": 20.0, "y": 0.0},
        ]
        ids_a = ["c", "a", "b"]
        ids_b = ["b", "c", "a"]

        sc_a = _FakeSceneController(_make_entities(*base))
        result_a = debug_duplicate_along_path(
            sc_a, ids_a, from_x=0.0, from_y=0.0, to_x=100.0, to_y=0.0, count=3,
        )

        sc_b = _FakeSceneController(_make_entities(*base))
        result_b = debug_duplicate_along_path(
            sc_b, ids_b, from_x=0.0, from_y=0.0, to_x=100.0, to_y=0.0, count=3,
        )

        dups_a = [(d["id"], d["x"], d["y"]) for d in _duplicates(sc_a)]
        dups_b = [(d["id"], d["x"], d["y"]) for d in _duplicates(sc_b)]
        assert dups_a == dups_b


# ---------------------------------------------------------------------------
# Multiple entities
# ---------------------------------------------------------------------------

class TestDuplicateAlongPathMultiple:
    def test_two_entities_along_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 5.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a", "b"], from_x=0.0, from_y=0.0, to_x=100.0, to_y=0.0, count=2,
        )
        assert result["ok"] is True
        # count=2, include_original → skip i=0, create at i=1 for both entities → 2
        assert result["created"] == 2
        dups = _duplicates(sc)
        dups_by_id = {d["id"]: d for d in dups}
        assert dups_by_id["a__dup1"]["x"] == pytest.approx(100.0)
        assert dups_by_id["b__dup1"]["x"] == pytest.approx(105.0)


# ---------------------------------------------------------------------------
# Command palette parsing
# ---------------------------------------------------------------------------

class TestDuplicateAlongPathParsing:
    def _run_action(
        self, monkeypatch: pytest.MonkeyPatch, arg: str
    ) -> tuple[dict[str, Any] | None, Any]:
        _patch_authoring(monkeypatch)
        captured: list[dict[str, Any]] = []

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "name": "Test"})

        class _FakeSC(_FakeSceneController):
            def debug_duplicate_along_path(self_inner, entity_ids, **kwargs):
                import engine.scene_runtime.authoring.entity_ops as _ops
                r = _ops.debug_duplicate_along_path(self_inner, entity_ids, **kwargs)
                captured.append(r)
                return r

        sc = _FakeSC(entities)

        world = SimpleNamespace(
            scene_controller=sc,
            entity_select_state=SimpleNamespace(
                selected_ids=["a"], primary_id="a",
            ),
        )

        monkeypatch.setattr(
            "engine.command_palette_registry._get_authored_payload",
            lambda w: sc.get_authored_scene_payload(),
        )

        from engine.command_palette_registry import action_duplicate_along_path
        action_duplicate_along_path(world, arg)
        return captured[0] if captured else None, sc

    def test_kv_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result, sc = self._run_action(
            monkeypatch,
            "from=0,0|to=100,0|count=3|include=1|name=numbered|orient=1",
        )
        assert result is not None
        assert result["ok"] is True
        assert result["created"] == 2
        assert result["orient"] is True
        dups = _duplicates(sc)
        names = sorted(d.get("name", "") for d in dups)
        assert names == ["Test_p001", "Test_p002"]

    def test_shorthand_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result, sc = self._run_action(
            monkeypatch,
            "0,0 100,0 3",
        )
        assert result is not None
        assert result["ok"] is True
        assert result["created"] == 2
        dups = sorted(_duplicates(sc), key=lambda e: e["x"])
        assert dups[0]["x"] == pytest.approx(50.0)
        assert dups[1]["x"] == pytest.approx(100.0)

    def test_shorthand_with_named_opts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result, sc = self._run_action(
            monkeypatch,
            "0,0 100,0 3 name=numbered orient=1",
        )
        assert result is not None
        assert result["ok"] is True
        assert result["orient"] is True
        dups = sorted(_duplicates(sc), key=lambda e: e["x"])
        assert dups[0].get("name") == "Test_p001"

    def test_empty_arg_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result, _sc = self._run_action(monkeypatch, "")
        assert result is None
