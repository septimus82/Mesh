"""Deterministic projection of replay artifacts into digest inputs.

The replay suite writes rich artifacts (timings, provenance, host metadata),
but golden digests should depend only on gameplay-relevant data. This module
provides pure projections used before hashing.
"""

from __future__ import annotations

from typing import Any


# Stable, reviewable projection policy used before hashing replay digest inputs.
# Keep this literal deterministically ordered; update ratchet tests when changed.
DIGEST_PROJECTION_POLICY: dict[str, tuple[str, ...]] = {
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


# Convenience constants for callers/tests.
REPORT_ONLY_KEYS: tuple[str, ...] = DIGEST_PROJECTION_POLICY["report_only_keys"]
REPORT_ONLY_KEY_PREFIXES: tuple[str, ...] = DIGEST_PROJECTION_POLICY["report_only_key_prefixes"]
_REPORT_ONLY_KEY_SET: frozenset[str] = frozenset(REPORT_ONLY_KEYS)


def _strip_report_only_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_report_only_keys(val)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in _REPORT_ONLY_KEY_SET
            and not any(str(key).startswith(prefix) for prefix in REPORT_ONLY_KEY_PREFIXES)
        }
    if isinstance(value, list):
        return [_strip_report_only_keys(item) for item in value]
    return value


def project_event_for_digest(obj: Any) -> Any:
    """Project a single event-like object into digest-relevant content."""
    return _strip_report_only_keys(obj)


def project_events_for_digest(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return gameplay-relevant projection of events payload."""
    return [project_event_for_digest(event) for event in events]


def project_world_digests_for_digest(obj: Any) -> Any:
    """Project world-digest payload into digest-relevant content."""
    if isinstance(obj, list):
        return [_strip_report_only_keys(entry) for entry in obj]
    return _strip_report_only_keys(obj)


def project_final_state_for_digest(obj: Any) -> Any:
    """Project final-state payload into digest-relevant content."""
    projected = _strip_report_only_keys(obj)
    if isinstance(obj, dict) and not isinstance(projected, dict):
        return {}
    return projected
