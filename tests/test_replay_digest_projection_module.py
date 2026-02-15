from __future__ import annotations

from mesh_cli import replay_digest_projection as projection
from mesh_cli import replays as replays_module


def _find_excluded_key_paths(value: object, *, path: str = "") -> list[str]:
    leaked: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value.keys(), key=str):
            key_str = str(key)
            key_path = f"{path}.{key_str}" if path else key_str
            if key_str in projection.REPORT_ONLY_KEYS or key_str.startswith("timing"):
                leaked.append(key_path)
            leaked.extend(_find_excluded_key_paths(value[key], path=key_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            leaked.extend(_find_excluded_key_paths(item, path=f"{path}[{index}]"))
    return leaked


def test_projection_is_deterministic_and_excludes_report_only_keys() -> None:
    events = [
        {
            "sequence": 0,
            "event_type": "ep01_entered",
            "payload": {"ok": True},
            "seed_ignored": True,
            "timing_tick_ms": 2.3,
            "provenance": {"platform": "linux", "python_version": "3.11"},
        }
    ]
    world_digests = [
        {
            "tick": 0,
            "digest": "abc",
            "host": "runner-1",
            "environment": "ci",
            "timing_ms": 0.2,
        }
    ]
    final_state = {
        "schema_version": 1,
        "final_state": {"flags": {"done": True}},
        "snapshots": [],
        "generated_at": "2026-02-11T00:00:00Z",
        "tool_version": "0.4.0",
    }

    projected_events_a = projection.project_events_for_digest(events)
    projected_events_b = projection.project_events_for_digest(events)
    projected_world_a = projection.project_world_digests_for_digest(world_digests)
    projected_world_b = projection.project_world_digests_for_digest(world_digests)
    projected_final_a = projection.project_final_state_for_digest(final_state)
    projected_final_b = projection.project_final_state_for_digest(final_state)

    assert projected_events_a == projected_events_b
    assert projected_world_a == projected_world_b
    assert projected_final_a == projected_final_b

    leaked_events = _find_excluded_key_paths(projected_events_a)
    leaked_world = _find_excluded_key_paths(projected_world_a)
    leaked_final = _find_excluded_key_paths(projected_final_a)
    assert not leaked_events, f"events projection leaked excluded keys: {sorted(leaked_events)}"
    assert not leaked_world, f"world digest projection leaked excluded keys: {sorted(leaked_world)}"
    assert not leaked_final, f"final state projection leaked excluded keys: {sorted(leaked_final)}"


def test_projection_digest_changes_for_gameplay_relevant_mutation() -> None:
    events_a = [{"event_type": "ep01_entered", "payload": {"hp": 10}, "sequence": 0}]
    events_b = [{"event_type": "ep01_entered", "payload": {"hp": 9}, "sequence": 0}]

    digest_a = replays_module._sha256_payload(projection.project_events_for_digest(events_a))
    digest_b = replays_module._sha256_payload(projection.project_events_for_digest(events_b))

    assert digest_a != digest_b

