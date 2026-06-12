from __future__ import annotations

import json

from engine.persistence_io import dumps_json_deterministic
from engine.tooling.replay_suite import run_replay_suite


def test_replay_suite_contract_ordering_and_schema(tmp_path):
    folder = tmp_path / "suite"
    folder.mkdir()

    (folder / "01_pass.json").write_text(
        json.dumps(
            {
                "steps": [
                    {"emit": "entered_zone", "zone_id": "ZoneOK"},
                ],
                "expect": {"last_zone_id": "ZoneOK"},
            }
        ),
        encoding="utf-8",
    )

    (folder / "02_fail.json").write_text(
        json.dumps(
            {
                "steps": [
                    {"emit": "entered_zone", "zone_id": "ZoneOK"},
                ],
                "expect": {"last_zone_id": "ZoneNOPE"},
            }
        ),
        encoding="utf-8",
    )

    summary1 = run_replay_suite(str(folder))
    summary2 = run_replay_suite(str(folder))
    assert summary1 == summary2

    assert summary1["total"] == 2
    assert summary1["passed"] == 1
    assert summary1["failed"] == 1

    results = summary1["results"]
    assert [r["script"] for r in results] == ["01_pass.json", "02_fail.json"]

    ok0 = results[0]
    assert ok0["ok"] is True
    assert ok0["error"] == ""
    assert isinstance(ok0["state"], dict)
    assert ok0["state"].get("last_zone_id") == "ZoneOK"

    bad = results[1]
    assert bad["ok"] is False
    assert bad["error"] == "last_zone_id mismatch: expected ZoneNOPE, got ZoneOK"
    assert isinstance(bad["state"], dict)
    assert bad["state"].get("last_zone_id") == "ZoneOK"

    # Stable JSON bytes using shared deterministic serializer.
    text1 = dumps_json_deterministic(summary1, indent=2, sort_keys=True)
    text2 = dumps_json_deterministic(summary2, indent=2, sort_keys=True)
    assert text1 == text2
    assert text1.endswith("\n")


def test_replay_suite_surfaces_expect_state_file_error_verbatim(tmp_path):
    folder = tmp_path / "suite"
    folder.mkdir()

    (folder / "01_missing_expect.json").write_text(
        json.dumps({"steps": [{"dump_state": True}], "expect_state_file": "missing.json"}),
        encoding="utf-8",
    )

    summary = run_replay_suite(str(folder))
    assert summary["total"] == 1
    assert summary["failed"] == 1

    missing_path = (folder / "missing.json").resolve()
    assert summary["results"][0]["error"] == f"expect_state_file not found: {missing_path}"


def test_replay_suite_ignores_suite_and_golden_metadata_files(tmp_path) -> None:
    folder = tmp_path / "suite"
    folder.mkdir()

    (folder / "suite.json").write_text("[]\n", encoding="utf-8")
    (folder / "ep01_golden.json").write_text("{}\n", encoding="utf-8")
    (folder / "01_pass.json").write_text(
        json.dumps({"steps": [{"emit": "entered_zone", "zone_id": "ZoneOK"}], "expect": {"last_zone_id": "ZoneOK"}}),
        encoding="utf-8",
    )

    summary = run_replay_suite(str(folder))
    assert summary["total"] == 1
    assert summary["failed"] == 0
    assert summary["results"][0]["script"] == "01_pass.json"


def test_replay_suite_ignores_campaign_chain_scripts(tmp_path) -> None:
    folder = tmp_path / "suite"
    folder.mkdir()

    (folder / "campaign02.json").write_text(
        json.dumps(
            {
                "campaign_id": "mini_campaign_02",
                "scenes": [{"scene_id": "ep01", "steps": [{"action": "drain"}]}],
            }
        ),
        encoding="utf-8",
    )
    (folder / "01_pass.json").write_text(
        json.dumps({"steps": [{"emit": "entered_zone", "zone_id": "ZoneOK"}], "expect": {"last_zone_id": "ZoneOK"}}),
        encoding="utf-8",
    )

    summary = run_replay_suite(str(folder))
    assert summary["total"] == 1
    assert summary["failed"] == 0
    assert summary["results"][0]["script"] == "01_pass.json"
