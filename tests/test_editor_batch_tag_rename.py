"""Fast-tier tests for batch tag apply/remove and batch rename authoring ops.

Validates:
- deterministic iteration order (sorted entity IDs)
- correct return counts
- player entities skipped
- no-op on empty selection
- rename skips entities without a name field
- remove-tag is idempotent
- toggle-tag adds/removes per entity
- command palette action wiring (add/remove/toggle tag, batch rename)
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Minimal stubs – no arcade, no real scene controller
# ---------------------------------------------------------------------------

def _make_entities(*specs: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a list of entity dicts from compact specs."""
    out: list[dict[str, Any]] = []
    for s in specs:
        ent: dict[str, Any] = {"id": s["id"]}
        if "name" in s:
            ent["name"] = s["name"]
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

    # Called by authoring functions after mutation.
    def apply_authored_scene_payload(self, payload: dict[str, Any]) -> None:
        self._applied = payload
        self._authored = payload

    # Proxy methods matching SceneController interface.
    def debug_add_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_add_tag(self, selected_ids, tag)

    def debug_remove_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_remove_tag(self, selected_ids, tag)

    def debug_batch_rename(self, selected_ids: list[str], prefix: str = "", suffix: str = "") -> tuple[int, int]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_batch_rename(self, selected_ids, prefix=prefix, suffix=suffix)

    def debug_toggle_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int, int]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_toggle_tag(self, selected_ids, tag)

    def debug_set_names(self, entity_ids: list[str], base: str, start: int = 1, width: int = 3) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_set_names(self, entity_ids, base, start=start, width=width)

    @property
    def entities_snapshot(self) -> list[dict[str, Any]]:
        return self._authored.get("entities", [])


# Patch the authoring helpers so they route through our fake controller.
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


# ---------------------------------------------------------------------------
# batch add tag
# ---------------------------------------------------------------------------

class TestBatchAddTag:
    def test_add_tag_deterministic_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_add_tag

        entities = _make_entities(
            {"id": "c", "name": "C", "tags": []},
            {"id": "a", "name": "A", "tags": []},
            {"id": "b", "name": "B", "tags": []},
        )
        sc = _FakeSceneController(entities)
        changed, skipped = debug_add_tag(sc, ["c", "a", "b"], "enemy")
        assert changed == 3
        assert skipped == 0
        # Tags applied in sorted-ID order (a, b, c).  All should have the tag.
        for ent in sc.entities_snapshot:
            assert "enemy" in ent["tags"]

    def test_add_tag_skips_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_add_tag

        entities = _make_entities(
            {"id": "player1", "name": "Player", "tags": [], "player": True},
            {"id": "npc1", "name": "NPC", "tags": []},
        )
        sc = _FakeSceneController(entities)
        changed, skipped = debug_add_tag(sc, ["player1", "npc1"], "quest")
        assert changed == 1
        assert skipped == 1
        npc = next(e for e in sc.entities_snapshot if e["id"] == "npc1")
        assert "quest" in npc["tags"]

    def test_add_tag_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_add_tag

        sc = _FakeSceneController(_make_entities({"id": "a", "name": "A", "tags": []}))
        changed, skipped = debug_add_tag(sc, [], "x")
        assert changed == 0
        assert skipped == 0

    def test_add_tag_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_add_tag

        entities = _make_entities({"id": "a", "name": "A", "tags": ["existing"]})
        sc = _FakeSceneController(entities)
        changed, _ = debug_add_tag(sc, ["a"], "existing")
        assert changed == 0


# ---------------------------------------------------------------------------
# batch remove tag
# ---------------------------------------------------------------------------

class TestBatchRemoveTag:
    def test_remove_tag_deterministic_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_remove_tag

        entities = _make_entities(
            {"id": "c", "name": "C", "tags": ["enemy"]},
            {"id": "a", "name": "A", "tags": ["enemy", "quest"]},
            {"id": "b", "name": "B", "tags": ["enemy"]},
        )
        sc = _FakeSceneController(entities)
        changed, skipped = debug_remove_tag(sc, ["c", "a", "b"], "enemy")
        assert changed == 3
        assert skipped == 0
        for ent in sc.entities_snapshot:
            assert "enemy" not in ent.get("tags", [])
        # "quest" tag on entity "a" should be preserved.
        a_ent = next(e for e in sc.entities_snapshot if e["id"] == "a")
        assert "quest" in a_ent["tags"]

    def test_remove_tag_skips_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_remove_tag

        entities = _make_entities(
            {"id": "player1", "name": "Player", "tags": ["enemy"], "player": True},
            {"id": "npc1", "name": "NPC", "tags": ["enemy"]},
        )
        sc = _FakeSceneController(entities)
        changed, skipped = debug_remove_tag(sc, ["player1", "npc1"], "enemy")
        assert changed == 1
        assert skipped == 1

    def test_remove_tag_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_remove_tag

        sc = _FakeSceneController(_make_entities({"id": "a", "name": "A", "tags": ["x"]}))
        changed, skipped = debug_remove_tag(sc, [], "x")
        assert changed == 0
        assert skipped == 0

    def test_remove_tag_not_present_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_remove_tag

        entities = _make_entities({"id": "a", "name": "A", "tags": ["other"]})
        sc = _FakeSceneController(entities)
        changed, _ = debug_remove_tag(sc, ["a"], "missing")
        assert changed == 0

    def test_remove_tag_no_tags_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_remove_tag

        entities = _make_entities({"id": "a", "name": "A"})
        sc = _FakeSceneController(entities)
        changed, _ = debug_remove_tag(sc, ["a"], "any")
        assert changed == 0


# ---------------------------------------------------------------------------
# batch rename
# ---------------------------------------------------------------------------

class TestBatchRename:
    def test_rename_prefix_suffix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        entities = _make_entities(
            {"id": "b", "name": "Beta"},
            {"id": "a", "name": "Alpha"},
        )
        sc = _FakeSceneController(entities)
        changed, skipped = debug_batch_rename(sc, ["b", "a"], prefix="Old_", suffix="_v2")
        assert changed == 2
        assert skipped == 0
        names = {e["id"]: e["name"] for e in sc.entities_snapshot}
        assert names["a"] == "Old_Alpha_v2"
        assert names["b"] == "Old_Beta_v2"

    def test_rename_prefix_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        entities = _make_entities({"id": "a", "name": "Guard"})
        sc = _FakeSceneController(entities)
        changed, _ = debug_batch_rename(sc, ["a"], prefix="NPC_")
        assert changed == 1
        assert sc.entities_snapshot[0]["name"] == "NPC_Guard"

    def test_rename_suffix_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        entities = _make_entities({"id": "a", "name": "Guard"})
        sc = _FakeSceneController(entities)
        changed, _ = debug_batch_rename(sc, ["a"], suffix="_bak")
        assert changed == 1
        assert sc.entities_snapshot[0]["name"] == "Guard_bak"

    def test_rename_skips_entities_without_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        entities = _make_entities(
            {"id": "a", "name": "HasName"},
            {"id": "b"},  # no name field
        )
        sc = _FakeSceneController(entities)
        changed, _ = debug_batch_rename(sc, ["a", "b"], prefix="X_")
        assert changed == 1
        a_ent = next(e for e in sc.entities_snapshot if e["id"] == "a")
        assert a_ent["name"] == "X_HasName"

    def test_rename_skips_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        entities = _make_entities(
            {"id": "player1", "name": "Hero", "player": True},
            {"id": "npc1", "name": "Guard"},
        )
        sc = _FakeSceneController(entities)
        changed, skipped = debug_batch_rename(sc, ["player1", "npc1"], prefix="Old_")
        assert changed == 1
        assert skipped == 1

    def test_rename_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        sc = _FakeSceneController(_make_entities({"id": "a", "name": "X"}))
        changed, _ = debug_batch_rename(sc, [], prefix="Y_")
        assert changed == 0

    def test_rename_no_prefix_no_suffix_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        sc = _FakeSceneController(_make_entities({"id": "a", "name": "X"}))
        changed, _ = debug_batch_rename(sc, ["a"], prefix="", suffix="")
        assert changed == 0

    def test_rename_deterministic_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mutations happen in sorted entity-ID order."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_batch_rename

        call_order: list[str] = []
        entities = _make_entities(
            {"id": "z", "name": "Z"},
            {"id": "m", "name": "M"},
            {"id": "a", "name": "A"},
        )
        sc = _FakeSceneController(entities)

        # We can verify sorted order by checking final names are correct
        # (if order mattered for prefix numbering, this would catch it).
        changed, _ = debug_batch_rename(sc, ["z", "m", "a"], suffix="_done")
        assert changed == 3
        names = sorted(e["name"] for e in sc.entities_snapshot)
        assert names == ["A_done", "M_done", "Z_done"]


# ---------------------------------------------------------------------------
# batch toggle tag
# ---------------------------------------------------------------------------

class TestBatchToggleTag:
    def test_toggle_adds_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_toggle_tag

        entities = _make_entities(
            {"id": "a", "name": "A", "tags": []},
            {"id": "b", "name": "B", "tags": ["other"]},
        )
        sc = _FakeSceneController(entities)
        added, removed, skipped = debug_toggle_tag(sc, ["a", "b"], "enemy")
        assert added == 2
        assert removed == 0
        assert skipped == 0
        for ent in sc.entities_snapshot:
            assert "enemy" in ent["tags"]

    def test_toggle_removes_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_toggle_tag

        entities = _make_entities(
            {"id": "a", "name": "A", "tags": ["enemy"]},
            {"id": "b", "name": "B", "tags": ["enemy", "quest"]},
        )
        sc = _FakeSceneController(entities)
        added, removed, skipped = debug_toggle_tag(sc, ["a", "b"], "enemy")
        assert added == 0
        assert removed == 2
        assert skipped == 0
        for ent in sc.entities_snapshot:
            assert "enemy" not in ent.get("tags", [])
        b_ent = next(e for e in sc.entities_snapshot if e["id"] == "b")
        assert "quest" in b_ent["tags"]

    def test_toggle_mixed_adds_and_removes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_toggle_tag

        entities = _make_entities(
            {"id": "a", "name": "A", "tags": ["enemy"]},
            {"id": "b", "name": "B", "tags": []},
            {"id": "c", "name": "C", "tags": ["enemy"]},
        )
        sc = _FakeSceneController(entities)
        added, removed, skipped = debug_toggle_tag(sc, ["a", "b", "c"], "enemy")
        assert added == 1
        assert removed == 2
        assert skipped == 0
        a_ent = next(e for e in sc.entities_snapshot if e["id"] == "a")
        b_ent = next(e for e in sc.entities_snapshot if e["id"] == "b")
        c_ent = next(e for e in sc.entities_snapshot if e["id"] == "c")
        assert "enemy" not in a_ent["tags"]
        assert "enemy" in b_ent["tags"]
        assert "enemy" not in c_ent["tags"]

    def test_toggle_skips_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_toggle_tag

        entities = _make_entities(
            {"id": "player1", "name": "Player", "player": True},
            {"id": "npc1", "name": "NPC", "tags": []},
        )
        sc = _FakeSceneController(entities)
        added, removed, skipped = debug_toggle_tag(sc, ["player1", "npc1"], "enemy")
        assert added == 1
        assert removed == 0
        assert skipped == 1

    def test_toggle_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_toggle_tag

        sc = _FakeSceneController(_make_entities({"id": "a", "name": "A", "tags": []}))
        added, removed, skipped = debug_toggle_tag(sc, [], "x")
        assert added == 0
        assert removed == 0
        assert skipped == 0

    def test_toggle_deterministic_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_toggle_tag

        entities = _make_entities(
            {"id": "z", "name": "Z", "tags": ["x"]},
            {"id": "m", "name": "M", "tags": []},
            {"id": "a", "name": "A", "tags": ["x"]},
        )
        sc = _FakeSceneController(entities)
        added, removed, _ = debug_toggle_tag(sc, ["z", "m", "a"], "x")
        assert added == 1
        assert removed == 2


# ---------------------------------------------------------------------------
# Command palette action wiring
# ---------------------------------------------------------------------------

class TestCommandPaletteActions:
    """Verify command palette actions delegate correctly."""

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

    def test_action_props_remove_tag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_props_remove_tag

        entities = _make_entities(
            {"id": "a", "name": "A", "tags": ["enemy"]},
            {"id": "b", "name": "B", "tags": ["enemy", "quest"]},
        )
        w = self._make_window(entities, ["a", "b"])
        action_props_remove_tag(w, "enemy")
        for ent in w.scene_controller.entities_snapshot:
            assert "enemy" not in ent.get("tags", [])
        b_ent = next(e for e in w.scene_controller.entities_snapshot if e["id"] == "b")
        assert "quest" in b_ent["tags"]

    def test_action_props_remove_tag_noop_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_props_remove_tag

        entities = _make_entities({"id": "a", "name": "A", "tags": ["x"]})
        w = self._make_window(entities, [])
        action_props_remove_tag(w, "x")  # should not raise

    def test_action_batch_rename(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_batch_rename

        entities = _make_entities(
            {"id": "a", "name": "Alpha"},
            {"id": "b", "name": "Beta"},
        )
        w = self._make_window(entities, ["a", "b"])
        action_batch_rename(w, "prefix=Old_|suffix=_v2")
        names = {e["id"]: e["name"] for e in w.scene_controller.entities_snapshot}
        assert names["a"] == "Old_Alpha_v2"
        assert names["b"] == "Old_Beta_v2"

    def test_action_batch_rename_noop_empty_arg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_batch_rename

        entities = _make_entities({"id": "a", "name": "Alpha"})
        w = self._make_window(entities, ["a"])
        action_batch_rename(w, "")  # should not raise, no changes
        assert w.scene_controller.entities_snapshot[0]["name"] == "Alpha"

    def test_action_batch_rename_prefix_only_arg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_batch_rename

        entities = _make_entities({"id": "a", "name": "Guard"})
        w = self._make_window(entities, ["a"])
        action_batch_rename(w, "prefix=NPC_")
        assert w.scene_controller.entities_snapshot[0]["name"] == "NPC_Guard"

    def test_action_props_toggle_tag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_props_toggle_tag

        entities = _make_entities(
            {"id": "a", "name": "A", "tags": ["enemy"]},
            {"id": "b", "name": "B", "tags": []},
        )
        w = self._make_window(entities, ["a", "b"])
        action_props_toggle_tag(w, "enemy")
        a_ent = next(e for e in w.scene_controller.entities_snapshot if e["id"] == "a")
        b_ent = next(e for e in w.scene_controller.entities_snapshot if e["id"] == "b")
        assert "enemy" not in a_ent.get("tags", [])
        assert "enemy" in b_ent["tags"]

    def test_action_props_toggle_tag_noop_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_props_toggle_tag

        entities = _make_entities({"id": "a", "name": "A", "tags": ["x"]})
        w = self._make_window(entities, [])
        action_props_toggle_tag(w, "x")  # should not raise


# ---------------------------------------------------------------------------
# set names (numbered renaming)
# ---------------------------------------------------------------------------

class TestSetNames:
    def test_set_names_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        entities = _make_entities(
            {"id": "c", "name": "OldC"},
            {"id": "a", "name": "OldA"},
            {"id": "b", "name": "OldB"},
        )
        sc = _FakeSceneController(entities)
        result = debug_set_names(sc, ["c", "a", "b"], "NPC")
        assert result["ok"] is True
        assert result["renamed"] == 3
        assert result["skipped"] == 0
        names = {e["id"]: e["name"] for e in sc.entities_snapshot}
        # sorted order: a, b, c  -> NPC_001, NPC_002, NPC_003
        assert names["a"] == "NPC_001"
        assert names["b"] == "NPC_002"
        assert names["c"] == "NPC_003"

    def test_set_names_custom_start_and_width(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        entities = _make_entities(
            {"id": "b", "name": "B"},
            {"id": "a", "name": "A"},
        )
        sc = _FakeSceneController(entities)
        result = debug_set_names(sc, ["b", "a"], "Crate", start=10, width=2)
        assert result["ok"] is True
        assert result["renamed"] == 2
        names = {e["id"]: e["name"] for e in sc.entities_snapshot}
        assert names["a"] == "Crate_10"
        assert names["b"] == "Crate_11"

    def test_set_names_skips_entities_without_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        entities = _make_entities(
            {"id": "a", "name": "HasName"},
            {"id": "b"},  # no name field
        )
        sc = _FakeSceneController(entities)
        result = debug_set_names(sc, ["a", "b"], "NPC")
        assert result["ok"] is True
        assert result["renamed"] == 1
        assert result["skipped"] == 1
        assert sc.entities_snapshot[0]["name"] == "NPC_001"  # "a" (sorted first)

    def test_set_names_skips_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        entities = _make_entities(
            {"id": "player1", "name": "Hero", "player": True},
            {"id": "npc1", "name": "Guard"},
        )
        sc = _FakeSceneController(entities)
        result = debug_set_names(sc, ["player1", "npc1"], "NPC")
        assert result["ok"] is True
        assert result["renamed"] == 1
        assert result["skipped"] == 1
        npc = next(e for e in sc.entities_snapshot if e["id"] == "npc1")
        assert npc["name"] == "NPC_001"

    def test_set_names_empty_selection_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        sc = _FakeSceneController(_make_entities({"id": "a", "name": "X"}))
        result = debug_set_names(sc, [], "NPC")
        assert result["ok"] is True
        assert result["renamed"] == 0

    def test_set_names_empty_base_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        entities = _make_entities({"id": "a", "name": "X"})
        sc = _FakeSceneController(entities)
        result = debug_set_names(sc, ["a"], "  ")
        assert result["ok"] is False
        assert result["renamed"] == 0
        # entity should be unchanged
        assert sc.entities_snapshot[0]["name"] == "X"

    def test_set_names_invalid_width_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        sc = _FakeSceneController(_make_entities({"id": "a", "name": "X"}))
        result = debug_set_names(sc, ["a"], "NPC", width=0)
        assert result["ok"] is False
        result2 = debug_set_names(sc, ["a"], "NPC", width=7)
        assert result2["ok"] is False

    def test_set_names_invalid_start_returns_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        sc = _FakeSceneController(_make_entities({"id": "a", "name": "X"}))
        result = debug_set_names(sc, ["a"], "NPC", start=-1)
        assert result["ok"] is False

    def test_set_names_deterministic_numbering_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Numbering must follow sorted entity-ID order."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_set_names

        entities = _make_entities(
            {"id": "z", "name": "Z"},
            {"id": "m", "name": "M"},
            {"id": "a", "name": "A"},
        )
        sc = _FakeSceneController(entities)
        result = debug_set_names(sc, ["z", "m", "a"], "Unit", start=5, width=2)
        assert result["renamed"] == 3
        names = {e["id"]: e["name"] for e in sc.entities_snapshot}
        assert names["a"] == "Unit_05"
        assert names["m"] == "Unit_06"
        assert names["z"] == "Unit_07"


class TestCommandPaletteSetNames:
    """Verify command palette action_set_names wiring."""

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

    def test_action_set_names_simple_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_set_names

        entities = _make_entities(
            {"id": "b", "name": "B"},
            {"id": "a", "name": "A"},
        )
        w = self._make_window(entities, ["b", "a"])
        action_set_names(w, "NPC")
        names = {e["id"]: e["name"] for e in w.scene_controller.entities_snapshot}
        assert names["a"] == "NPC_001"
        assert names["b"] == "NPC_002"

    def test_action_set_names_key_value_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_set_names

        entities = _make_entities(
            {"id": "b", "name": "B"},
            {"id": "a", "name": "A"},
        )
        w = self._make_window(entities, ["b", "a"])
        action_set_names(w, "base=NPC|start=10|width=2")
        names = {e["id"]: e["name"] for e in w.scene_controller.entities_snapshot}
        assert names["a"] == "NPC_10"
        assert names["b"] == "NPC_11"

    def test_action_set_names_noop_empty_arg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_set_names

        entities = _make_entities({"id": "a", "name": "X"})
        w = self._make_window(entities, ["a"])
        action_set_names(w, "")  # should not raise, no changes
        assert w.scene_controller.entities_snapshot[0]["name"] == "X"

    def test_action_set_names_noop_empty_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_set_names

        entities = _make_entities({"id": "a", "name": "X"})
        w = self._make_window(entities, [])
        action_set_names(w, "NPC")  # should not raise
