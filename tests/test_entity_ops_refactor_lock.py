"""Refactor-lock tests for entity_ops.py.

These tests prove that the migrated debug_* operations no longer call
``find_entity_by_id`` inside their per-ID loops.  They monkeypatch
``find_entity_by_id`` to raise ``AssertionError`` if ever invoked,
then exercise each target op end-to-end.  If any op still reaches
``find_entity_by_id`` the test blows up immediately.

Additionally, determinism tests verify that scatter with the same seed
produces identical output across invocations.
"""
from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _poisoned_find(*args: Any, **kwargs: Any) -> None:  # noqa: ANN401
    raise AssertionError(
        "find_entity_by_id was called — this op should use the entity index instead"
    )


def _make_entities(*specs: dict[str, Any]) -> list[Dict[str, Any]]:
    return [dict(s) for s in specs]


class _FakeSceneController:
    """Minimal stand-in for SceneController used by authoring ops."""

    def __init__(self, entities: list[Dict[str, Any]]) -> None:
        self._authored: Dict[str, Any] = {"entities": copy.deepcopy(entities)}
        self.applied: list[Dict[str, Any]] = []

    # ---- authoring interface used by entity_ops --------------------------
    def get_authored_scene_payload(self) -> Dict[str, Any]:  # noqa: D102
        return self._authored

    def get_runtime_authored_payload(self) -> Dict[str, Any]:  # noqa: D102
        return self._authored


# Patch the two free-standing functions that entity_ops imports at module level.
_AUTHORING_MODULE = "engine.scene_runtime.authoring.entity_ops"


def _patch_authoring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect get/apply helpers to our fake."""
    import engine.scene_runtime.authoring.entity_ops as _mod  # noqa: PLC0415

    monkeypatch.setattr(
        _mod,
        "get_authored_scene_payload",
        lambda ctrl: ctrl.get_authored_scene_payload(),
    )
    monkeypatch.setattr(
        _mod,
        "debug_apply_authored_scene_payload",
        lambda ctrl, payload: _apply(ctrl, payload),
    )


def _apply(ctrl: _FakeSceneController, payload: Dict[str, Any]) -> bool:
    ctrl._authored = copy.deepcopy(payload)
    ctrl.applied.append(copy.deepcopy(payload))
    return True


def _duplicates(ctrl: _FakeSceneController) -> list[Dict[str, Any]]:
    ents = ctrl._authored.get("entities", [])
    return [e for e in ents if isinstance(e, dict) and "__dup" in str(e.get("id", ""))]


# ---------------------------------------------------------------------------
# Poison target — applied to ALL tests in this module
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _poison_find(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch find_entity_by_id to blow up if called."""
    monkeypatch.setattr(
        "engine.entity_paint_mode.find_entity_by_id",
        _poisoned_find,
    )


# ---------------------------------------------------------------------------
# Target op 1: debug_snap_to_grid
# ---------------------------------------------------------------------------

class TestSnapToGridNoFind:
    def test_snap_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_snap_to_grid

        entities = _make_entities(
            {"id": "a", "x": 7.0, "y": 13.0, "prefab_id": "p"},
            {"id": "b", "x": 17.0, "y": 25.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_snap_to_grid(sc, ["a", "b"], step=8, axes="xy", mode="nearest")
        assert result["ok"] is True
        assert result["moved"] == 2
        assert result["skipped"] == 0
        snapped = {e["id"]: e for e in sc._authored["entities"]}
        assert snapped["a"]["x"] == 8.0
        assert snapped["a"]["y"] == 16.0
        assert snapped["b"]["x"] == 16.0
        assert snapped["b"]["y"] == 24.0


# ---------------------------------------------------------------------------
# Target op 2: debug_nudge_selection
# ---------------------------------------------------------------------------

class TestNudgeNoFind:
    def test_nudge_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_nudge_selection

        entities = _make_entities(
            {"id": "a", "x": 10.0, "y": 20.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_nudge_selection(sc, ["a"], dx=5.0, dy=-3.0)
        assert result["ok"] is True
        assert result["moved"] == 1
        ent = sc._authored["entities"][0]
        assert ent["x"] == 15.0
        assert ent["y"] == 17.0


# ---------------------------------------------------------------------------
# Target op 3: debug_rotate_selection
# ---------------------------------------------------------------------------

class TestRotateNoFind:
    def test_rotate_self(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_rotate_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0, "prefab_id": "p"},
            {"id": "b", "x": 10.0, "y": 0.0, "rotation": 90.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_rotate_selection(sc, ["a", "b"], deg=45.0, about="self")
        assert result["ok"] is True
        assert result["rotated"] == 2
        rotated = {e["id"]: e for e in sc._authored["entities"]}
        assert rotated["a"]["rotation"] == pytest.approx(45.0)
        assert rotated["b"]["rotation"] == pytest.approx(135.0)


# ---------------------------------------------------------------------------
# Target op 4: debug_duplicate_to_grid
# ---------------------------------------------------------------------------

class TestDuplicateToGridNoFind:
    def test_grid_2x2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_to_grid

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_duplicate_to_grid(
            sc, ["a"], rows=2, cols=2, dx=16.0, dy=16.0,
            include_original=True,
        )
        assert result["ok"] is True
        assert result["created"] == 3  # 2x2 - 1 original = 3
        dups = _duplicates(sc)
        assert len(dups) == 3


# ---------------------------------------------------------------------------
# Target op 5: debug_scatter_selection
# ---------------------------------------------------------------------------

class TestScatterNoFind:
    def test_scatter_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_scatter_selection(
            sc, ["a"], n=5, seed=42, shape="circle", radius=32.0,
            include_original=False,
        )
        assert result["ok"] is True
        assert result["created"] == 5
        dups = _duplicates(sc)
        assert len(dups) == 5


# ---------------------------------------------------------------------------
# Additional migrated ops — refactor-lock coverage
# ---------------------------------------------------------------------------

class TestSimpleOpsNoFind:
    def test_set_prefab_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_prefab_id

        entities = _make_entities({"id": "a", "prefab_id": "old"})
        sc = _FakeSceneController(entities)
        changed, skipped = debug_set_prefab_id(sc, ["a"], "new")
        assert changed == 1
        assert skipped == 0
        assert sc._authored["entities"][0]["prefab_id"] == "new"

    def test_add_tag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_add_tag

        entities = _make_entities({"id": "a", "tags": []})
        sc = _FakeSceneController(entities)
        changed, skipped = debug_add_tag(sc, ["a"], "mytag")
        assert changed == 1
        assert "mytag" in sc._authored["entities"][0]["tags"]

    def test_remove_tag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_remove_tag

        entities = _make_entities({"id": "a", "tags": ["keep", "remove"]})
        sc = _FakeSceneController(entities)
        changed, skipped = debug_remove_tag(sc, ["a"], "remove")
        assert changed == 1
        assert sc._authored["entities"][0]["tags"] == ["keep"]

    def test_toggle_tag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_toggle_tag

        entities = _make_entities({"id": "a", "tags": ["existing"]})
        sc = _FakeSceneController(entities)
        added, removed, skipped = debug_toggle_tag(sc, ["a"], "existing")
        assert removed == 1
        assert added == 0

    def test_batch_rename(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        entities = _make_entities({"id": "a", "name": "foo"})
        sc = _FakeSceneController(entities)
        changed, skipped = debug_batch_rename(sc, ["a"], prefix="pre_", suffix="_suf")
        assert changed == 1
        assert sc._authored["entities"][0]["name"] == "pre_foo_suf"

    def test_set_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        entities = _make_entities(
            {"id": "a", "name": "old1"},
            {"id": "b", "name": "old2"},
        )
        sc = _FakeSceneController(entities)
        result = debug_set_names(sc, ["a", "b"], base="item", start=1, width=3)
        assert result["ok"] is True
        assert result["renamed"] == 2
        names = {e["id"]: e["name"] for e in sc._authored["entities"]}
        assert names["a"] == "item_001"
        assert names["b"] == "item_002"

    def test_add_behaviour(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_add_behaviour

        entities = _make_entities({"id": "a", "behaviours": []})
        sc = _FakeSceneController(entities)
        changed, skipped = debug_add_behaviour(sc, ["a"], "Patrol")
        assert changed == 1

    def test_remove_behaviour(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_remove_behaviour

        entities = _make_entities({"id": "a", "behaviours": ["Patrol", "Guard"]})
        sc = _FakeSceneController(entities)
        changed, skipped = debug_remove_behaviour(sc, ["a"], "Patrol")
        assert changed == 1


# ---------------------------------------------------------------------------
# Spatial ops — refactor-lock coverage
# ---------------------------------------------------------------------------

class TestSpatialOpsNoFind:
    def test_align(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_align_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "prefab_id": "p"},
            {"id": "b", "x": 10.0, "y": 5.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_align_selection(sc, ["a", "b"], axis="x", mode="left", reference="group")
        assert result["ok"] is True

    def test_distribute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_distribute_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "prefab_id": "p"},
            {"id": "b", "x": 50.0, "y": 0.0, "prefab_id": "p"},
            {"id": "c", "x": 100.0, "y": 0.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_distribute_selection(
            sc, ["a", "b", "c"], axis="x", mode="center",
        )
        assert result["ok"] is True

    def test_mirror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_mirror_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 0.0, "prefab_id": "p"},
            {"id": "b", "x": 10.0, "y": 0.0, "rotation": 0.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_mirror_selection(sc, ["a", "b"], axis="x", about="group")
        assert result["ok"] is True

    def test_duplicate_along_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_duplicate_along_path

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_duplicate_along_path(
            sc, ["a"], from_x=0, from_y=0, to_x=100, to_y=0,
            count=3, include_original=True,
        )
        assert result["ok"] is True
        assert result["created"] == 2  # 3 points - 1 original

    def test_group_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "prefab_id": "p"},
            {"id": "b", "x": 10.0, "y": 0.0, "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b"])
        assert result["ok"] is True
        assert result["linked"] == 2

    def test_ungroup_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_ungroup_selection

        entities = _make_entities(
            {"id": "group_1", "x": 5.0, "y": 0.0, "is_group": True, "tags": ["group"]},
            {"id": "a", "x": 0.0, "y": 0.0, "group_id": "group_1", "prefab_id": "p"},
            {"id": "b", "x": 10.0, "y": 0.0, "group_id": "group_1", "prefab_id": "p"},
        )
        sc = _FakeSceneController(entities)
        result = debug_ungroup_selection(sc, ["group_1"])
        assert result["ok"] is True
        assert result["unlinked"] == 2
        assert result["deleted_group"] is True


# ---------------------------------------------------------------------------
# Config ops — refactor-lock coverage
# ---------------------------------------------------------------------------

class TestConfigOpsNoFind:
    def test_config_mutate_for_behaviour(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_config_triggerzone_set_zone_id

        entities = _make_entities({
            "id": "a",
            "behaviours": ["TriggerZone"],
            "behaviour_config": {"TriggerZone": {"zone_id": "old"}},
        })
        sc = _FakeSceneController(entities)
        changed, skip_p, skip_b = debug_config_triggerzone_set_zone_id(sc, ["a"], "new_zone")
        assert changed == 1
        cfg = sc._authored["entities"][0]["behaviour_config"]["TriggerZone"]
        assert cfg["zone_id"] == "new_zone"


# ---------------------------------------------------------------------------
# Scatter determinism
# ---------------------------------------------------------------------------

class TestScatterDeterminism:
    def test_same_seed_identical_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_scatter_selection

        def _run(seed: int = 99) -> list[Dict[str, Any]]:
            entities = _make_entities(
                {"id": "a", "x": 0.0, "y": 0.0, "prefab_id": "p"},
                {"id": "b", "x": 10.0, "y": 0.0, "prefab_id": "p"},
            )
            sc = _FakeSceneController(entities)
            debug_scatter_selection(
                sc, ["a", "b"], n=10, seed=seed,
                shape="circle", radius=100.0,
                include_original=False,
                jitter_rot_deg=15.0,
            )
            return _duplicates(sc)

        run1 = _run(seed=99)
        run2 = _run(seed=99)
        assert len(run1) == len(run2)
        for d1, d2 in zip(run1, run2):
            assert d1["id"] == d2["id"]
            assert d1["x"] == pytest.approx(d2["x"])
            assert d1["y"] == pytest.approx(d2["y"])
            assert d1.get("rotation", 0.0) == pytest.approx(d2.get("rotation", 0.0))

        # Different seed → different output
        run3 = _run(seed=123)
        positions_99 = [(d["x"], d["y"]) for d in run1]
        positions_123 = [(d["x"], d["y"]) for d in run3]
        assert positions_99 != positions_123
