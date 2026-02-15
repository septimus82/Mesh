"""Fast-tier tests for Selection: Scatter… editor authoring action.

Validates:
- deterministic: same seed → identical positions/names/rotations
- different seed → at least one position differs
- circle sampling stays within radius
- rect sampling stays within bounds
- include_original logic: created == (n-1)*len(selection) when include=1
- snap_step applied correctly (half-up ties)
- jitter rotation applied deterministically; 0 jitter leaves rotation unchanged
- skip player / no-position entities
- validation: n < 1, radius <= 0, etc.
- command palette parsing (kv + shorthand)
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

    def debug_scatter_selection(
        self,
        entity_ids: list[str],
        n: int = 1,
        shape: str = "circle",
        radius: float = 64.0,
        width: float = 128.0,
        height: float = 128.0,
        center: str = "group",
        seed: int = 0,
        jitter_rot_deg: float = 0.0,
        snap_step: int | None = None,
        include_original: bool = True,
        name_mode: str = "none",
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_scatter_selection(
            self, entity_ids, n=n, shape=shape,
            radius=radius, width=width, height=height,
            center=center, seed=seed,
            jitter_rot_deg=jitter_rot_deg, snap_step=snap_step,
            include_original=include_original,
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
# Determinism
# ---------------------------------------------------------------------------

class TestScatterDeterminism:
    def test_same_seed_same_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        base = [{"id": "a", "x": 10.0, "y": 20.0}]
        sc1 = _FakeSceneController(_make_entities(*base))
        r1 = debug_scatter_selection(sc1, ["a"], n=5, radius=100.0, seed=42)

        sc2 = _FakeSceneController(_make_entities(*base))
        r2 = debug_scatter_selection(sc2, ["a"], n=5, radius=100.0, seed=42)

        d1 = [(d["id"], d["x"], d["y"]) for d in _duplicates(sc1)]
        d2 = [(d["id"], d["x"], d["y"]) for d in _duplicates(sc2)]
        assert d1 == d2
        assert r1["created"] == r2["created"]

    def test_different_seed_different_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        base = [{"id": "a", "x": 0.0, "y": 0.0}]
        sc1 = _FakeSceneController(_make_entities(*base))
        debug_scatter_selection(sc1, ["a"], n=5, radius=100.0, seed=1)

        sc2 = _FakeSceneController(_make_entities(*base))
        debug_scatter_selection(sc2, ["a"], n=5, radius=100.0, seed=2)

        pos1 = [(d["x"], d["y"]) for d in _duplicates(sc1)]
        pos2 = [(d["x"], d["y"]) for d in _duplicates(sc2)]
        assert pos1 != pos2

    def test_shuffled_ids_same_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        base = [
            {"id": "c", "x": 30.0, "y": 0.0},
            {"id": "a", "x": 10.0, "y": 0.0},
            {"id": "b", "x": 20.0, "y": 0.0},
        ]

        sc1 = _FakeSceneController(_make_entities(*base))
        debug_scatter_selection(sc1, ["c", "a", "b"], n=3, seed=99)

        sc2 = _FakeSceneController(_make_entities(*base))
        debug_scatter_selection(sc2, ["b", "c", "a"], n=3, seed=99)

        d1 = [(d["id"], d["x"], d["y"]) for d in _duplicates(sc1)]
        d2 = [(d["id"], d["x"], d["y"]) for d in _duplicates(sc2)]
        assert d1 == d2


# ---------------------------------------------------------------------------
# Circle sampling
# ---------------------------------------------------------------------------

class TestScatterCircle:
    def test_within_radius(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=50, shape="circle", radius=64.0,
            seed=7, include_original=False,
        )
        assert result["ok"] is True
        assert result["created"] == 50
        for d in _duplicates(sc):
            dist = math.sqrt(d["x"] ** 2 + d["y"] ** 2)
            assert dist <= 64.0 + 1e-9, f"duplicate at ({d['x']}, {d['y']}) dist={dist}"

    def test_created_count_include_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 5.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a", "b"], n=4, seed=0, include_original=True,
        )
        assert result["ok"] is True
        # (n-1) * 2 entities = 3 * 2 = 6
        assert result["created"] == 6

    def test_no_include_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=3, seed=0, include_original=False,
        )
        assert result["ok"] is True
        assert result["created"] == 3


# ---------------------------------------------------------------------------
# Rect sampling
# ---------------------------------------------------------------------------

class TestScatterRect:
    def test_within_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=50, shape="rect", width=100.0, height=80.0,
            seed=13, include_original=False,
        )
        assert result["ok"] is True
        assert result["created"] == 50
        for d in _duplicates(sc):
            assert -50.0 - 1e-9 <= d["x"] <= 50.0 + 1e-9
            assert -40.0 - 1e-9 <= d["y"] <= 40.0 + 1e-9


# ---------------------------------------------------------------------------
# Snap
# ---------------------------------------------------------------------------

class TestScatterSnap:
    def test_snap_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=10, shape="circle", radius=100.0,
            seed=42, snap_step=16, include_original=False,
        )
        assert result["ok"] is True
        for d in _duplicates(sc):
            assert d["x"] % 16 == pytest.approx(0.0, abs=1e-9)
            assert d["y"] % 16 == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Jitter rotation
# ---------------------------------------------------------------------------

class TestScatterRotation:
    def test_zero_jitter_preserves_rotation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 45.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=3, seed=0, jitter_rot_deg=0.0,
        )
        assert result["ok"] is True
        for d in _duplicates(sc):
            # rotation should NOT be set when jitter is 0
            assert d.get("rotation") == 45.0  # deep-copied original

    def test_nonzero_jitter_deterministic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        base = [{"id": "a", "x": 0.0, "y": 0.0, "rotation": 90.0}]
        sc1 = _FakeSceneController(_make_entities(*base))
        debug_scatter_selection(sc1, ["a"], n=5, seed=7, jitter_rot_deg=30.0)

        sc2 = _FakeSceneController(_make_entities(*base))
        debug_scatter_selection(sc2, ["a"], n=5, seed=7, jitter_rot_deg=30.0)

        rots1 = [d["rotation"] for d in _duplicates(sc1)]
        rots2 = [d["rotation"] for d in _duplicates(sc2)]
        assert rots1 == rots2
        # At least one should differ from 90.0 given jitter=30
        assert any(abs(r - 90.0) > 0.01 for r in rots1)

    def test_jitter_within_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 180.0})
        sc = _FakeSceneController(entities)
        debug_scatter_selection(
            sc, ["a"], n=50, seed=42, jitter_rot_deg=10.0, include_original=False,
        )
        for d in _duplicates(sc):
            # rotation = (180 + jitter) % 360 → should be near 180 ± 10
            rot = d["rotation"]
            # Normalize to distance from 180
            diff = min(abs(rot - 180.0), 360.0 - abs(rot - 180.0))
            assert diff <= 10.0 + 1e-9


# ---------------------------------------------------------------------------
# Skip / validation
# ---------------------------------------------------------------------------

class TestScatterValidation:
    def test_skip_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities(
            {"id": "p", "x": 0.0, "y": 0.0, "player": True},
            {"id": "a", "x": 10.0, "y": 10.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(sc, ["p", "a"], n=3, seed=0)
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["created"] == 2  # (n-1) * 1 participant

    def test_skip_no_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a"})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(sc, ["a"], n=3, seed=0)
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["created"] == 0

    def test_empty_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(sc, [], n=3, seed=0)
        assert result["ok"] is False

    def test_n_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(sc, ["a"], n=0, seed=0)
        assert result["ok"] is False

    def test_negative_radius(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=3, shape="circle", radius=-5, seed=0,
        )
        assert result["ok"] is False

    def test_zero_width_rect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=3, shape="rect", width=0, height=100, seed=0,
        )
        assert result["ok"] is False

    def test_invalid_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=3, shape="hexagon", seed=0,
        )
        assert result["ok"] is False

    def test_invalid_center(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=3, center="nowhere", seed=0,
        )
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

class TestScatterNaming:
    def test_name_mode_numbered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "tree", "x": 0.0, "y": 0.0, "name": "Oak"})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["tree"], n=4, seed=0, name_mode="numbered",
        )
        assert result["ok"] is True
        assert result["created"] == 3
        dups = _duplicates(sc)
        names = sorted(d.get("name", "") for d in dups)
        assert names == ["Oak_s001", "Oak_s002", "Oak_s003"]

    def test_name_mode_none_preserves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "name": "Flower"})
        sc = _FakeSceneController(entities)
        debug_scatter_selection(sc, ["a"], n=3, seed=0)
        for d in _duplicates(sc):
            assert d.get("name") == "Flower"


# ---------------------------------------------------------------------------
# Center modes
# ---------------------------------------------------------------------------

class TestScatterCenter:
    def test_center_origin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With center=origin and seed giving known offsets, pivot is (0,0)."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities({"id": "a", "x": 50.0, "y": 50.0})
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=2, seed=0, center="origin", include_original=False,
            shape="circle", radius=0.001,  # tiny radius → near (0,0)
        )
        assert result["ok"] is True
        dups = _duplicates(sc)
        # Rel offset = (50-0, 50-0) = (50,50) added to scatter near (0,0)
        for d in dups:
            # Should be near 50,50 (the rel offset from origin pivot)
            assert abs(d["x"] - 50.0) < 1.0
            assert abs(d["y"] - 50.0) < 1.0

    def test_center_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 10.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        # centroid = (5, 0)
        result = debug_scatter_selection(
            sc, ["a", "b"], n=1, seed=0, center="group",
            shape="circle", radius=0.001, include_original=False,
        )
        assert result["ok"] is True
        dups = _duplicates(sc)
        # "a" rel=(-5,0), "b" rel=(5,0); both near centroid (5,0)
        a_dups = [d for d in dups if d["id"].startswith("a__")]
        b_dups = [d for d in dups if d["id"].startswith("b__")]
        assert len(a_dups) == 1
        assert len(b_dups) == 1
        # a_dup near (5-5, 0) = (0, 0); b_dup near (5+5, 0) = (10, 0)
        assert abs(a_dups[0]["x"] - 0.0) < 1.0
        assert abs(b_dups[0]["x"] - 10.0) < 1.0


# ---------------------------------------------------------------------------
# Multi-entity group shape preservation
# ---------------------------------------------------------------------------

class TestScatterGroupShape:
    def test_relative_positions_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two entities 10 apart should stay 10 apart in each scatter group."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 10.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a", "b"], n=5, seed=42, include_original=True,
        )
        assert result["ok"] is True
        assert result["created"] == 8  # (5-1) * 2

        dups = _duplicates(sc)
        # Group by scatter index (same point → a__dup and b__dup created in sequence)
        a_dups = sorted([d for d in dups if d["id"].startswith("a__")], key=lambda d: d["id"])
        b_dups = sorted([d for d in dups if d["id"].startswith("b__")], key=lambda d: d["id"])
        assert len(a_dups) == 4
        assert len(b_dups) == 4
        for ad, bd in zip(a_dups, b_dups):
            dx = bd["x"] - ad["x"]
            dy = bd["y"] - ad["y"]
            assert dx == pytest.approx(10.0)
            assert dy == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Command palette parsing
# ---------------------------------------------------------------------------

class TestScatterParsing:
    def _run_action(
        self, monkeypatch: pytest.MonkeyPatch, arg: str,
    ) -> tuple[dict[str, Any] | None, Any]:
        _patch_authoring(monkeypatch)
        captured: list[dict[str, Any]] = []

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0, "name": "Test"})

        class _FakeSC(_FakeSceneController):
            def debug_scatter_selection(self_inner, entity_ids, **kwargs):
                import engine.scene_runtime.authoring.entity_ops as _ops
                r = _ops.debug_scatter_selection(self_inner, entity_ids, **kwargs)
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

        from engine.command_palette_registry import action_scatter_selection
        action_scatter_selection(world, arg)
        return captured[0] if captured else None, sc

    def test_kv_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result, sc = self._run_action(
            monkeypatch,
            "n=5|shape=circle|radius=64|center=group|seed=42|rot=10|snap=16|include=1|name=numbered",
        )
        assert result is not None
        assert result["ok"] is True
        assert result["created"] == 4  # (5-1)*1
        assert result["shape"] == "circle"
        assert result["seed"] == 42
        dups = _duplicates(sc)
        names = sorted(d.get("name", "") for d in dups)
        assert names == ["Test_s001", "Test_s002", "Test_s003", "Test_s004"]
        # All snapped
        for d in dups:
            assert d["x"] % 16 == pytest.approx(0.0, abs=1e-9)

    def test_shorthand_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result, _sc = self._run_action(
            monkeypatch,
            "5 seed=42 radius=128",
        )
        assert result is not None
        assert result["ok"] is True
        assert result["created"] == 4  # (5-1)*1

    def test_kv_rect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result, sc = self._run_action(
            monkeypatch,
            "n=3|shape=rect|width=100|height=80|seed=7|include=0",
        )
        assert result is not None
        assert result["ok"] is True
        assert result["created"] == 3
        assert result["shape"] == "rect"
        for d in _duplicates(sc):
            assert -50.0 - 1e-9 <= d["x"] <= 50.0 + 1e-9
            assert -40.0 - 1e-9 <= d["y"] <= 40.0 + 1e-9

    def test_empty_arg_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result, _sc = self._run_action(monkeypatch, "")
        assert result is None
