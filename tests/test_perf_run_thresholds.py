import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def temp_replay_script(tmp_path):
    replay_path = tmp_path / "perf_test.json"
    data = {
        "steps": [
            {"emit": "entered_zone", "zone_id": "test_zone"},
            {"dump_state": True}
        ]
    }
    replay_path.write_text(json.dumps(data), encoding="utf-8")
    return replay_path


def test_perf_run_thresholds_fail_and_pass(temp_replay_script, tmp_path):
    out_fail = tmp_path / "perf_fail.json"
    cmd_fail = [
        sys.executable,
        "-m", "mesh_cli",
        "perf-run",
        "--replay", str(temp_replay_script),
        "--frames", "10",
        "--warmup", "1",
        "--out", str(out_fail),
        "--headless",
        "--fail-p95-frame-ms", "0.0001",
    ]
    result_fail = subprocess.run(cmd_fail, capture_output=True, text=True)
    assert result_fail.returncode != 0, result_fail.stdout + result_fail.stderr
    assert "Threshold failures" in result_fail.stdout

    report_fail = json.loads(out_fail.read_text(encoding="utf-8"))
    assert report_fail["meta"]["thresholds"]["fail_p95_frame_ms"] == 0.0001
    assert report_fail["meta"]["evaluation"]["ok"] is False
    assert report_fail["meta"]["evaluation"]["failed"]

    out_pass = tmp_path / "perf_pass.json"
    cmd_pass = [
        sys.executable,
        "-m", "mesh_cli",
        "perf-run",
        "--replay", str(temp_replay_script),
        "--frames", "10",
        "--warmup", "1",
        "--out", str(out_pass),
        "--headless",
        "--fail-p95-frame-ms", "1000000",
    ]
    result_pass = subprocess.run(cmd_pass, capture_output=True, text=True)
    assert result_pass.returncode == 0, result_pass.stdout + result_pass.stderr

    report_pass = json.loads(out_pass.read_text(encoding="utf-8"))
    assert report_pass["meta"]["thresholds"]["fail_p95_frame_ms"] == 1000000
    assert report_pass["meta"]["evaluation"]["ok"] is True
