from __future__ import annotations

from typing import Any

from mesh_cli import episode as episode_module
from mesh_cli import replay_digest_projection as projection_module
from mesh_cli import replays as replays_module


def _suite_style_digest_triplet(
    *,
    events: list[dict[str, Any]],
    world_digests: list[dict[str, Any]],
    final_state_payload: dict[str, Any],
) -> dict[str, str]:
    events_for_digest = [projection_module.project_event_for_digest(event) for event in events]
    world_for_digest = projection_module.project_world_digests_for_digest(world_digests)
    final_for_digest = projection_module.project_final_state_for_digest(final_state_payload)
    return {
        "expected_event_digest": replays_module._sha256_payload(events_for_digest),
        "expected_world_digest": replays_module._sha256_payload(world_for_digest),
        "expected_final_state_digest": replays_module._sha256_payload(final_for_digest),
    }


def test_episode_and_suite_digest_inputs_match_for_same_artifacts() -> None:
    events = [
        {
            "event_type": "ep01_entered",
            "payload": {"flag": True, "seed_ignored": True, "timing_ms": 1.25},
            "sequence": 0,
            "report_meta_probe": "ignored",
        },
        {
            "event_type": "ep01_complete",
            "payload": {"result": "ok"},
            "sequence": 1,
            "environment": "ci",
        },
    ]
    world_digests = [
        {"frame": 0, "digest": "aaa", "timing_ms": 0.5, "host": "runner"},
        {"frame": 1, "digest": "bbb", "platform": "linux"},
    ]
    final_state_payload = {
        "schema_version": 1,
        "final_state": {
            "flags": {"done": True},
            "provenance": {"host": "runner"},
        },
        "snapshots": [{"tick": 1, "python_version": "3.11"}],
        "seed_ignored": True,
    }

    episode_triplet = episode_module._compute_replay_artifact_digest_triplet(
        events=events,
        world_digests=world_digests,
        final_state_payload=final_state_payload,
    )
    suite_triplet = _suite_style_digest_triplet(
        events=events,
        world_digests=world_digests,
        final_state_payload=final_state_payload,
    )

    assert episode_triplet == suite_triplet


def test_projection_policy_is_imported_not_copied() -> None:
    assert episode_module._project_event_for_digest is projection_module.project_event_for_digest
    assert episode_module._project_world_digests_for_digest is projection_module.project_world_digests_for_digest
    assert episode_module._project_final_state_for_digest is projection_module.project_final_state_for_digest
