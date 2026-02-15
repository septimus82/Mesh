from __future__ import annotations

import json
from pathlib import Path

import mesh_cli
from mesh_cli import replays as replays_module


def _write_suite(path: Path, *, golden: Path, budgets: dict | None = None) -> None:
    case: dict[str, object] = {
        "id": "ep01",
        "scene": "scenes/episode_01_intro.json",
        "script": "replays/ep01.json",
        "golden": str(golden),
    }
    if budgets is not None:
        case["budgets"] = budgets
    path.write_text(json.dumps([case], indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bootstrap_golden(suite: Path, out_dir: Path, *, reason: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    return mesh_cli.main(
        [
            "replays",
            "update-golden",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--reason",
            reason,
            "--quiet",
        ]
    )


def _fake_episode_handle_with_timings(total_ms: float):
    def _fake(args) -> int:
        case_out = Path(args.out_dir)
        case_out.mkdir(parents=True, exist_ok=True)
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
                    # Fixed replay_report timing; budget should read timings.json when present.
                    "total_ms": 1.0,
                    "tick_ms_count": 2,
                    "tick_ms_list": [0.5, 0.5],
                    "tick_ms_p50": 0.5,
                    "tick_ms_p95": 0.5,
                    "tick_ms_max": 0.5,
                },
            },
            "run_2": {"ok": True, "timing": {}},
        }
        timings_payload = {
            "schema_version": 1,
            "timing": {
                "total_ms": total_ms,
                "tick_ms_count": 2,
                "tick_ms_list": [total_ms / 2.0, total_ms / 2.0],
                "tick_ms_p50": total_ms / 2.0,
                "tick_ms_p95": total_ms / 2.0,
                "tick_ms_max": total_ms / 2.0,
            },
        }
        (case_out / "replay_report.json").write_text(
            json.dumps(replay_report, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (case_out / "replay_report.txt").write_text("ok\n", encoding="utf-8")
        (case_out / "timings.json").write_text(
            json.dumps(timings_payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (case_out / "events.ndjson").write_text('{"event_type":"ep01_entered","sequence":0}\n', encoding="utf-8")
        (case_out / "digests.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "digests": [{"digest": "aaa", "frame": 0}, {"digest": "bbb", "frame": 1}],
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (case_out / "final_state_bundle.json").write_text(
            json.dumps(
                {"schema_version": 1, "final_state": {"ok": True}, "snapshots": [{"s": 1}]},
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0

    return _fake


def _digest_triplet(actual: dict) -> tuple[str, str, str]:
    return (
        str(actual.get("expected_event_digest", "")),
        str(actual.get("expected_world_digest", "")),
        str(actual.get("expected_final_state_digest", "")),
    )


def _write_case_artifacts(case_out_dir: Path) -> None:
    case_out_dir.mkdir(parents=True, exist_ok=True)
    replay_report = {
        "ok": True,
        "seed_ignored": False,
        "determinism": {"digests_match": True, "events_match": True, "final_state_match": True},
        "run_1": {
            "ok": True,
            "timing": {
                "total_ms": 10.0,
                "tick_ms_count": 2,
                "tick_ms_list": [5.0, 5.0],
                "tick_ms_p50": 5.0,
                "tick_ms_p95": 5.0,
                "tick_ms_max": 5.0,
            },
        },
        "run_2": {"ok": True, "timing": {}},
    }
    (case_out_dir / "replay_report.json").write_text(
        json.dumps(replay_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (case_out_dir / "replay_report.txt").write_text("ok\n", encoding="utf-8")
    (case_out_dir / "timings.json").write_text(
        json.dumps({"schema_version": 1, "timing": replay_report["run_1"]["timing"]}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (case_out_dir / "events.ndjson").write_text(
        "\n".join(
            [
                json.dumps({"event_type": "ep01_entered", "payload": {"hp": 10}, "sequence": 0}, sort_keys=True),
                json.dumps({"event_type": "ep01_complete", "payload": {"hp": 10}, "sequence": 1}, sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (case_out_dir / "digests.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "digests": [{"frame": 0, "digest": "aaa"}, {"frame": 1, "digest": "bbb"}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (case_out_dir / "final_state_bundle.json").write_text(
        json.dumps(
            {"schema_version": 1, "final_state": {"flags": {"done": True}}, "snapshots": [{"s": 1}]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _make_case(case_out_dir: Path) -> replays_module.ReplaySuiteCase:
    return replays_module.ReplaySuiteCase(
        case_id="ep01",
        mode="episode",
        scene_rel="scenes/episode_01_intro.json",
        script_rel="replays/ep01.json",
        golden_rel="replays/golden/ep01_golden.json",
        scene_path=Path("scenes/episode_01_intro.json"),
        script_path=Path("replays/ep01.json"),
        golden_path=Path("replays/golden/ep01_golden.json"),
        budgets=None,
    )


def test_timings_flip_budget_not_digests(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    golden = tmp_path / "ep01_golden.json"
    out_dir = tmp_path / "out"
    _write_suite(
        suite,
        golden=golden,
        budgets={
            "max_total_ms": 50.0,
            "max_tick_ms_p95": 25.0,
            "max_tick_ms_max": 40.0,
        },
    )

    monkeypatch.setattr("mesh_cli.replays.episode_commands.handle", _fake_episode_handle_with_timings(10.0))
    assert _bootstrap_golden(suite, out_dir, reason="policy budget-vs-digest bootstrap") == 0

    rc_low = mesh_cli.main(
        ["replays", "run", "--suite", str(suite), "--out-dir", str(out_dir), "--seed", "123", "--quiet"]
    )
    assert rc_low == 0
    low_case = _read_json(out_dir / "suite_report.json")["cases"][0]
    low_triplet = _digest_triplet(low_case["actual"])
    assert low_case["budget"]["ok"] is True

    monkeypatch.setattr("mesh_cli.replays.episode_commands.handle", _fake_episode_handle_with_timings(120.0))
    rc_high = mesh_cli.main(
        ["replays", "run", "--suite", str(suite), "--out-dir", str(out_dir), "--seed", "123", "--quiet"]
    )
    assert rc_high == 1
    high_case = _read_json(out_dir / "suite_report.json")["cases"][0]
    high_triplet = _digest_triplet(high_case["actual"])

    assert high_case["match"] is True
    assert high_case["error"] == "budget exceeded"
    assert high_case["budget"]["ok"] is False
    assert low_triplet == high_triplet, (
        "artifact=timings.json changed but digest triplet changed: "
        f"event={low_triplet[0]}->{high_triplet[0]} "
        f"world={low_triplet[1]}->{high_triplet[1]} "
        f"final={low_triplet[2]}->{high_triplet[2]}"
    )

    observed_total = high_case["budget"]["observed"]["total_ms"]
    threshold_total = high_case["budget"]["limits"]["max_total_ms"]
    assert observed_total == 120.0, (
        "budget metric mismatch for timings artifact: "
        f"metric=total_ms observed={observed_total} threshold={threshold_total}"
    )
    assert observed_total > threshold_total, (
        "budget expected failure not triggered: "
        f"metric=total_ms observed={observed_total} threshold={threshold_total}"
    )


def test_report_only_fields_do_not_affect_digests(tmp_path: Path) -> None:
    case_out = tmp_path / "case"
    _write_case_artifacts(case_out)
    case = _make_case(case_out)

    base_actual = replays_module._collect_case_actual(case=case, case_out_dir=case_out)
    base_triplet = _digest_triplet(base_actual)

    replay_report_path = case_out / "replay_report.json"
    replay_report = _read_json(replay_report_path)
    replay_report["seed_ignored"] = True
    replay_report["host"] = "ci-worker"
    replay_report["environment"] = "ci"
    replay_report["provenance"] = {"platform": "linux", "python_version": "3.11"}
    replay_report["timing_debug"] = {"jitter_ms": 99.0}
    replay_report_path.write_text(json.dumps(replay_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    suite_report_base = {"schema_version": 1, "cases": [{"id": "ep01"}]}
    suite_report_with_meta = {
        **suite_report_base,
        "host": "ci-worker",
        "env": "ci",
        "provenance": {"tool_version": "0.4.0"},
        "timing_meta": {"total_ms": 10.0},
    }
    assert replays_module._sha256_payload(suite_report_base) != replays_module._sha256_payload(suite_report_with_meta)

    after_actual = replays_module._collect_case_actual(case=case, case_out_dir=case_out)
    after_triplet = _digest_triplet(after_actual)
    assert base_triplet == after_triplet, (
        "artifact=replay_report.json/suite_report metadata changed but digest triplet changed: "
        f"event={base_triplet[0]}->{after_triplet[0]} "
        f"world={base_triplet[1]}->{after_triplet[1]} "
        f"final={base_triplet[2]}->{after_triplet[2]}"
    )


def test_gameplay_change_affects_event_digest() -> None:
    events_base = [
        {"event_type": "ep01_entered", "payload": {"hp": 10}, "sequence": 0},
        {"event_type": "ep01_complete", "payload": {"hp": 10}, "sequence": 1},
    ]
    events_changed = [
        {"event_type": "ep01_entered", "payload": {"hp": 9}, "sequence": 0},
        {"event_type": "ep01_complete", "payload": {"hp": 10}, "sequence": 1},
    ]
    base_digest = replays_module._sha256_payload(
        replays_module._project_events_for_golden_digest(events_base)
    )
    changed_digest = replays_module._sha256_payload(
        replays_module._project_events_for_golden_digest(events_changed)
    )
    assert base_digest != changed_digest, (
        "artifact=events.ndjson gameplay mutation did not change expected_event_digest: "
        f"base={base_digest} changed={changed_digest}"
    )

