from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mesh_cli


def _write_suite(path: Path, *, scene_a: Path, scene_b: Path, script_a: Path, script_b: Path, golden_a: Path, golden_b: Path) -> None:
    payload = [
        {
            "id": "ep2",
            "scene": str(scene_b),
            "script": str(script_b),
            "golden": str(golden_b),
        },
        {
            "id": "ep1",
            "scene": str(scene_a),
            "script": str(script_a),
            "golden": str(golden_a),
        },
    ]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fake_episode_handle_factory(event_by_script_name: dict[str, str]):
    def _fake(args) -> int:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        script_name = Path(str(args.script)).name
        event_type = event_by_script_name.get(script_name, "event_default")

        replay_report = {
            "ok": True,
            "determinism": {
                "digests_match": True,
                "events_match": True,
                "final_state_match": True,
            },
            "run_1": {
                "ok": True,
                "timing": {
                    "total_ms": 10.0,
                    "tick_ms_count": 2,
                    "tick_ms_list": [1.0, 2.0],
                    "tick_ms_p50": 1.5,
                    "tick_ms_p95": 2.0,
                    "tick_ms_max": 2.0,
                },
            },
            "run_2": {"ok": True, "timing": {}},
        }
        (out_dir / "replay_report.json").write_text(json.dumps(replay_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (out_dir / "replay_report.txt").write_text("ok\n", encoding="utf-8")
        (out_dir / "events.ndjson").write_text(
            json.dumps({"event_type": event_type}, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (out_dir / "digests.json").write_text(
            json.dumps({"schema_version": 1, "digests": [{"digest": f"{event_type}_a"}, {"digest": f"{event_type}_b"}]}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (out_dir / "final_state_bundle.json").write_text(
            json.dumps({"schema_version": 1, "final_state": {"event_type": event_type}, "snapshots": [{"event_type": event_type}]}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return 0

    return _fake


def test_cli_replays_update_golden_updates_one_case_when_case_filter_provided(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene_a = tmp_path / "scene_a.json"
    scene_b = tmp_path / "scene_b.json"
    script_a = tmp_path / "script_a.json"
    script_b = tmp_path / "script_b.json"
    golden_a = tmp_path / "ep1_golden.json"
    golden_b = tmp_path / "ep2_golden.json"
    for path in (scene_a, scene_b, script_a, script_b):
        path.write_text("{}\n", encoding="utf-8")
    _write_suite(
        suite,
        scene_a=scene_a,
        scene_b=scene_b,
        script_a=script_a,
        script_b=script_b,
        golden_a=golden_a,
        golden_b=golden_b,
    )

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script_a.json": "ep1_evt", "script_b.json": "ep2_evt"}),
    )

    rc = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--case",
            "ep1",
            "--reason",
            "update golden for ep1 fixture",
            "--quiet",
        ]
    )
    assert rc == 0
    assert golden_a.exists()
    assert not golden_b.exists()
    report = _read_json(out_dir / "update_golden_report.json")
    assert report["summary"]["selected"] == 1
    assert report["cases"][0]["id"] == "ep1"
    assert (out_dir / "ep1" / "golden_diff.txt").exists()


def test_cli_replays_update_golden_updates_all_cases_and_reports_sorted_changed_cases(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene_a = tmp_path / "scene_a.json"
    scene_b = tmp_path / "scene_b.json"
    script_a = tmp_path / "script_a.json"
    script_b = tmp_path / "script_b.json"
    golden_a = tmp_path / "ep1_golden.json"
    golden_b = tmp_path / "ep2_golden.json"
    for path in (scene_a, scene_b, script_a, script_b):
        path.write_text("{}\n", encoding="utf-8")
    _write_suite(
        suite,
        scene_a=scene_a,
        scene_b=scene_b,
        script_a=script_a,
        script_b=script_b,
        golden_a=golden_a,
        golden_b=golden_b,
    )

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script_a.json": "same_ep1", "script_b.json": "before_ep2"}),
    )
    assert (
        mesh_cli.main(
            [
                "replays",
                "update-golden",
                "--suite",
                str(suite),
                "--out-dir",
                str(out_dir),
                "--reason",
                "bootstrap baseline",
                "--quiet",
            ]
        )
        == 0
    )

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script_a.json": "same_ep1", "script_b.json": "after_ep2"}),
    )
    rc = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--reason",
            "ep2 event shape changed intentionally",
            "--quiet",
        ]
    )
    assert rc == 0
    report = _read_json(out_dir / "update_golden_report.json")
    assert report["changed_cases"] == ["ep2"]
    assert report["unchanged_cases"] == ["ep1"]
    assert report["summary"]["changed"] == 1
    assert report["summary"]["unchanged"] == 1
    assert report["cases"][0]["golden_diff_payload"]["changed_fields"] == sorted(report["cases"][0]["golden_diff_payload"]["changed_fields"])
    assert report["cases"][1]["golden_diff_payload"]["changed_fields"] == sorted(report["cases"][1]["golden_diff_payload"]["changed_fields"])


def test_cli_replays_update_golden_refuses_missing_out_dir(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    scene = tmp_path / "scene.json"
    script = tmp_path / "script.json"
    golden = tmp_path / "golden.json"
    scene.write_text("{}\n", encoding="utf-8")
    script.write_text("{}\n", encoding="utf-8")
    suite.write_text(
        json.dumps(
            [
                {
                    "id": "ep1",
                    "scene": str(scene),
                    "script": str(script),
                    "golden": str(golden),
                }
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    rc = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(tmp_path / "does_not_exist"),
            "--quiet",
        ]
    )
    assert rc == 2


def test_cli_replays_update_golden_refuses_unknown_mode_without_allow_flag(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = tmp_path / "scene.json"
    script = tmp_path / "script.json"
    golden = tmp_path / "golden.json"
    scene.write_text("{}\n", encoding="utf-8")
    script.write_text("{}\n", encoding="utf-8")
    suite.write_text(
        json.dumps(
            [
                {
                    "id": "ep1",
                    "scene": str(scene),
                    "script": str(script),
                    "golden": str(golden),
                },
                {
                    "id": "legacy_case",
                    "mode": "legacy",
                    "scene": str(scene),
                    "script": str(script),
                    "golden": str(tmp_path / "legacy_golden.json"),
                },
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script.json": "evt"}),
    )

    rc_fail = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--quiet",
        ]
    )
    assert rc_fail == 2

    rc_ok = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--allow-unknown-mode",
            "--reason",
            "refresh known modes only",
            "--quiet",
        ]
    )
    assert rc_ok == 0
    report = _read_json(out_dir / "update_golden_report.json")
    assert report["summary"]["skipped_unknown_modes"] == 1
    assert report["skipped_unknown_modes"][0]["id"] == "legacy_case"


def test_cli_replays_update_golden_requires_reason_when_changes_detected(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = tmp_path / "scene.json"
    script = tmp_path / "script.json"
    golden = tmp_path / "golden.json"
    scene.write_text("{}\n", encoding="utf-8")
    script.write_text("{}\n", encoding="utf-8")
    suite.write_text(
        json.dumps(
            [
                {
                    "id": "ep1",
                    "scene": str(scene),
                    "script": str(script),
                    "golden": str(golden),
                }
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script.json": "evt_reason_required"}),
    )

    rc = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--quiet",
        ]
    )
    assert rc == 1
    assert not golden.exists()
    report = _read_json(out_dir / "update_golden_report.json")
    assert report["ok"] is False
    assert report["summary"]["changed"] == 1
    assert report["summary"]["updated"] == 0
    assert any("rerun with --reason" in entry for entry in report["policy_errors"])


def test_cli_replays_update_golden_allow_no_reason_bypasses_policy(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = tmp_path / "scene.json"
    script = tmp_path / "script.json"
    golden = tmp_path / "golden.json"
    scene.write_text("{}\n", encoding="utf-8")
    script.write_text("{}\n", encoding="utf-8")
    suite.write_text(
        json.dumps(
            [
                {
                    "id": "ep1",
                    "scene": str(scene),
                    "script": str(script),
                    "golden": str(golden),
                }
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script.json": "evt_allow_no_reason"}),
    )

    rc = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--allow-no-reason",
            "--quiet",
        ]
    )
    assert rc == 0
    assert golden.exists()
    report = _read_json(out_dir / "update_golden_report.json")
    assert report["allow_no_reason"] is True
    assert report["reason"] is None
    assert report["summary"]["changed"] == 1
    assert report["summary"]["updated"] == 1


def test_cli_replays_update_golden_max_changed_blocks_large_updates(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene_a = tmp_path / "scene_a.json"
    scene_b = tmp_path / "scene_b.json"
    script_a = tmp_path / "script_a.json"
    script_b = tmp_path / "script_b.json"
    golden_a = tmp_path / "ep1_golden.json"
    golden_b = tmp_path / "ep2_golden.json"
    for path in (scene_a, scene_b, script_a, script_b):
        path.write_text("{}\n", encoding="utf-8")
    _write_suite(
        suite,
        scene_a=scene_a,
        scene_b=scene_b,
        script_a=script_a,
        script_b=script_b,
        golden_a=golden_a,
        golden_b=golden_b,
    )
    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script_a.json": "evt_a", "script_b.json": "evt_b"}),
    )

    rc = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--reason",
            "bulk refresh",
            "--max-changed",
            "1",
            "--quiet",
        ]
    )
    assert rc == 1
    assert not golden_a.exists()
    assert not golden_b.exists()
    report = _read_json(out_dir / "update_golden_report.json")
    assert report["summary"]["changed"] == 2
    assert report["summary"]["updated"] == 0
    assert any("--max-changed=1" in entry for entry in report["policy_errors"])


def test_cli_replays_update_golden_dry_run_writes_report_only(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = tmp_path / "scene.json"
    script = tmp_path / "script.json"
    golden = tmp_path / "golden.json"
    scene.write_text("{}\n", encoding="utf-8")
    script.write_text("{}\n", encoding="utf-8")
    suite.write_text(
        json.dumps(
            [
                {
                    "id": "ep1",
                    "scene": str(scene),
                    "script": str(script),
                    "golden": str(golden),
                }
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script.json": "evt_before_dry_run"}),
    )
    rc_first = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--reason",
            "seed baseline",
            "--quiet",
        ]
    )
    assert rc_first == 0
    golden_before = golden.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory({"script.json": "evt_after_dry_run"}),
    )
    rc = mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--dry-run",
            "--quiet",
        ]
    )
    assert rc == 0
    assert golden.read_text(encoding="utf-8") == golden_before
    assert not (out_dir / "ep1" / "golden_diff.txt").exists()
    report = _read_json(out_dir / "update_golden_report.json")
    assert report["dry_run"] is True
    assert report["summary"]["changed"] == 1
    assert report["summary"]["updated"] == 0
