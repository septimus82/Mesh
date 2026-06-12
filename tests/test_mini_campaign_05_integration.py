from __future__ import annotations

import json
from pathlib import Path

from tooling.campaign_replay import load_campaign_script_from_path, run_campaign_replay

STANDARD_SCRIPT_PATH = Path("replays/campaign05_standard.json")
VARIANT_SCRIPT_PATH = Path("replays/campaign05_variant.json")
EVENTS_PATH = Path("assets/data/events.json")
QUESTS_PATH = Path("assets/data/quests.json")
EP05_SCENE_PATH = Path("scenes/episode_05_ep05.json")
EP06_SCENE_PATH = Path("scenes/episode_06_ep06.json")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run_script(path: Path):
    script = load_campaign_script_from_path(path)
    return run_campaign_replay(script)


def _scene_entity(scene_path: Path, entity_id: str) -> dict:
    payload = _load_json(scene_path)
    for entity in payload.get("entities", []):
        if isinstance(entity, dict) and entity.get("id") == entity_id:
            return entity
    raise AssertionError(f"Entity not found: {entity_id}")


class TestMiniCampaign05Integration:
    def test_campaign05_script_contracts(self) -> None:
        standard = _load_json(STANDARD_SCRIPT_PATH)
        variant = _load_json(VARIANT_SCRIPT_PATH)

        for payload in (standard, variant):
            assert payload["campaign_id"] == "mini_campaign_05"
            assert payload["initial_flags"] == ["campaign05.active", "campaign05.started"]
            assert [entry["scene_id"] for entry in payload["scenes"]] == ["ep01", "ep02", "ep03", "ep04", "ep05", "ep06"]
            assert any(
                step.get("action") == "save_restore_boundary"
                for scene in payload["scenes"]
                for step in scene.get("steps", [])
                if isinstance(step, dict)
            )

    def test_standard_path_emits_standard_reward_event(self) -> None:
        result = _run_script(STANDARD_SCRIPT_PATH)
        final_flags = result.final_flags
        assert final_flags.get("campaign05.active") is True
        assert final_flags.get("campaign05.ep06_complete") is True

        event_types = result.to_trace_dict()["event_types"]
        assert "ep06_reward_collected" in event_types
        assert "ep06_reward_bonus_collected" not in event_types

        quest_state = result.checkpoints["after_ep06"]["quest_state"]["quests"]["mini_campaign_05"]
        assert quest_state["state"] == "completed"
        assert quest_state["x_completed_stages"] == ["episode_01", "episode_02", "episode_03", "episode_04", "episode_05", "episode_06"]

    def test_variant_path_emits_bonus_reward_event(self) -> None:
        result = _run_script(VARIANT_SCRIPT_PATH)
        final_flags = result.final_flags
        assert final_flags.get("campaign05.active") is True
        assert final_flags.get("campaign05.ep06_complete") is True

        event_types = result.to_trace_dict()["event_types"]
        assert "ep06_reward_bonus_collected" in event_types
        assert "ep06_reward_collected" not in event_types

    def test_save_restore_boundaries_and_scene_transition_to_episode_06(self) -> None:
        result = _run_script(STANDARD_SCRIPT_PATH)
        checkpoints = result.checkpoints
        assert {"after_ep01", "after_ep02", "after_ep03", "after_ep04", "after_ep05", "after_ep06"}.issubset(checkpoints.keys())

        quest_ep05 = checkpoints["after_ep05"]["quest_state"]["quests"]["mini_campaign_05"]
        assert quest_ep05["current_step"] == "episode_06"

        changes_ep05 = checkpoints["after_ep05"].get("scene_changes", [])
        assert any(item.get("scene") == "scenes/episode_06_ep06.json" for item in changes_ep05)

    def test_determinism_digest_and_event_sequences(self) -> None:
        first = _run_script(VARIANT_SCRIPT_PATH).to_trace_dict()
        second = _run_script(VARIANT_SCRIPT_PATH).to_trace_dict()
        assert first["digests"] == second["digests"]
        assert first["event_types"] == second["event_types"]
        assert first["final_flags"] == second["final_flags"]

    def test_campaign05_registration_and_scene_wiring(self) -> None:
        events = _load_json(EVENTS_PATH)
        names = {entry.get("name") for entry in events.get("events", []) if isinstance(entry, dict)}
        required_events = {
            "campaign05_started",
            "go_to_episode_06_ep06",
            "campaign05_complete",
            "ep06_reward_collected",
            "ep06_reward_bonus_collected",
            "quest_ep06_complete",
        }
        assert required_events.issubset(names)

        quests = _load_json(QUESTS_PATH)
        quest_entry = None
        for entry in quests.get("quests", []):
            if isinstance(entry, dict) and entry.get("id") == "mini_campaign_05":
                quest_entry = entry
                break
        assert quest_entry is not None
        stages = quest_entry.get("stages", [])
        assert [stage.get("id") for stage in stages] == ["episode_01", "episode_02", "episode_03", "episode_04", "episode_05", "episode_06"]

        ep05_portal = _scene_entity(EP05_SCENE_PATH, "episode_05_exit_to_ep06")
        ep05_cfg = ep05_portal.get("behaviour_config", {}).get("SceneExit", {})
        assert ep05_cfg.get("listen_event") == "go_to_episode_06_ep06"
        assert ep05_cfg.get("target_scene") == "scenes/episode_06_ep06.json"

        ep06_done_ctrl = _scene_entity(EP06_SCENE_PATH, "episode_06_campaign05_done_ctrl")
        ep06_actions = ep06_done_ctrl.get("behaviour_config", {}).get("ActionListRunner", {}).get("actions", [])
        assert any(
            isinstance(action, dict)
            and action.get("type") == "set_flag"
            and action.get("flag") == "campaign05.ep06_complete"
            for action in ep06_actions
        )
