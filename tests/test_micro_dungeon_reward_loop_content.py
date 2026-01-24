from __future__ import annotations

import json
from pathlib import Path


def _find_entity(payload: dict, entity_id: str) -> dict:
    entities = payload.get("entities")
    assert isinstance(entities, list)
    ent = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
    assert isinstance(ent, dict)
    return ent


def _get_cfg(ent: dict, behaviour: str) -> dict:
    cfg_root = ent.get("behaviour_config")
    assert isinstance(cfg_root, dict)
    cfg = cfg_root.get(behaviour)
    assert isinstance(cfg, dict)
    return cfg


def _assert_dialogue_choice(ent: dict, *, choice_id: str, choice_text: str) -> None:
    cfg = _get_cfg(ent, "Dialogue")
    dialogue = cfg.get("dialogue")
    assert isinstance(dialogue, dict)
    nodes = dialogue.get("nodes")
    assert isinstance(nodes, dict)
    root = nodes.get("root")
    assert isinstance(root, dict)
    choices = root.get("choices")
    assert isinstance(choices, list)
    match = next((c for c in choices if isinstance(c, dict) and c.get("id") == choice_id), None)
    assert isinstance(match, dict)
    assert match.get("text") == choice_text


def test_side_room_key_has_dialogue_choice_and_hook() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "side_room_01.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    key_ent = _find_entity(payload, "side_room_01_sidekey_240_232_0_0")
    assert key_ent.get("prefab_id") == "slime_blob"
    _assert_dialogue_choice(key_ent, choice_id="take_side_key", choice_text="Take key")

    hook = _find_entity(payload, "side_room_01_choiceflag_demo_side_key_taken_take_side_key_0_0")
    cfg = _get_cfg(hook, "SetGameStateOnEvent")
    assert cfg.get("event_type") == "dialogue_choice"
    assert cfg.get("payload_field") == "choice_id"
    assert cfg.get("payload_value") == "take_side_key"
    assert cfg.get("once") is True
    assert cfg.get("forbid_flags") == ["demo.side_key_taken"]
    assert cfg.get("set_flags") == {"demo.side_key_taken": True}
    assert cfg.get("toast") == "You got a key"
    assert cfg.get("toast_seconds") == 3.0


def test_side_room_barrier_blocks_until_key_used_and_sets_flag() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "side_room_01.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    barrier = _find_entity(payload, "side_room_01_barrier_184_184_0_0")
    assert barrier.get("prefab_id") == "anvil_guard"
    assert barrier.get("forbid_flags") == ["demo.side_key_used"]
    _assert_dialogue_choice(barrier, choice_id="use_side_key", choice_text="Open door")

    locked = _find_entity(payload, "side_room_01_choicetoast_locked_use_side_key_0_0")
    lcfg = _get_cfg(locked, "SetGameStateOnEvent")
    assert lcfg.get("event_type") == "dialogue_choice"
    assert lcfg.get("payload_field") == "choice_id"
    assert lcfg.get("payload_value") == "use_side_key"
    assert lcfg.get("require_flags") == []
    assert lcfg.get("forbid_flags") == ["demo.side_key_taken"]
    assert lcfg.get("once") is False
    assert lcfg.get("toast") == "Locked"
    assert lcfg.get("toast_seconds") == 2.0

    unlock = _find_entity(payload, "side_room_01_choiceflag_demo_side_key_used_use_side_key_0_0")
    ucfg = _get_cfg(unlock, "SetGameStateOnEvent")
    assert ucfg.get("event_type") == "dialogue_choice"
    assert ucfg.get("payload_field") == "choice_id"
    assert ucfg.get("payload_value") == "use_side_key"
    assert ucfg.get("require_flags") == ["demo.side_key_taken"]
    assert ucfg.get("forbid_flags") == ["demo.side_key_used"]
    assert ucfg.get("once") is True
    assert ucfg.get("set_flags") == {"demo.side_key_used": True}


def test_reward_nook_chest_has_dialogue_choice_and_gated_hooks() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "reward_nook_01.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    chest = _find_entity(payload, "reward_nook_01_rewardchest_240_232_0_0")
    assert chest.get("prefab_id") == "magma_cube"
    _assert_dialogue_choice(chest, choice_id="open_reward_chest", choice_text="Open chest")

    locked = _find_entity(payload, "reward_nook_01_choicetoast_locked_open_reward_chest_0_0")
    lcfg = _get_cfg(locked, "SetGameStateOnEvent")
    assert lcfg.get("event_type") == "dialogue_choice"
    assert lcfg.get("payload_field") == "choice_id"
    assert lcfg.get("payload_value") == "open_reward_chest"
    assert lcfg.get("require_flags") == []
    assert lcfg.get("forbid_flags") == ["demo.side_key_taken"]
    assert lcfg.get("once") is False
    assert lcfg.get("toast") == "Locked"
    assert lcfg.get("toast_seconds") == 2.0

    reward = _find_entity(payload, "reward_nook_01_choiceflag_demo_reward_claimed_open_reward_chest_0_0")
    rcfg = _get_cfg(reward, "SetGameStateOnEvent")
    assert rcfg.get("event_type") == "dialogue_choice"
    assert rcfg.get("payload_field") == "choice_id"
    assert rcfg.get("payload_value") == "open_reward_chest"
    assert rcfg.get("require_flags") == ["demo.side_key_taken"]
    assert rcfg.get("forbid_flags") == ["demo.reward_claimed"]
    assert rcfg.get("once") is True
    assert rcfg.get("set_flags") == {"demo.reward_claimed": True}
    assert rcfg.get("toast") == "Reward claimed!"
    assert rcfg.get("toast_seconds") == 3.0
