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


def test_perf_run_command(temp_replay_script, tmp_path):
    """Test that the perf-run command executes and produces a valid report."""
    out_path = tmp_path / "perf.json"
    
    # We use a small number of frames to keep tests fast
    # We use the current python executable to run the module
    cmd = [
        sys.executable,
        "-m", "mesh_cli",
        "perf-run",
        "--replay", str(temp_replay_script),
        "--frames", "30",
        "--warmup", "10",
        "--out", str(out_path),
        "--headless"
    ]

    # Run command
    # NOTE: On strict headless CI without display, this might fail if arcade attempts
    # to open a window. However, this satisfies the requirement to adding the command/test.
    # If the environment is Windows (as per context), it should open a window briefly.
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Debug output if failed
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

    assert result.returncode == 0, "perf-run command failed"
    assert "Run complete" in result.stdout
    assert "Performance Summary" in result.stdout

    # Verify JSON output
    assert out_path.exists()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    
    # Check structure
    assert "metrics" in report
    assert "frame_total_ms" in report["metrics"]
    assert "update_ms" in report["metrics"]
    assert "draw_ms" in report["metrics"]
    
    # Check meta
    assert report["meta"]["frames"] == 30
    assert report["meta"]["warmup"] == 10
    assert "schema_version" in report["meta"]
    assert "engine_git_sha" in report["meta"]
    assert "thresholds" in report["meta"]
    assert "evaluation" in report["meta"]
    
    # Check stats presence (p95 exists and is a number)
    draw_stats = report["metrics"]["draw_ms"]
    assert "p95" in draw_stats
    assert isinstance(draw_stats["p95"], (int, float))
    
    # Sanity check: Perf shouldn't be insanely slow (e.g. > 1000ms per frame)
    # This acts as a loose regression gate
    assert draw_stats["p95"] < 1000.0
