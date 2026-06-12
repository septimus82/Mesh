from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from engine.behaviours.health import Health
from engine.game_state_controller import GameState
from tooling.campaign_replay import load_campaign_script_from_path, run_campaign_replay

SCRIPT_PATH = Path("replays/campaign02.json")
EVENTS_PATH = Path("assets/data/events.json")
QUESTS_PATH = Path("assets/data/quests.json")
EP01_SCENE_PATH = Path("scenes/episode_01_intro.json")
EP02_SCENE_PATH = Path("scenes/episode_02_ep02.json")
EP03_SCENE_PATH = Path("scenes/episode_03_ep03.json")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run_campaign02():
    script = load_campaign_script_from_path(SCRIPT_PATH)
    return run_campaign_replay(script)


def _scene_entity(scene_path: Path, entity_id: str) -> dict:
    payload = _load_json(scene_path)
    for entity in payload.get("entities", []):
        if isinstance(entity, dict) and entity.get("id") == entity_id:
            return entity
    raise AssertionError(f"Entity not found: {entity_id}")


class TestMiniCampaign02Integration:
    def test_campaign02_script_contract(self) -> None:
        script = _load_json(SCRIPT_PATH)
        assert script["campaign_id"] == "mini_campaign_02"
        assert [entry["scene_id"] for entry in script["scenes"]] == ["ep01", "ep02", "ep03"]
        assert any(
            step.get("action") == "save_restore_boundary"
            for entry in script["scenes"]
            for step in entry.get("steps", [])
            if isinstance(step, dict)
        )

    def test_happy_path_end_to_end_across_three_episodes(self) -> None:
        result = _run_campaign02()
        checkpoints = result.checkpoints
        assert {"after_ep01", "after_ep02", "after_ep03"}.issubset(checkpoints.keys())

        final_flags = result.final_flags
        assert final_flags.get("campaign02.started") is True
        assert final_flags.get("campaign02.ep01_complete") is True
        assert final_flags.get("campaign02.ep02_complete") is True
        assert final_flags.get("campaign02.ep03_complete") is True

        quest_state = checkpoints["after_ep03"]["quest_state"]["quests"]["mini_campaign_02"]
        assert quest_state["state"] == "completed"
        assert quest_state["x_completed_stages"] == ["episode_01", "episode_02", "episode_03"]

    def test_save_restore_boundary_after_episode_01(self) -> None:
        result = _run_campaign02()
        checkpoint = result.checkpoints["after_ep01"]
        quest_state = checkpoint["quest_state"]["quests"]["mini_campaign_02"]
        assert quest_state["current_step"] == "episode_02"
        scene_changes = checkpoint.get("scene_changes", [])
        assert any(item.get("scene") == "scenes/episode_02_ep02.json" for item in scene_changes)

    def test_save_restore_boundary_after_episode_02(self) -> None:
        result = _run_campaign02()
        checkpoint = result.checkpoints["after_ep02"]
        quest_state = checkpoint["quest_state"]["quests"]["mini_campaign_02"]
        assert quest_state["current_step"] == "episode_03"
        scene_changes = checkpoint.get("scene_changes", [])
        assert any(item.get("scene") == "scenes/episode_03_ep03.json" for item in scene_changes)

    def test_determinism_event_and_digest_sequences(self) -> None:
        first = _run_campaign02().to_trace_dict()
        second = _run_campaign02().to_trace_dict()
        assert first["digests"] == second["digests"]
        assert first["event_types"] == second["event_types"]
        assert first["final_flags"] == second["final_flags"]

    def test_episode_transient_flags_do_not_leak_as_true(self) -> None:
        result = _run_campaign02()
        true_flags = {flag for flag, value in result.final_flags.items() if value is True}

        expected_true = {
            "campaign02.started",
            "campaign02.ep01_complete",
            "campaign02.ep02_complete",
            "campaign02.ep03_complete",
            "ep01.complete",
            "ep02.complete",
            "ep03.complete",
        }
        assert true_flags == expected_true

    def test_player_hp_persistence_across_scene_transition(self) -> None:
        window = MagicMock()
        game_state_ctrl = MagicMock()
        game_state_ctrl.state = GameState()
        window.game_state_controller = game_state_ctrl

        entity = MagicMock()
        entity.mesh_id = "player"
        entity.mesh_name = "Player"
        entity.mesh_tag = "player"
        entity.mesh_tags = ["player"]
        entity.mesh_entity_data = {}

        health = Health(entity, window, max_hp=20.0, hp=20.0)
        health.apply_damage(7.0)
        saved = health.saveable_state()

        next_window = MagicMock()
        next_state_ctrl = MagicMock()
        next_state_ctrl.state = GameState()
        next_window.game_state_controller = next_state_ctrl

        next_entity = MagicMock()
        next_entity.mesh_id = "player"
        next_entity.mesh_name = "Player"
        next_entity.mesh_tag = "player"
        next_entity.mesh_tags = ["player"]
        next_entity.mesh_entity_data = {}

        next_health = Health(next_entity, next_window, max_hp=20.0, hp=20.0)
        next_health.restore_state(saved)
        assert next_health.hp == saved["hp"]

    def test_campaign02_events_and_quest_registered(self) -> None:
        events = _load_json(EVENTS_PATH)
        names = {entry.get("name") for entry in events.get("events", []) if isinstance(entry, dict)}
        required_events = {
            "campaign02_started",
            "go_to_episode_02_ep02",
            "go_to_episode_03_ep03",
            "campaign02_complete",
        }
        assert required_events.issubset(names)

        quests = _load_json(QUESTS_PATH)
        quest_entry = None
        for entry in quests.get("quests", []):
            if isinstance(entry, dict) and entry.get("id") == "mini_campaign_02":
                quest_entry = entry
                break
        assert quest_entry is not None
        stages = quest_entry.get("stages", [])
        assert [stage.get("id") for stage in stages] == ["episode_01", "episode_02", "episode_03"]

    def test_campaign_portal_wiring_across_episode_scenes(self) -> None:
        ep01_portal = _scene_entity(EP01_SCENE_PATH, "episode_01_exit_to_ep02")
        ep02_portal = _scene_entity(EP02_SCENE_PATH, "episode_02_exit_to_ep03")
        ep03_ctrl = _scene_entity(EP03_SCENE_PATH, "episode_03_campaign02_done_ctrl")

        ep01_cfg = ep01_portal.get("behaviour_config", {}).get("SceneExit", {})
        assert ep01_cfg.get("listen_event") == "go_to_episode_02_ep02"
        assert ep01_cfg.get("target_scene") == "scenes/episode_02_ep02.json"

        ep02_cfg = ep02_portal.get("behaviour_config", {}).get("SceneExit", {})
        assert ep02_cfg.get("listen_event") == "go_to_episode_03_ep03"
        assert ep02_cfg.get("target_scene") == "scenes/episode_03_ep03.json"

        ep03_actions = (
            ep03_ctrl.get("behaviour_config", {})
            .get("ActionListRunner", {})
            .get("actions", [])
        )
        assert any(
            isinstance(action, dict) and action.get("type") == "set_flag" and action.get("flag") == "campaign02.ep03_complete"
            for action in ep03_actions
        )
