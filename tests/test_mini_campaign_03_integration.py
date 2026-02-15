from __future__ import annotations

import json
from pathlib import Path

from tooling.campaign_replay import load_campaign_script_from_path, run_campaign_replay


HELP_SCRIPT_PATH = Path("replays/campaign03_help.json")
SILENT_SCRIPT_PATH = Path("replays/campaign03_silent.json")
EVENTS_PATH = Path("assets/data/events.json")
QUESTS_PATH = Path("assets/data/quests.json")
EP03_SCENE_PATH = Path("scenes/episode_03_ep03.json")
EP04_SCENE_PATH = Path("scenes/episode_04_ep04.json")


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


class TestMiniCampaign03Integration:
    def test_campaign03_help_script_contract(self) -> None:
        script = _load_json(HELP_SCRIPT_PATH)
        assert script["campaign_id"] == "mini_campaign_03"
        assert script["initial_flags"] == ["campaign03.active"]
        assert [entry["scene_id"] for entry in script["scenes"]] == ["ep01", "ep02", "ep03", "ep04"]

    def test_help_branch_emits_bonus_reward_event(self) -> None:
        result = _run_script(HELP_SCRIPT_PATH)
        final_flags = result.final_flags
        assert final_flags.get("campaign03.started") is True
        assert final_flags.get("campaign03.helped_mentor") is True
        assert final_flags.get("campaign03.ep04_complete") is True

        event_types = result.to_trace_dict()["event_types"]
        assert "ep04_reward_bonus_collected" in event_types
        assert "ep04_reward_collected" not in event_types

        quest_state = result.checkpoints["after_ep04"]["quest_state"]["quests"]["mini_campaign_03"]
        assert quest_state["state"] == "completed"
        assert quest_state["x_completed_stages"] == ["episode_01", "episode_02", "episode_03", "episode_04"]

    def test_silent_branch_emits_standard_reward_event(self) -> None:
        result = _run_script(SILENT_SCRIPT_PATH)
        final_flags = result.final_flags
        assert final_flags.get("campaign03.started") is True
        assert final_flags.get("campaign03.helped_mentor") is not True
        assert final_flags.get("campaign03.ep04_complete") is True

        event_types = result.to_trace_dict()["event_types"]
        assert "ep04_reward_collected" in event_types
        assert "ep04_reward_bonus_collected" not in event_types

    def test_save_restore_boundaries_and_scene_transitions(self) -> None:
        result = _run_script(HELP_SCRIPT_PATH)
        checkpoints = result.checkpoints
        assert {"after_ep01", "after_ep02", "after_ep03", "after_ep04"}.issubset(checkpoints.keys())

        quest_ep01 = checkpoints["after_ep01"]["quest_state"]["quests"]["mini_campaign_03"]
        quest_ep02 = checkpoints["after_ep02"]["quest_state"]["quests"]["mini_campaign_03"]
        quest_ep03 = checkpoints["after_ep03"]["quest_state"]["quests"]["mini_campaign_03"]

        assert quest_ep01["current_step"] == "episode_02"
        assert quest_ep02["current_step"] == "episode_03"
        assert quest_ep03["current_step"] == "episode_04"

        changes_ep01 = checkpoints["after_ep01"].get("scene_changes", [])
        changes_ep02 = checkpoints["after_ep02"].get("scene_changes", [])
        changes_ep03 = checkpoints["after_ep03"].get("scene_changes", [])

        assert any(item.get("scene") == "scenes/episode_02_ep02.json" for item in changes_ep01)
        assert any(item.get("scene") == "scenes/episode_03_ep03.json" for item in changes_ep02)
        assert any(item.get("scene") == "scenes/episode_04_ep04.json" for item in changes_ep03)

    def test_determinism_digest_and_event_sequences(self) -> None:
        first = _run_script(HELP_SCRIPT_PATH).to_trace_dict()
        second = _run_script(HELP_SCRIPT_PATH).to_trace_dict()
        assert first["digests"] == second["digests"]
        assert first["event_types"] == second["event_types"]
        assert first["final_flags"] == second["final_flags"]

    def test_campaign03_registration_and_scene_wiring(self) -> None:
        events = _load_json(EVENTS_PATH)
        names = {entry.get("name") for entry in events.get("events", []) if isinstance(entry, dict)}
        required_events = {
            "campaign03_started",
            "go_to_episode_04_ep04",
            "campaign03_complete",
            "campaign03.helped_mentor",
            "ep04_reward_bonus_collected",
        }
        assert required_events.issubset(names)

        quests = _load_json(QUESTS_PATH)
        quest_entry = None
        for entry in quests.get("quests", []):
            if isinstance(entry, dict) and entry.get("id") == "mini_campaign_03":
                quest_entry = entry
                break
        assert quest_entry is not None
        stages = quest_entry.get("stages", [])
        assert [stage.get("id") for stage in stages] == ["episode_01", "episode_02", "episode_03", "episode_04"]

        ep03_portal = _scene_entity(EP03_SCENE_PATH, "episode_03_exit_to_ep04")
        ep03_cfg = ep03_portal.get("behaviour_config", {}).get("SceneExit", {})
        assert ep03_cfg.get("listen_event") == "go_to_episode_04_ep04"
        assert ep03_cfg.get("target_scene") == "scenes/episode_04_ep04.json"

        ep04_ctrl = _scene_entity(EP04_SCENE_PATH, "episode_04_campaign03_done_ctrl")
        ep04_actions = ep04_ctrl.get("behaviour_config", {}).get("ActionListRunner", {}).get("actions", [])
        assert any(
            isinstance(action, dict)
            and action.get("type") == "emit_event"
            and action.get("event_type") == "campaign03_complete"
            for action in ep04_actions
        )
