from __future__ import annotations

import json
from pathlib import Path


def _find_entity(payload: dict, entity_id: str) -> dict:
    ent = next((e for e in payload.get("entities") or [] if isinstance(e, dict) and e.get("id") == entity_id), None)
    assert isinstance(ent, dict)
    return ent


def _dialogue_choice_ids(ent: dict) -> set[str]:
    cfg_root = ent.get("behaviour_config")
    cfg = cfg_root.get("Dialogue") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    dialogue_root = cfg.get("dialogue")
    assert isinstance(dialogue_root, dict)
    nodes = dialogue_root.get("nodes")
    assert isinstance(nodes, dict)
    root = nodes.get("root")
    assert isinstance(root, dict)
    choices = root.get("choices")
    assert isinstance(choices, list)
    ids: set[str] = set()
    for c in choices:
        if isinstance(c, dict) and isinstance(c.get("id"), str):
            ids.add(c["id"])
    return ids


def _find_sgs_hook(payload: dict, *, payload_value: str) -> dict:
    for ent in payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        cfg_root = ent.get("behaviour_config")
        cfg = cfg_root.get("SetGameStateOnEvent") if isinstance(cfg_root, dict) else None
        if not isinstance(cfg, dict):
            continue
        if cfg.get("event_type") != "dialogue_choice":
            continue
        if cfg.get("payload_field") != "choice_id":
            continue
        if cfg.get("payload_value") != payload_value:
            continue
        return ent
    raise AssertionError(f"missing SetGameStateOnEvent hook for choice_id={payload_value!r}")


def test_micro_stealth_completion_room_has_ultimate_reward_gated_by_both_flags() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "micro_stealth_completion_room.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    chest_id = "micro_stealth_completion_room_ultimatechest_160_160_0_0"
    claimed_id = "micro_stealth_completion_room_ultimateclaimed_192_160_0_0"

    chest = _find_entity(payload, chest_id)
    assert chest.get("require_flags") == [
        "demo.guard_patrol_demo_reward_claimed",
        "demo.guard_patrol_chase_duo_demo_reward_claimed",
    ]
    forbid = chest.get("forbid_flags")
    assert isinstance(forbid, list)
    assert "demo.micro_stealth_ultimate_reward_claimed" in forbid
    assert "demo.guard_patrol_demo_spotted" in forbid
    assert "demo.guard_patrol_chase_duo_demo_spotted" in forbid
    assert "open_micro_stealth_ultimate_reward" in _dialogue_choice_ids(chest)

    hook = _find_sgs_hook(payload, payload_value="open_micro_stealth_ultimate_reward")
    cfg_root = hook.get("behaviour_config")
    cfg = cfg_root.get("SetGameStateOnEvent") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("require_flags") == [
        "demo.guard_patrol_demo_reward_claimed",
        "demo.guard_patrol_chase_duo_demo_reward_claimed",
    ]
    assert cfg.get("forbid_flags") == ["demo.micro_stealth_ultimate_reward_claimed"]
    assert cfg.get("set_flags") == {"demo.micro_stealth_ultimate_reward_claimed": True}

    claimed = _find_entity(payload, claimed_id)
    assert claimed.get("require_flags") == ["demo.micro_stealth_ultimate_reward_claimed"]
