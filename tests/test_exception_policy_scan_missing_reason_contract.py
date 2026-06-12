from __future__ import annotations

from pathlib import Path

import pytest

from tooling import scan_exception_policies

pytestmark = [pytest.mark.fast]


def _parse_site(site: str) -> tuple[str, int]:
    path, _, line = site.rpartition(":")
    return path, int(line)


def test_missing_ble001_reason_summary_is_deterministic() -> None:
    sites = [
        ("mesh_cli/release.py", 607),
        ("engine/foo.py", 12),
        ("engine/foo.py", 2),
        ("engine/bar.py", 9),
    ]

    summary = scan_exception_policies._build_missing_ble001_reason_summary(sites, limit=3)
    reversed_summary = scan_exception_policies._build_missing_ble001_reason_summary(list(reversed(sites)), limit=3)

    assert list(summary.keys()) == [
        "missing_ble001_reason_total",
        "missing_ble001_reason_sites_first",
        "missing_ble001_reason_sites_limit",
    ]
    assert summary == reversed_summary
    assert summary == {
        "missing_ble001_reason_total": 4,
        "missing_ble001_reason_sites_first": [
            "engine/bar.py:9",
            "engine/foo.py:2",
            "engine/foo.py:12",
        ],
        "missing_ble001_reason_sites_limit": 3,
    }


def test_missing_ble001_reason_log_uses_deterministic_summary_fields() -> None:
    payload = {
        "ble001_missing_reason_count": 999,
        "missing_ble001_reason_total": 7,
        "missing_ble001_reason_sites_first": [
            "mesh_cli/release.py:530",
            "engine/assets.py:29",
            "engine/animation.py:85",
            "engine/animation.py:121",
            "engine/animation.py:400",
            "engine/assets_reload.py:92",
        ],
    }

    message = scan_exception_policies._format_missing_ble001_reason_log(payload, limit=5)

    assert message == (
        "[exception-policy-scan] "
        "missing_ble001_reason_total=7 "
        "missing_ble001_reason_sites_first[5]="
        "mesh_cli/release.py:530, engine/assets.py:29, engine/animation.py:85, "
        "engine/animation.py:121, engine/animation.py:400"
    )


def test_missing_ble001_reason_scan_ratchet() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    payload = scan_exception_policies.scan(["engine", "mesh_cli", "tooling"], repo_root=repo_root)

    assert payload["missing_ble001_reason_total"] == payload["ble001_missing_reason_count"]
    assert payload["missing_ble001_reason_total"] <= 0
    assert payload["missing_ble001_reason_sites_limit"] == 25
    sites = payload["missing_ble001_reason_sites_first"]
    assert len(sites) <= 25
    assert [_parse_site(site) for site in sites] == sorted(_parse_site(site) for site in sites)
