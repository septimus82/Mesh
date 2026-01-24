from __future__ import annotations

import json
from pathlib import Path


def _visible_entity_ids(scene_payload: dict, flags: set[str]) -> list[str]:
    ids: list[str] = []
    for ent in scene_payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        ent_id = ent.get("id")
        if not isinstance(ent_id, str) or not ent_id:
            continue
        if ent.get("tag") == "player":
            ids.append(ent_id)
            continue

        require_flags = ent.get("require_flags") or []
        forbid_flags = ent.get("forbid_flags") or []
        if not isinstance(require_flags, list) or not isinstance(forbid_flags, list):
            ids.append(ent_id)
            continue
        if any((isinstance(f, str) and f.strip() and f.strip() not in flags) for f in require_flags):
            continue
        if any((isinstance(f, str) and f.strip() and f.strip() in flags) for f in forbid_flags):
            continue
        ids.append(ent_id)
    return ids


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


def test_guard_patrol_chase_demo_objective_and_reward_gating() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "guard_patrol_chase_demo.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    objective_id = "guard_patrol_chase_demo_objectivelever_336_208_0_0"
    chest_id = "guard_patrol_chase_demo_rewardchest_112_176_0_0"
    claimed_id = "guard_patrol_chase_demo_rewardclaimed_144_176_0_0"

    objective = _find_entity(payload, objective_id)
    forbid = objective.get("forbid_flags")
    assert isinstance(forbid, list)
    assert "demo.guard_patrol_demo_complete" in forbid
    assert "complete_guard_patrol_demo" in _dialogue_choice_ids(objective)
    complete_hook = _find_sgs_hook(payload, payload_value="complete_guard_patrol_demo")
    cfg_root = complete_hook.get("behaviour_config")
    cfg = cfg_root.get("SetGameStateOnEvent") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("forbid_flags") == ["demo.guard_patrol_demo_complete"]
    assert cfg.get("set_flags") == {"demo.guard_patrol_demo_complete": True}

    chest = _find_entity(payload, chest_id)
    assert chest.get("require_flags") == ["demo.guard_patrol_demo_complete"]
    assert chest.get("forbid_flags") == ["demo.guard_patrol_demo_reward_claimed"]
    assert "open_guard_patrol_demo_chest" in _dialogue_choice_ids(chest)
    reward_hook = _find_sgs_hook(payload, payload_value="open_guard_patrol_demo_chest")
    cfg_root = reward_hook.get("behaviour_config")
    cfg = cfg_root.get("SetGameStateOnEvent") if isinstance(cfg_root, dict) else None
    assert isinstance(cfg, dict)
    assert cfg.get("once") is True
    assert cfg.get("require_flags") == ["demo.guard_patrol_demo_complete"]
    assert cfg.get("forbid_flags") == ["demo.guard_patrol_demo_reward_claimed"]
    assert cfg.get("set_flags") == {"demo.guard_patrol_demo_reward_claimed": True}

    claimed = _find_entity(payload, claimed_id)
    assert claimed.get("require_flags") == ["demo.guard_patrol_demo_reward_claimed"]

    ids_before = _visible_entity_ids(payload, set())
    assert objective_id in ids_before
    assert chest_id not in ids_before
    assert claimed_id not in ids_before

    ids_complete = _visible_entity_ids(payload, {"demo.guard_patrol_demo_complete"})
    assert objective_id not in ids_complete
    assert chest_id in ids_complete
    assert claimed_id not in ids_complete

    ids_claimed = _visible_entity_ids(
        payload,
        {"demo.guard_patrol_demo_complete", "demo.guard_patrol_demo_reward_claimed"},
    )
    assert objective_id not in ids_claimed
    assert chest_id not in ids_claimed
    assert claimed_id in ids_claimed
