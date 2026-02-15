"""Fast-tier tests for Selection: Group… / Ungroup editor authoring actions.

Validates:
- grouping creates a group entity at centroid with is_group/tags
- deterministic member ordering and stable group name numbering
- membership links (group_id) set correctly
- ungroup deletes group entity and removes links
- edge cases: <2 members, player skipped, already-grouped refuses
- command palette parsing: group simple + kv, ungroup
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
        for key in ("name", "x", "y", "width", "height", "rotation", "group_id", "is_group"):
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

    def debug_group_selection(
        self,
        entity_ids: list[str],
        name_base: str = "Group",
        about: str = "group",
        primary_id: str = "",
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_group_selection(
            self, entity_ids, name_base=name_base, about=about,
            primary_id=primary_id,
        )

    def debug_ungroup_selection(
        self,
        entity_ids: list[str],
        mode: str = "auto",
    ) -> dict[str, Any]:
        import engine.scene_runtime.authoring.entity_ops as _ops
        return _ops.debug_ungroup_selection(self, entity_ids, mode=mode)

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


def _group_entities(sc: _FakeSceneController) -> list[dict[str, Any]]:
    return [e for e in sc.entities_snapshot if e.get("is_group") is True]


# ---------------------------------------------------------------------------
# Group: basic
# ---------------------------------------------------------------------------

class TestGroupBasic:
    def test_group_two_entities_at_centroid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 200.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b"])
        assert result["ok"] is True
        assert result["linked"] == 2
        assert result["members"] == ["a", "b"]  # sorted
        assert result["group_name"].startswith("Group_")

        # Group entity was created at centroid.
        groups = _group_entities(sc)
        assert len(groups) == 1
        g = groups[0]
        assert g["is_group"] is True
        assert "group" in g["tags"]
        assert g["x"] == pytest.approx(50.0)
        assert g["y"] == pytest.approx(100.0)
        assert g["id"] == result["group_id"]
        assert g["name"] == result["group_name"]

        # Members have group_id set.
        for eid in ["a", "b"]:
            ent = _ent_by_id(sc, eid)
            assert ent is not None
            assert ent["group_id"] == result["group_id"]

    def test_group_three_entities_sorted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "c", "x": 30.0, "y": 0.0},
            {"id": "a", "x": 10.0, "y": 0.0},
            {"id": "b", "x": 20.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["c", "a", "b"])
        assert result["ok"] is True
        assert result["members"] == ["a", "b", "c"]  # deterministic sort
        assert result["linked"] == 3

    def test_custom_name_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b"], name_base="Trees")
        assert result["ok"] is True
        assert result["group_name"].startswith("Trees_")


# ---------------------------------------------------------------------------
# Group: name numbering
# ---------------------------------------------------------------------------

class TestGroupNaming:
    def test_name_increments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        # Pre-existing Group_001.
        entities = _make_entities(
            {"id": "existing_group", "x": 0.0, "y": 0.0, "name": "Group_001", "is_group": True, "tags": ["group"]},
            {"id": "a", "x": 10.0, "y": 0.0},
            {"id": "b", "x": 20.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b"])
        assert result["ok"] is True
        assert result["group_name"] == "Group_002"

    def test_id_increments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        # Pre-existing group_1.
        entities = _make_entities(
            {"id": "group_1", "x": 0.0, "y": 0.0, "is_group": True, "tags": ["group"], "name": "Group_001"},
            {"id": "a", "x": 10.0, "y": 0.0},
            {"id": "b", "x": 20.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b"])
        assert result["ok"] is True
        assert result["group_id"] == "group_2"


# ---------------------------------------------------------------------------
# Group: about=primary pivot
# ---------------------------------------------------------------------------

class TestGroupAboutPrimary:
    def test_primary_pivot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 200.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(
            sc, ["a", "b"], about="primary", primary_id="a",
        )
        assert result["ok"] is True
        g = _group_entities(sc)
        assert len(g) == 1
        assert g[0]["x"] == pytest.approx(0.0)
        assert g[0]["y"] == pytest.approx(0.0)

    def test_primary_missing_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(
            sc, ["a", "b"], about="primary", primary_id="",
        )
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Group: edge cases
# ---------------------------------------------------------------------------

class TestGroupEdgeCases:
    def test_fewer_than_two_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a"])
        assert result["ok"] is False

    def test_empty_selection_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        sc = _FakeSceneController([])
        result = debug_group_selection(sc, [])
        assert result["ok"] is False

    def test_skip_player(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "player": True},
            {"id": "b", "x": 10.0, "y": 0.0},
            {"id": "c", "x": 20.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b", "c"])
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["linked"] == 2
        assert "a" not in result["members"]

    def test_skip_no_position(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a"},  # no x/y
            {"id": "b", "x": 10.0, "y": 0.0},
            {"id": "c", "x": 20.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b", "c"])
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["linked"] == 2

    def test_already_grouped_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "group_id": "group_1"},
            {"id": "b", "x": 10.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b"])
        assert result["ok"] is False

    def test_invalid_about(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 10.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["a", "b"], about="invalid")
        assert result["ok"] is False

    def test_group_entities_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Trying to include a group entity itself as a member is skipped."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection

        entities = _make_entities(
            {"id": "g", "x": 0.0, "y": 0.0, "is_group": True, "tags": ["group"]},
            {"id": "a", "x": 10.0, "y": 0.0},
            {"id": "b", "x": 20.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        result = debug_group_selection(sc, ["g", "a", "b"])
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert "g" not in result["members"]


# ---------------------------------------------------------------------------
# Ungroup: selecting the group entity
# ---------------------------------------------------------------------------

class TestUngroupByGroupEntity:
    def test_ungroup_by_selecting_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection, debug_ungroup_selection

        # First create a group.
        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        group_result = debug_group_selection(sc, ["a", "b"])
        gid = group_result["group_id"]

        # Ungroup by selecting the group entity.
        result = debug_ungroup_selection(sc, [gid])
        assert result["ok"] is True
        assert result["group_id"] == gid
        assert result["unlinked"] == 2
        assert result["deleted_group"] is True

        # Group entity removed.
        assert _ent_by_id(sc, gid) is None
        # Members unlinked.
        for eid in ["a", "b"]:
            ent = _ent_by_id(sc, eid)
            assert ent is not None
            assert "group_id" not in ent


# ---------------------------------------------------------------------------
# Ungroup: selecting members
# ---------------------------------------------------------------------------

class TestUngroupByMembers:
    def test_ungroup_by_member_selection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection, debug_ungroup_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        sc = _FakeSceneController(entities)
        group_result = debug_group_selection(sc, ["a", "b"])
        gid = group_result["group_id"]

        # Ungroup by selecting a member.
        result = debug_ungroup_selection(sc, ["a"])
        assert result["ok"] is True
        assert result["group_id"] == gid
        assert result["unlinked"] == 2  # both members unlinked
        assert result["deleted_group"] is True

    def test_ungroup_picks_lowest_group_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When members belong to different groups, lowest group_id wins."""
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_ungroup_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "group_id": "group_2"},
            {"id": "b", "x": 10.0, "y": 0.0, "group_id": "group_1"},
            {"id": "group_1", "x": 5.0, "y": 0.0, "is_group": True, "tags": ["group"], "name": "Group_001"},
            {"id": "group_2", "x": 5.0, "y": 0.0, "is_group": True, "tags": ["group"], "name": "Group_002"},
        )
        sc = _FakeSceneController(entities)
        result = debug_ungroup_selection(sc, ["a", "b"])
        assert result["ok"] is True
        assert result["group_id"] == "group_1"  # lowest lex


# ---------------------------------------------------------------------------
# Ungroup: edge cases
# ---------------------------------------------------------------------------

class TestUngroupEdgeCases:
    def test_empty_selection_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_ungroup_selection

        sc = _FakeSceneController([])
        result = debug_ungroup_selection(sc, [])
        assert result["ok"] is False

    def test_no_group_found_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_ungroup_selection

        entities = _make_entities({"id": "a", "x": 0.0, "y": 0.0})
        sc = _FakeSceneController(entities)
        result = debug_ungroup_selection(sc, ["a"])
        assert result["ok"] is False

    def test_player_skipped_in_ungroup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_ungroup_selection

        entities = _make_entities(
            {"id": "player", "x": 0.0, "y": 0.0, "player": True},
            {"id": "a", "x": 10.0, "y": 0.0, "group_id": "group_1"},
            {"id": "group_1", "x": 5.0, "y": 0.0, "is_group": True, "tags": ["group"], "name": "Group_001"},
        )
        sc = _FakeSceneController(entities)
        result = debug_ungroup_selection(sc, ["player", "a"])
        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["unlinked"] == 1


# ---------------------------------------------------------------------------
# Round-trip: group then ungroup restores clean state
# ---------------------------------------------------------------------------

class TestGroupUngroupRoundTrip:
    def test_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_authoring(monkeypatch)
        from engine.scene_runtime.authoring.entity_ops import debug_group_selection, debug_ungroup_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 200.0},
        )
        sc = _FakeSceneController(entities)

        grp = debug_group_selection(sc, ["a", "b"])
        assert grp["ok"] is True
        assert len(sc.entities_snapshot) == 3  # original 2 + group

        ung = debug_ungroup_selection(sc, [grp["group_id"]])
        assert ung["ok"] is True
        assert len(sc.entities_snapshot) == 2  # back to original 2
        for ent in sc.entities_snapshot:
            assert "group_id" not in ent


# ---------------------------------------------------------------------------
# Command palette action wiring
# ---------------------------------------------------------------------------

class TestGroupCommandPaletteAction:
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

    def test_group_simple(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        w = self._make_world(entities)
        action_group_selection(w, "MyGroup")
        captured = capsys.readouterr().out
        assert "action=group_selection" in captured
        assert "linked=2" in captured

    def test_group_kv_about_primary(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_group_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 100.0, "y": 0.0},
        )
        w = self._make_world(entities)
        action_group_selection(w, "base=Trees|about=primary")
        captured = capsys.readouterr().out
        assert "action=group_selection" in captured
        assert "about=primary" in captured

    def test_group_no_selection_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_group_selection

        w = SimpleNamespace(
            entity_select_state=SimpleNamespace(selected_ids=[], primary_id=""),
        )
        action_group_selection(w, "Group")
        captured = capsys.readouterr().out
        assert "noop" in captured
        assert "no_selection" in captured


class TestUngroupCommandPaletteAction:
    def _make_world(self, entities: list[dict[str, Any]]) -> SimpleNamespace:
        sc = _FakeSceneController(entities)
        all_ids = [e["id"] for e in entities if "player" not in (e.get("tags") or [])]

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
            selected_ids=all_ids,
            primary_id=all_ids[0] if all_ids else "",
        )
        return w

    def test_ungroup_command(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_ungroup_selection

        entities = _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "group_id": "group_1"},
            {"id": "b", "x": 10.0, "y": 0.0, "group_id": "group_1"},
            {"id": "group_1", "x": 5.0, "y": 0.0, "is_group": True, "tags": ["group"], "name": "Group_001"},
        )
        w = self._make_world(entities)
        action_ungroup_selection(w, "")
        captured = capsys.readouterr().out
        assert "action=ungroup_selection" in captured
        assert "unlinked=2" in captured

    def test_ungroup_no_selection_noop(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        _patch_authoring(monkeypatch)
        from engine.command_palette_registry import action_ungroup_selection

        w = SimpleNamespace(
            entity_select_state=SimpleNamespace(selected_ids=[], primary_id=""),
        )
        action_ungroup_selection(w, "")
        captured = capsys.readouterr().out
        assert "noop" in captured
        assert "no_selection" in captured
