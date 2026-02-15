from __future__ import annotations

import json

from mesh_cli import replay_digest_projection as projection_module
from mesh_cli import replays as replays_module


_EXPECTED_DIGEST_PROJECTION_POLICY: dict[str, tuple[str, ...]] = {
    "report_only_keys": (
        "env",
        "environment",
        "generated_at",
        "host",
        "platform",
        "provenance",
        "python_version",
        "report_meta_probe",
        "seed_ignored",
        "timing",
        "tool_version",
    ),
    "report_only_key_prefixes": ("timing",),
}


def _normalize_policy(policy: dict[str, object]) -> dict[str, tuple[str, ...]]:
    keys_raw = policy.get("report_only_keys", ())
    prefixes_raw = policy.get("report_only_key_prefixes", ())
    keys = tuple(str(item) for item in keys_raw) if isinstance(keys_raw, (list, tuple)) else ()
    prefixes = tuple(str(item) for item in prefixes_raw) if isinstance(prefixes_raw, (list, tuple)) else ()
    return {
        "report_only_keys": keys,
        "report_only_key_prefixes": prefixes,
    }


def _format_policy(policy: dict[str, tuple[str, ...]]) -> str:
    return json.dumps(
        {
            "report_only_keys": list(policy["report_only_keys"]),
            "report_only_key_prefixes": list(policy["report_only_key_prefixes"]),
        },
        indent=2,
        sort_keys=True,
    )


def test_projection_keys_are_stable_ratchet() -> None:
    actual = _normalize_policy(replays_module.DIGEST_PROJECTION_POLICY)
    expected = _EXPECTED_DIGEST_PROJECTION_POLICY
    projection_actual = _normalize_policy(projection_module.DIGEST_PROJECTION_POLICY)
    assert projection_actual == actual, (
        "projection config changed: replays.py and replay_digest_projection.py diverged\n"
        f"replays:\n{_format_policy(actual)}\n"
        f"projection_module:\n{_format_policy(projection_actual)}"
    )
    assert actual == expected, (
        "projection config changed\n"
        f"expected:\n{_format_policy(expected)}\n"
        f"actual:\n{_format_policy(actual)}"
    )


def test_projection_rejects_new_report_only_key_without_update() -> None:
    synthetic_key = "report_meta_probe"
    events_base = [{"event_type": "ep01_entered", "payload": {"hp": 10}, "sequence": 0}]
    events_with_synthetic_report_key = [
        {
            "event_type": "ep01_entered",
            "payload": {"hp": 10},
            "sequence": 0,
            synthetic_key: {"source": "report-only"},
        }
    ]

    actual_policy = _normalize_policy(replays_module.DIGEST_PROJECTION_POLICY)
    report_only_keys = actual_policy["report_only_keys"]
    report_only_prefixes = actual_policy["report_only_key_prefixes"]
    is_ignored_by_policy = synthetic_key in report_only_keys or any(
        synthetic_key.startswith(prefix) for prefix in report_only_prefixes
    )
    assert is_ignored_by_policy, (
        "projection config changed: synthetic report-only key is not ignored\n"
        f"key={synthetic_key}\n"
        f"report_only_keys={list(report_only_keys)}\n"
        f"report_only_key_prefixes={list(report_only_prefixes)}\n"
        "Update DIGEST_PROJECTION_POLICY allowlist/exclusions intentionally."
    )

    base_digest = replays_module._sha256_payload(
        replays_module._project_events_for_golden_digest(events_base)
    )
    with_key_digest = replays_module._sha256_payload(
        replays_module._project_events_for_golden_digest(events_with_synthetic_report_key)
    )
    assert base_digest == with_key_digest, (
        "projection config changed: synthetic report-only key affected event digest\n"
        f"key={synthetic_key}\n"
        f"base_digest={base_digest}\n"
        f"with_key_digest={with_key_digest}\n"
        "Update DIGEST_PROJECTION_POLICY allowlist/exclusions intentionally."
    )
