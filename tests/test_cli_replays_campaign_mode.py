from __future__ import annotations

import json
from pathlib import Path

import mesh_cli


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cli_replays_run_supports_campaign_mode_case(tmp_path: Path) -> None:
    suite_path = tmp_path / "suite_campaign.json"
    golden_path = tmp_path / "campaign02_golden.json"
    out_dir = tmp_path / "out"

    suite_payload = [
        {
            "id": "campaign02",
            "mode": "campaign",
            "scene": "scenes/episode_01_intro.json",
            "script": "replays/campaign02.json",
            "golden": str(golden_path),
            "budgets": {
                "max_total_ms": 5000.0,
                "max_tick_ms_p95": 50.0,
                "max_tick_ms_max": 200.0,
            },
        }
    ]
    suite_path.write_text(json.dumps(suite_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    rc_update = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite_path),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--reason",
            "bootstrap campaign fixture",
            "--quiet",
        ]
    )
    assert rc_update == 0
    assert golden_path.exists()

    rc_compare = mesh_cli.main(
        [
            "replays",
            "run",
            "--suite",
            str(suite_path),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    assert rc_compare == 0

    report = _read_json(out_dir / "suite_report.json")
    case = report["cases"][0]
    assert case["mode"] == "campaign"
    assert case["ok"] is True
    assert case["run_ok"] is True
    assert case["match"] is True
    assert case["seed_ignored"] is True

    replay_report = _read_json(out_dir / "campaign02" / "replay_report.json")
    assert replay_report["seed_ignored"] is True
