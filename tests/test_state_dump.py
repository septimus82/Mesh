from __future__ import annotations

from types import SimpleNamespace

from engine.persistence_io import dumps_json_deterministic
from engine.tooling.state_dump import dump_state


def test_dump_state_is_deterministic_for_same_inputs(monkeypatch):
    monkeypatch.setenv("MESH_ACTIVE_PRESET", "act1_full_demo")

    window = SimpleNamespace()
    window.engine_config = SimpleNamespace(world_file="worlds/act1_prologue.json")
    window.world_controller = SimpleNamespace(id="act1_prologue")
    window.scene_controller = SimpleNamespace(current_scene_path="packs/core_regions/scenes/Act1_Prologue_Cabin.json")

    state = SimpleNamespace(
        counters={"gold": 7},
        flags={"zzz": True, "aaa": True, "bbb": False, "ccc": True},
        variables={"last_zone_id": "ZoneA"},
    )

    class _GS:
        def __init__(self):
            self.state = state

        def get_var(self, name, default=None):
            return state.variables.get(name, default)

    window.game_state_controller = _GS()

    # Provide a quest manager with mixed statuses.
    window.quest_manager = SimpleNamespace(
        list_active_quests=lambda: [
            {"id": "q_inactive", "status": "inactive"},
            {"id": "q_active", "status": "active"},
            {"id": "q_completed", "status": "completed"},
            {"id": "q_active2", "status": "active"},
        ]
    )

    first = dump_state(window)
    second = dump_state(window)

    assert first == second

    # Also lock deterministic serialization bytes.
    b1 = dumps_json_deterministic(first, indent=2, sort_keys=True, trailing_newline=True).encode("utf-8")
    b2 = dumps_json_deterministic(second, indent=2, sort_keys=True, trailing_newline=True).encode("utf-8")
    assert b1 == b2

    assert first["preset_id"] == "act1_full_demo"
    assert first["gold"] == 7
    assert first["flags_count"] == 3
    assert first["flags_sample"] == ["aaa", "ccc", "zzz"]
    assert first["last_zone_id"] == "ZoneA"
    assert first["active_quest_ids"] == ["q_active", "q_active2"]
