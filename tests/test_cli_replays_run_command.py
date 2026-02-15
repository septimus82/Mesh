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
    payload = [
        case
    ]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bootstrap_golden(suite: Path, out_dir: Path, *, reason: str = "test baseline") -> int:
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


def _fake_episode_handle_factory(
    *,
    total_ms: float,
    tick_ms_p95: float,
    tick_ms_max: float,
    tick_ms_list: list[float],
) -> object:
    def _fake_episode_handle(args) -> int:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
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
                    "total_ms": total_ms,
                    "tick_ms_count": len(tick_ms_list),
                    "tick_ms_list": list(tick_ms_list),
                    "tick_ms_p50": tick_ms_list[len(tick_ms_list) // 2],
                    "tick_ms_p95": tick_ms_p95,
                    "tick_ms_max": tick_ms_max,
                },
            },
            "run_2": {"ok": True, "timing": {}},
        }
        (out_dir / "replay_report.json").write_text(json.dumps(replay_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (out_dir / "replay_report.txt").write_text("ok\n", encoding="utf-8")
        (out_dir / "events.ndjson").write_text('{"event_type":"ep01_entered"}\n', encoding="utf-8")
        (out_dir / "digests.json").write_text(
            json.dumps({"schema_version": 1, "digests": [{"digest": "aaa"}, {"digest": "bbb"}]}, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (out_dir / "final_state_bundle.json").write_text(
            json.dumps({"schema_version": 1, "final_state": {"ok": True}, "snapshots": [{"s": 1}]}, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0

    return _fake_episode_handle


def test_cli_replays_run_suite_writes_artifacts_and_passes_against_golden(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    golden = tmp_path / "ep01_golden.json"
    out_dir = tmp_path / "out"
    _write_suite(suite, golden=golden)

    rc_update = _bootstrap_golden(suite, out_dir, reason="bootstrap ep01 golden")
    assert rc_update == 0
    assert golden.exists()

    case_dir = out_dir / "ep01"
    assert (case_dir / "replay_report.json").exists()
    assert (case_dir / "events.ndjson").exists()
    assert (case_dir / "digests.json").exists()
    assert (case_dir / "final_state_bundle.json").exists()
    assert (case_dir / "performance.json").exists()

    rc_compare = mesh_cli.main(
        [
            "replays",
            "run",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    assert rc_compare == 0

    report = _read_json(out_dir / "suite_report.json")
    assert report["ok"] is True
    assert report["summary"]["total"] == 1
    assert report["summary"]["mismatched"] == 0
    assert report["cases"][0]["run_ok"] is True
    assert report["cases"][0]["match"] is True


def test_cli_replays_run_mismatch_fails_with_actionable_report(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    golden = tmp_path / "ep01_golden.json"
    out_dir = tmp_path / "out"
    _write_suite(suite, golden=golden)

    assert _bootstrap_golden(suite, out_dir, reason="bootstrap mismatch fixture") == 0

    payload = _read_json(golden)
    payload["expected_event_digest"] = "0" * 64
    golden.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rc = mesh_cli.main(
        [
            "replays",
            "run",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    assert rc == 1

    report = _read_json(out_dir / "suite_report.json")
    assert report["ok"] is False
    case = report["cases"][0]
    assert case["error"] == "golden mismatch (1 field(s))"
    fields = [item["field"] for item in case["mismatches"]]
    assert "expected_event_digest" in fields

    text_report = (out_dir / "suite_report.txt").read_text(encoding="utf-8")
    assert "expected_event_digest" in text_report


def test_cli_replays_update_golden_is_deterministic_for_fixture(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    golden = tmp_path / "ep01_golden.json"
    out_dir = tmp_path / "out"
    _write_suite(suite, golden=golden)

    rc_first = _bootstrap_golden(suite, out_dir, reason="first baseline")
    assert rc_first == 0
    first_bytes = golden.read_bytes()

    rc_second = _bootstrap_golden(suite, out_dir, reason="second baseline")
    assert rc_second == 0
    second_bytes = golden.read_bytes()
    assert first_bytes == second_bytes

    payload = _read_json(golden)
    assert len(str(payload["expected_event_digest"])) == 64
    assert len(str(payload["expected_world_digest"])) == 64
    assert len(str(payload["expected_final_state_digest"])) == 64
    assert int(payload["counts"]["event_count"]) > 0
    assert int(payload["counts"]["world_digest_count"]) > 0


def test_cli_replays_run_rejects_update_golden_flag(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    golden = tmp_path / "ep01_golden.json"
    out_dir = tmp_path / "out"
    _write_suite(suite, golden=golden)
    out_dir.mkdir(parents=True, exist_ok=True)

    rc = mesh_cli.main(
        [
            "replays",
            "run",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--update-golden",
            "--quiet",
        ]
    )
    assert rc == 2
    assert not golden.exists()


def test_cli_replays_run_budget_pass_with_monkeypatched_timing(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    golden = tmp_path / "ep01_golden.json"
    out_dir = tmp_path / "out"
    _write_suite(
        suite,
        golden=golden,
        budgets={
            "max_total_ms": 200.0,
            "max_tick_ms_p95": 20.0,
            "max_tick_ms_max": 30.0,
        },
    )

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory(
            total_ms=120.4444,
            tick_ms_p95=12.2222,
            tick_ms_max=20.3333,
            tick_ms_list=[3.4567, 5.1234, 12.2222, 20.3333],
        ),
    )

    rc = _bootstrap_golden(suite, out_dir, reason="bootstrap budget pass")
    assert rc == 0
    rc = mesh_cli.main(
        [
            "replays",
            "run",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    assert rc == 0
    report = _read_json(out_dir / "suite_report.json")
    case = report["cases"][0]
    assert case["ok"] is True
    assert case["budget"]["ok"] is True
    perf = _read_json(out_dir / "ep01" / "performance.json")
    assert perf["performance"]["total_ms"] == 120.444
    assert perf["performance"]["tick_ms_p95"] == 12.222
    assert perf["performance"]["tick_ms_max"] == 20.333


def test_cli_replays_run_budget_fail_is_actionable(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    golden = tmp_path / "ep01_golden.json"
    out_dir = tmp_path / "out"
    _write_suite(
        suite,
        golden=golden,
        budgets={
            "max_total_ms": 100.0,
            "max_tick_ms_p95": 8.0,
            "max_tick_ms_max": 10.0,
        },
    )

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory(
            total_ms=120.0,
            tick_ms_p95=12.0,
            tick_ms_max=22.0,
            tick_ms_list=[3.0, 8.0, 12.0, 22.0],
        ),
    )

    rc = _bootstrap_golden(suite, out_dir, reason="bootstrap budget fail")
    assert rc == 0
    rc = mesh_cli.main(
        [
            "replays",
            "run",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    assert rc == 1
    report = _read_json(out_dir / "suite_report.json")
    case = report["cases"][0]
    assert case["error"] == "budget exceeded"
    assert case["budget"]["ok"] is False
    violations = case["budget"]["violations"]
    metrics = [item["metric"] for item in violations]
    assert "total_ms" in metrics
    assert "tick_ms_p95" in metrics
    assert "tick_ms_max" in metrics


def test_cli_replays_run_budget_skipped_when_selector_disables_enforcement(tmp_path: Path, monkeypatch) -> None:
    suite = tmp_path / "suite.json"
    golden = tmp_path / "ep01_golden.json"
    out_dir = tmp_path / "out"
    _write_suite(
        suite,
        golden=golden,
        budgets={
            "max_total_ms": 1.0,
        },
    )

    monkeypatch.setattr(
        "mesh_cli.replays.episode_commands.handle",
        _fake_episode_handle_factory(
            total_ms=120.0,
            tick_ms_p95=12.0,
            tick_ms_max=22.0,
            tick_ms_list=[3.0, 8.0, 12.0, 22.0],
        ),
    )

    assert _bootstrap_golden(suite, out_dir, reason="bootstrap budget skipped") == 0
    rc = mesh_cli.main(
        [
            "replays",
            "run",
            "--suite",
            str(suite),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--budgets-only-on",
            "none",
            "--quiet",
        ]
    )
    assert rc == 0
    report = _read_json(out_dir / "suite_report.json")
    case = report["cases"][0]
    assert case["budget"]["skipped"] is True
    assert case["budget"]["reason"] == "budget enforcement disabled on this platform"


def test_replay_digest_projection_ignores_report_only_fields() -> None:
    events_base = [{"event_type": "ep01_entered", "payload": {}, "sequence": 0}]
    events_with_info = [
        {
            "event_type": "ep01_entered",
            "payload": {},
            "sequence": 0,
            "seed_ignored": True,
            "timing": {"total_ms": 1.23},
            "provenance": {"platform": "win32"},
        }
    ]
    assert replays_module._sha256_payload(
        replays_module._project_events_for_golden_digest(events_base)
    ) == replays_module._sha256_payload(
        replays_module._project_events_for_golden_digest(events_with_info)
    )

    world_base = [{"tick": 0, "digest": "aaa"}]
    world_with_info = [{"tick": 0, "digest": "aaa", "timing": {"ms": 4.2}, "platform": "linux"}]
    assert replays_module._sha256_payload(
        replays_module._project_world_digests_for_golden_digest(world_base)
    ) == replays_module._sha256_payload(
        replays_module._project_world_digests_for_golden_digest(world_with_info)
    )

    final_state_base = {"schema_version": 1, "final_state": {"flags": {"ok": True}}, "snapshots": []}
    final_state_with_info = {
        "schema_version": 1,
        "final_state": {"flags": {"ok": True}},
        "snapshots": [],
        "seed_ignored": True,
        "host": "ci-node",
        "provenance": {"python_version": "3.11.0"},
    }
    assert replays_module._sha256_payload(
        replays_module._project_final_state_for_golden_digest(final_state_base)
    ) == replays_module._sha256_payload(
        replays_module._project_final_state_for_golden_digest(final_state_with_info)
    )


def test_replay_digest_projection_changes_when_gameplay_payload_changes() -> None:
    events_a = [{"event_type": "ep01_entered", "payload": {}, "sequence": 0}]
    events_b = [{"event_type": "ep01_complete", "payload": {}, "sequence": 0}]
    assert replays_module._sha256_payload(
        replays_module._project_events_for_golden_digest(events_a)
    ) != replays_module._sha256_payload(
        replays_module._project_events_for_golden_digest(events_b)
    )

    world_a = [{"tick": 0, "digest": "aaa"}]
    world_b = [{"tick": 0, "digest": "bbb"}]
    assert replays_module._sha256_payload(
        replays_module._project_world_digests_for_golden_digest(world_a)
    ) != replays_module._sha256_payload(
        replays_module._project_world_digests_for_golden_digest(world_b)
    )

