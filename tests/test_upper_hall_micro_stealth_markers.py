from __future__ import annotations

import json
from pathlib import Path


def _find_by_name(payload: dict, name: str) -> dict:
    ent = next((e for e in payload.get("entities") or [] if isinstance(e, dict) and e.get("name") == name), None)
    assert isinstance(ent, dict)
    return ent


def _assert_requires_flag(ent: dict, flag: str) -> None:
    req = ent.get("require_flags")
    assert isinstance(req, list)
    assert flag in req


def test_upper_hall_has_micro_stealth_progress_markers() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "scenes" / "upper_hall.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    _assert_requires_flag(_find_by_name(payload, "GuardPatrolDemoComplete"), "demo.guard_patrol_demo_complete")
    _assert_requires_flag(_find_by_name(payload, "GuardPatrolDemoRewardClaimed"), "demo.guard_patrol_demo_reward_claimed")
    _assert_requires_flag(_find_by_name(payload, "GuardPatrolChaseDuoDemoComplete"), "demo.guard_patrol_chase_duo_demo_complete")
    _assert_requires_flag(
        _find_by_name(payload, "GuardPatrolChaseDuoDemoRewardClaimed"),
        "demo.guard_patrol_chase_duo_demo_reward_claimed",
    )
    _assert_requires_flag(_find_by_name(payload, "MicroStealthUltimateClaimed"), "demo.micro_stealth_ultimate_reward_claimed")

