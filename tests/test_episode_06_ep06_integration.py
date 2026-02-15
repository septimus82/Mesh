from __future__ import annotations

import json
from pathlib import Path

import mesh_cli


def _write_script(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_replay(script_path: Path, out_dir: Path) -> dict:
    rc = mesh_cli.main(
        [
            "episode",
            "replay-check",
            "--scene",
            "episode_06_ep06.json",
            "--script",
            str(script_path),
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    assert rc == 0
    return json.loads((out_dir / "replay_report.json").read_text(encoding="utf-8"))


def _base_script() -> dict:
    return {
        "dt_schedule": [0.2] * 18,
        "actions": [],
        "steps": [{"dump_state": True}],
    }


def test_episode_06_fight_path_happy() -> None:
    script = _base_script()
    script["actions"] = [
        {"t": 0, "type": "emit", "event": "ep06_entered"},
        {"t": 2, "type": "dialogue_choose", "choice": 0},
        {"t": 3, "type": "emit", "event": "died", "payload": {"name": "Episode06FightSentry"}},
        {"t": 4, "type": "interact", "entity": "episode_06_ep06_rune_a"},
        {"t": 5, "type": "interact", "entity": "episode_06_ep06_rune_b"},
        {"t": 6, "type": "interact", "entity": "episode_06_ep06_reward_cache"},
        {"t": 7, "type": "interact", "entity": "episode_06_ep06_exit_door"},
        {"t": 10, "type": "assert_flag", "flag": "ep06.complete", "value": True},
    ]

    out_dir = Path("artifacts/tests/ep06_fight")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_script(out_dir / "script.json", script)
    report = _run_replay(out_dir / "script.json", out_dir)
    assert report["ok"] is True
    assert report["determinism"]["events_match"] is True
    assert report["determinism"]["digests_match"] is True


def test_episode_06_puzzle_path_happy() -> None:
    script = _base_script()
    script["actions"] = [
        {"t": 0, "type": "emit", "event": "ep06_entered"},
        {"t": 2, "type": "dialogue_choose", "choice": 1},
        {"t": 3, "type": "emit", "event": "died", "payload": {"name": "Episode06PuzzleSentry"}},
        {"t": 4, "type": "interact", "entity": "episode_06_ep06_rune_a"},
        {"t": 5, "type": "interact", "entity": "episode_06_ep06_rune_b"},
        {"t": 6, "type": "interact", "entity": "episode_06_ep06_reward_bonus_cache"},
        {"t": 7, "type": "interact", "entity": "episode_06_ep06_exit_door"},
        {"t": 10, "type": "assert_flag", "flag": "ep06.reward_bonus_collected", "value": True},
        {"t": 11, "type": "assert_flag", "flag": "ep06.complete", "value": True},
    ]

    out_dir = Path("artifacts/tests/ep06_puzzle")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_script(out_dir / "script.json", script)
    report = _run_replay(out_dir / "script.json", out_dir)
    assert report["ok"] is True


def test_episode_06_save_restore_mid_cutscene() -> None:
    script = _base_script()
    script["actions"] = [
        {"t": 0, "type": "emit", "event": "ep06_entered"},
        {"t": 1, "type": "save", "slot": "mid_cutscene"},
        {"t": 2, "type": "restore", "slot": "mid_cutscene"},
        {"t": 4, "type": "dialogue_choose", "choice": 0},
        {"t": 5, "type": "emit", "event": "died", "payload": {"name": "Episode06FightSentry"}},
        {"t": 6, "type": "interact", "entity": "episode_06_ep06_rune_a"},
        {"t": 7, "type": "interact", "entity": "episode_06_ep06_rune_b"},
        {"t": 8, "type": "interact", "entity": "episode_06_ep06_reward_cache"},
        {"t": 9, "type": "interact", "entity": "episode_06_ep06_exit_door"},
        {"t": 12, "type": "assert_flag", "flag": "ep06.complete", "value": True},
    ]

    out_dir = Path("artifacts/tests/ep06_mid_cutscene")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_script(out_dir / "script.json", script)
    report = _run_replay(out_dir / "script.json", out_dir)
    assert report["ok"] is True
    assert report["run_1"]["save_actions"] >= 1
    assert report["run_1"]["restore_actions"] >= 1


def test_episode_06_save_restore_mid_combat() -> None:
    script = _base_script()
    script["actions"] = [
        {"t": 0, "type": "emit", "event": "ep06_entered"},
        {"t": 2, "type": "dialogue_choose", "choice": 0},
        {"t": 3, "type": "save", "slot": "mid_combat"},
        {"t": 4, "type": "emit", "event": "died", "payload": {"name": "Episode06FightSentry"}},
        {"t": 5, "type": "restore", "slot": "mid_combat"},
        {"t": 6, "type": "emit", "event": "died", "payload": {"name": "Episode06FightSentry"}},
        {"t": 7, "type": "interact", "entity": "episode_06_ep06_rune_a"},
        {"t": 8, "type": "interact", "entity": "episode_06_ep06_rune_b"},
        {"t": 9, "type": "interact", "entity": "episode_06_ep06_reward_cache"},
        {"t": 10, "type": "interact", "entity": "episode_06_ep06_exit_door"},
        {"t": 13, "type": "assert_flag", "flag": "ep06.complete", "value": True},
    ]

    out_dir = Path("artifacts/tests/ep06_mid_combat")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_script(out_dir / "script.json", script)
    report = _run_replay(out_dir / "script.json", out_dir)
    assert report["ok"] is True


def test_episode_06_save_restore_mid_puzzle_reset_window() -> None:
    script = {
        "dt_schedule": [0.1] * 22,
        "actions": [
            {"t": 0, "type": "emit", "event": "ep06_entered"},
            {"t": 4, "type": "dialogue_choose", "choice": 1},
            {"t": 5, "type": "emit", "event": "died", "payload": {"name": "Episode06PuzzleSentry"}},
            {"t": 6, "type": "save", "slot": "reset_window"},
            {"t": 7, "type": "interact", "entity": "episode_06_ep06_rune_b"},
            {"t": 8, "type": "restore", "slot": "reset_window"},
            {"t": 10, "type": "interact", "entity": "episode_06_ep06_rune_a"},
            {"t": 11, "type": "interact", "entity": "episode_06_ep06_rune_b"},
            {"t": 12, "type": "interact", "entity": "episode_06_ep06_reward_bonus_cache"},
            {"t": 13, "type": "interact", "entity": "episode_06_ep06_exit_door"},
            {"t": 16, "type": "assert_flag", "flag": "ep06.complete", "value": True},
        ],
        "steps": [{"dump_state": True}],
    }

    out_dir = Path("artifacts/tests/ep06_mid_reset")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_script(out_dir / "script.json", script)
    report = _run_replay(out_dir / "script.json", out_dir)
    assert report["ok"] is True


def test_episode_06_determinism_digest_and_event_sequences() -> None:
    script = _base_script()
    script["actions"] = [
        {"t": 0, "type": "emit", "event": "ep06_entered"},
        {"t": 2, "type": "dialogue_choose", "choice": 1},
        {"t": 3, "type": "emit", "event": "died", "payload": {"name": "Episode06PuzzleSentry"}},
        {"t": 4, "type": "interact", "entity": "episode_06_ep06_rune_a"},
        {"t": 5, "type": "save", "slot": "mid"},
        {"t": 6, "type": "interact", "entity": "episode_06_ep06_rune_b"},
        {"t": 7, "type": "restore", "slot": "mid"},
        {"t": 8, "type": "interact", "entity": "episode_06_ep06_rune_b"},
        {"t": 9, "type": "interact", "entity": "episode_06_ep06_reward_bonus_cache"},
        {"t": 10, "type": "interact", "entity": "episode_06_ep06_exit_door"},
        {"t": 13, "type": "assert_flag", "flag": "ep06.complete", "value": True},
    ]

    out_a = Path("artifacts/tests/ep06_det_a")
    out_b = Path("artifacts/tests/ep06_det_b")
    out_a.mkdir(parents=True, exist_ok=True)
    out_b.mkdir(parents=True, exist_ok=True)
    _write_script(out_a / "script.json", script)
    _write_script(out_b / "script.json", script)

    report_a = _run_replay(out_a / "script.json", out_a)
    report_b = _run_replay(out_b / "script.json", out_b)

    assert report_a["ok"] is True
    assert report_b["ok"] is True
    assert (out_a / "events.ndjson").read_bytes() == (out_b / "events.ndjson").read_bytes()
    assert (out_a / "digests.json").read_bytes() == (out_b / "digests.json").read_bytes()
