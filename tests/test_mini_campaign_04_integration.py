from __future__ import annotations

import json
from pathlib import Path

from tooling.campaign_replay import load_campaign_script_from_path, run_campaign_replay


BONUS_SCRIPT_PATH = Path("replays/campaign04_bonus.json")
STANDARD_SCRIPT_PATH = Path("replays/campaign04_standard.json")
EVENTS_PATH = Path("assets/data/events.json")
QUESTS_PATH = Path("assets/data/quests.json")
EP01_SCENE_PATH = Path("scenes/episode_01_intro.json")
EP04_SCENE_PATH = Path("scenes/episode_04_ep04.json")
EP05_SCENE_PATH = Path("scenes/episode_05_ep05.json")


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


class TestMiniCampaign04Integration:
    def test_campaign04_script_contracts(self) -> None:
        bonus = _load_json(BONUS_SCRIPT_PATH)
        standard = _load_json(STANDARD_SCRIPT_PATH)

        for payload in (bonus, standard):
            assert payload["campaign_id"] == "mini_campaign_04"
            assert payload["initial_flags"] == ["campaign04.active", "campaign04.started"]
            assert [entry["scene_id"] for entry in payload["scenes"]] == ["ep01", "ep02", "ep03", "ep04", "ep05"]

        assert any(
            step.get("action") == "save_restore_boundary"
            for scene in bonus["scenes"]
            for step in scene.get("steps", [])
            if isinstance(step, dict)
        )

    def test_bonus_path_emits_bonus_reward_event(self) -> None:
        result = _run_script(BONUS_SCRIPT_PATH)
        final_flags = result.final_flags
        assert final_flags.get("campaign04.active") is True
        assert final_flags.get("campaign04.helped_mentor") is True
        assert final_flags.get("campaign04.ep05_complete") is True

        event_types = result.to_trace_dict()["event_types"]
        assert "ep05_reward_bonus_collected" in event_types
        assert "ep05_reward_collected" not in event_types

        quest_state = result.checkpoints["after_ep05"]["quest_state"]["quests"]["mini_campaign_04"]
        assert quest_state["state"] == "completed"
        assert quest_state["x_completed_stages"] == ["episode_01", "episode_02", "episode_03", "episode_04", "episode_05"]

    def test_standard_path_emits_standard_reward_event(self) -> None:
        result = _run_script(STANDARD_SCRIPT_PATH)
        final_flags = result.final_flags
        assert final_flags.get("campaign04.active") is True
        assert final_flags.get("campaign04.helped_mentor") is not True
        assert final_flags.get("campaign04.ep05_complete") is True

        event_types = result.to_trace_dict()["event_types"]
        assert "ep05_reward_collected" in event_types
        assert "ep05_reward_bonus_collected" not in event_types

    def test_save_restore_boundary_and_transition_to_episode_05(self) -> None:
        result = _run_script(BONUS_SCRIPT_PATH)
        checkpoints = result.checkpoints
        assert {"after_ep01", "after_ep02", "after_ep03", "after_ep04", "after_ep05"}.issubset(checkpoints.keys())

        quest_ep04 = checkpoints["after_ep04"]["quest_state"]["quests"]["mini_campaign_04"]
        assert quest_ep04["current_step"] == "episode_05"

        changes_ep04 = checkpoints["after_ep04"].get("scene_changes", [])
        assert any(item.get("scene") == "scenes/episode_05_ep05.json" for item in changes_ep04)

    def test_determinism_digest_and_event_sequences(self) -> None:
        first = _run_script(BONUS_SCRIPT_PATH).to_trace_dict()
        second = _run_script(BONUS_SCRIPT_PATH).to_trace_dict()
        assert first["digests"] == second["digests"]
        assert first["event_types"] == second["event_types"]
        assert first["final_flags"] == second["final_flags"]

    def test_campaign04_registration_and_scene_wiring(self) -> None:
        events = _load_json(EVENTS_PATH)
        names = {entry.get("name") for entry in events.get("events", []) if isinstance(entry, dict)}
        required_events = {
            "campaign04_started",
            "go_to_episode_05_ep05",
            "campaign04_complete",
            "ep05_reward_bonus_collected",
            "ep05_reward_collected",
        }
        assert required_events.issubset(names)

        quests = _load_json(QUESTS_PATH)
        quest_entry = None
        for entry in quests.get("quests", []):
            if isinstance(entry, dict) and entry.get("id") == "mini_campaign_04":
                quest_entry = entry
                break
        assert quest_entry is not None
        stages = quest_entry.get("stages", [])
        assert [stage.get("id") for stage in stages] == ["episode_01", "episode_02", "episode_03", "episode_04", "episode_05"]

        ep01_help_ctrl = _scene_entity(EP01_SCENE_PATH, "episode_01_campaign04_help_payoff_ctrl")
        ep01_help_cfg = ep01_help_ctrl.get("behaviour_config", {}).get("ActionListRunner", {})
        assert "campaign04.active" in ep01_help_cfg.get("require_flags", [])

        ep04_portal = _scene_entity(EP04_SCENE_PATH, "episode_04_exit_to_ep05")
        ep04_cfg = ep04_portal.get("behaviour_config", {}).get("SceneExit", {})
        assert ep04_cfg.get("listen_event") == "go_to_episode_05_ep05"
        assert ep04_cfg.get("target_scene") == "scenes/episode_05_ep05.json"

        ep05_done_ctrl = _scene_entity(EP05_SCENE_PATH, "episode_05_campaign04_done_ctrl")
        ep05_actions = ep05_done_ctrl.get("behaviour_config", {}).get("ActionListRunner", {}).get("actions", [])
        assert any(
            isinstance(action, dict)
            and action.get("type") == "set_flag"
            and action.get("flag") == "campaign04.ep05_complete"
            for action in ep05_actions
        )
