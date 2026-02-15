from __future__ import annotations

import json
from pathlib import Path

import mesh_cli


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_episode_replay_check_identical_seed_produces_identical_digests_and_events(tmp_path: Path) -> None:
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    rc_a = mesh_cli.main(
        [
            "episode",
            "replay-check",
            "--scene",
            "episode_01_intro.json",
            "--script",
            "replays/ep01.json",
            "--out-dir",
            str(out_a),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    rc_b = mesh_cli.main(
        [
            "episode",
            "replay-check",
            "--scene",
            "episode_01_intro.json",
            "--script",
            "replays/ep01.json",
            "--out-dir",
            str(out_b),
            "--seed",
            "123",
            "--quiet",
        ]
    )

    assert rc_a == 0
    assert rc_b == 0
    assert (out_a / "digests.json").read_bytes() == (out_b / "digests.json").read_bytes()
    assert (out_a / "events.ndjson").read_bytes() == (out_b / "events.ndjson").read_bytes()


def test_episode_replay_check_invalid_entity_is_actionable(tmp_path: Path) -> None:
    bad_script = tmp_path / "bad_replay.json"
    bad_script.write_text(
        json.dumps(
            {
                "dt_schedule": [0.1, 0.1, 0.1],
                "actions": [
                    {"t": 0, "type": "emit", "event": "ep01_entered"},
                    {"t": 1, "type": "interact", "entity": "missing_terminal"},
                ],
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "bad_out"

    rc = mesh_cli.main(
        [
            "episode",
            "replay-check",
            "--scene",
            "episode_01_intro.json",
            "--script",
            str(bad_script),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )

    assert rc == 1
    report = _read_json(out_dir / "replay_report.json")
    assert report["ok"] is False
    error = str(report["run_1"]["error"])
    assert "missing_terminal" in error
    assert "not found" in error or "actions[" in error


def test_episode_replay_check_save_restore_preserves_determinism(tmp_path: Path) -> None:
    out_dir = tmp_path / "ep02"

    rc = mesh_cli.main(
        [
            "episode",
            "replay-check",
            "--scene",
            "episode_02_ep02.json",
            "--script",
            "replays/ep02.json",
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )

    assert rc == 0
    report = _read_json(out_dir / "replay_report.json")
    assert report["ok"] is True
    assert report["run_1"]["save_actions"] > 0
    assert report["run_1"]["restore_actions"] > 0
    assert report["determinism"]["digests_match"] is True
    assert report["determinism"]["events_match"] is True
    assert report["determinism"]["final_state_match"] is True
    assert (out_dir / "save_restore_diagnostics.json").exists()
    assert (out_dir / "save_restore_diagnostics.txt").exists()
