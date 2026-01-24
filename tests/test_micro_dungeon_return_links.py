from __future__ import annotations

import json
from pathlib import Path


def test_main_world_links_include_micro_dungeon_reverse_edges() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))
    links = payload["links"]
    assert isinstance(links, list)

    edges = {(str(link.get("from") or ""), str(link.get("to") or "")) for link in links if isinstance(link, dict)}
    for edge in (
        ("upper_hall", "side_room_01"),
        ("side_room_01", "upper_hall"),
        ("side_room_01", "reward_nook_01"),
        ("reward_nook_01", "side_room_01"),
    ):
        assert edge in edges


def test_return_door_macros_patch_existing_transition_ids(monkeypatch) -> None:
    from engine.tooling_runtime.macro_apply_report import compute_scene_macro_report

    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    side_payload = json.loads((repo_root / "scenes" / "side_room_01.json").read_text(encoding="utf-8"))
    assert isinstance(side_payload, dict)
    side_result = compute_scene_macro_report(
        scene_payload=side_payload,
        scene_path="scenes/side_room_01.json",
        macro_path="packs/core_regions/macros/door_back_to_upper_hall.json",
        raw_args=[],
        anchor_override="primary",
        cursor_world_pos=(184.0, 184.0),
        primary_entity_id="side_room_01_transition_upper_hall_184_184_0_0",
    )
    assert int(side_result.report["will_create"]) == 0
    assert int(side_result.report["will_update"]) == 1
    assert side_result.report["create_ids"] == []
    assert side_result.report["update_ids"] == ["side_room_01_transition_upper_hall_184_184_0_0"]

    reward_payload = json.loads((repo_root / "scenes" / "reward_nook_01.json").read_text(encoding="utf-8"))
    assert isinstance(reward_payload, dict)
    reward_result = compute_scene_macro_report(
        scene_payload=reward_payload,
        scene_path="scenes/reward_nook_01.json",
        macro_path="packs/core_regions/macros/door_back_to_side_room_01.json",
        raw_args=[],
        anchor_override="primary",
        cursor_world_pos=(184.0, 184.0),
        primary_entity_id="reward_nook_01_transition_side_room_01_184_184_0_0",
    )
    assert int(reward_result.report["will_create"]) == 0
    assert int(reward_result.report["will_update"]) == 1
    assert reward_result.report["create_ids"] == []
    assert reward_result.report["update_ids"] == ["reward_nook_01_transition_side_room_01_184_184_0_0"]
