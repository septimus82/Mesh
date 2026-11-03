"""GPU-lane measurements and runner calibration (#422): reported on every run, judged against nothing, never failing a
lane, and the terrain frame-time assertion they explain unchanged."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tooling import test_tiers

pytestmark = [pytest.mark.fast]

REPO = Path(__file__).resolve().parents[1]
JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2" time="3.5">
<properties>
<property name="measure.terrain_stroke" value='{"frame_ms": {"median": 57.1, "n": 48}, "commit_ms": 17.6}' />
<property name="measure.note" value="not json" />
<property name="something_else" value="1" />
</properties>
<testcase classname="tests.test_terrain_gpu" name="test_a" time="3.0" />
<testcase classname="tests.test_terrain_gpu" name="test_b" time="0.5" />
</testsuite></testsuites>
"""
CPU = {"cpu": "AMD EPYC 7763 64-Core Processor", "vcpus": 4, "cpu_ms": 24.5}
# What CI's Windows runner reported (#456's first runs).
GL = {"gl_frame_ms": 10.55, "gl_vendor": "Mesa", "gl_renderer": "llvmpipe (LLVM 22.1.1, 256 bits)",
      "gl_version": "4.5 (Compatibility Profile) Mesa 26.0.3 (git-1897b18965)"}
GITHUB = {"RUNNER_OS": "Windows", "ImageOS": "win25", "ImageVersion": "20261030.294", "GALLIUM_DRIVER": "llvmpipe"}


def _calibration(monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str, stderr: str = "") -> dict[str, Any]:
    monkeypatch.setattr(test_tiers.subprocess, "run",
                        lambda *_a, **_k: subprocess.CompletedProcess([], returncode, stdout, stderr))
    return test_tiers.runner_calibration()


def test_a_lane_summary_carries_the_values_tests_recorded(tmp_path: Path) -> None:
    junit = tmp_path / "pytest_gpu.xml"
    junit.write_text(JUNIT, encoding="utf-8")
    run = test_tiers.summarize_junit(junit)
    assert (run.selected, run.passed) == (2, 2)
    assert run.measurements == {"terrain_stroke": {"frame_ms": {"median": 57.1, "n": 48}, "commit_ms": 17.6},
                                "note": "not json"}


def test_a_failing_test_beside_a_measurement_is_still_reported_as_failed(tmp_path: Path) -> None:
    junit = tmp_path / "pytest_gpu.xml"
    junit.write_text(JUNIT.replace('name="test_b" time="0.5" />',
                                   'name="test_b" time="0.5"><failure message="assert (62.63 &lt; 60)" /></testcase>'),
                     encoding="utf-8")
    run = test_tiers.summarize_junit(junit)
    assert run.failed == ["tests.test_terrain_gpu::test_b"] and run.passed == 1
    assert run.measurements["terrain_stroke"]["frame_ms"]["median"] == 57.1


def test_only_the_gpu_lane_calibrates_the_runner() -> None:
    assert {name for name, tier in test_tiers.TIERS.items() if tier.calibrate} == {"gpu"}


@pytest.mark.parametrize("broken", ["raises", "garbage", "nothing"])
def test_a_calibration_that_fails_is_reported_never_raised(monkeypatch: pytest.MonkeyPatch, broken: str) -> None:
    def run(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        if broken == "raises":
            raise subprocess.TimeoutExpired("python", 120)
        return subprocess.CompletedProcess([], 1, "Traceback ..." if broken == "garbage" else "", "")

    monkeypatch.setattr(test_tiers.subprocess, "run", run)
    result = test_tiers.runner_calibration()
    assert set(result) == {"complete", "error"} and result["complete"] is False and result["error"]


def test_a_runner_that_cant_draw_still_reports_its_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = "Traceback (most recent call last):\n  ...\npyglet.window.NoSuchConfigException: no GL config"
    result = _calibration(monkeypatch, 1, json.dumps(CPU) + "\n", stderr)
    assert result == {**CPU, "complete": False,
                      "error": "no gl_frame_ms; pyglet.window.NoSuchConfigException: no GL config"}


def test_a_zero_exit_with_only_the_cpu_is_an_incomplete_calibration(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _calibration(monkeypatch, 0, json.dumps(CPU) + "\n")
    assert result == {**CPU, "complete": False, "error": "no gl_frame_ms"}


@pytest.mark.parametrize("frame", ["fast", 0, -1.5, True, None])
def test_an_invalid_frame_time_is_dropped_and_said(monkeypatch: pytest.MonkeyPatch, frame: object) -> None:
    result = _calibration(monkeypatch, 0, json.dumps(CPU) + "\n" + json.dumps({**GL, "gl_frame_ms": frame}) + "\n")
    assert result["complete"] is False and "gl_frame_ms" not in result
    assert result["error"] == f"invalid gl_frame_ms {frame!r}" and result["cpu_ms"] == 24.5


def test_a_complete_calibration_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _calibration(monkeypatch, 0, json.dumps(CPU) + "\n" + json.dumps(GL) + "\n")
    assert result == {**CPU, **GL, "complete": True}


def test_the_host_names_the_runner_image_gl_and_mesa_settings() -> None:
    assert test_tiers.runner_host({**CPU, **GL}, GITHUB) == {
        "runner_os": "Windows", "image_os": "win25", "image_version": "20261030.294", "gl_vendor": "Mesa",
        "gl_renderer": "llvmpipe (LLVM 22.1.1, 256 bits)",
        "gl_version": "4.5 (Compatibility Profile) Mesa 26.0.3 (git-1897b18965)",
        "mesa_version": "26.0.3", "llvm_version": "22.1.1", "mesa_env": {"GALLIUM_DRIVER": "llvmpipe"}}
    ubuntu = {**GL, "gl_renderer": "llvmpipe (LLVM 21.1.8, 256 bits)",
              "gl_version": "4.5 (Core Profile) Mesa 26.0.8-1ubuntu0.3"}
    host = test_tiers.runner_host(ubuntu, {"RUNNER_OS": "Linux"})
    assert (host["mesa_version"], host["llvm_version"]) == ("26.0.8-1ubuntu0.3", "21.1.8")


def test_outside_github_the_runner_fields_are_unavailable_not_an_error() -> None:
    host = test_tiers.runner_host({**CPU, **GL}, {})
    assert {host[k] for k in ("runner_os", "image_os", "image_version")} == {"unavailable"}
    assert host["mesa_env"] == {} and host["gl_vendor"] == "Mesa"


@pytest.mark.parametrize("gl", [{}, {"gl_vendor": "", "gl_renderer": 42, "gl_version": ["4.5"]},
                                {"gl_vendor": "NVIDIA Corporation", "gl_renderer": "NVIDIA GeForce RTX 4070",
                                 "gl_version": "4.6.0 NVIDIA 610.88"}])
def test_missing_or_malformed_gl_strings_are_unavailable(gl: dict[str, object]) -> None:
    host = test_tiers.runner_host({**CPU, **gl}, GITHUB)
    assert host["mesa_version"] == host["llvm_version"] == "unavailable"
    for key in ("gl_vendor", "gl_renderer", "gl_version"):
        assert host[key] == (gl[key] if isinstance(gl.get(key), str) and gl[key] else "unavailable")


def test_only_the_allowlisted_mesa_settings_are_recorded() -> None:
    env = {**GITHUB, "LP_NUM_THREADS": "4", "LIBGL_ALWAYS_SOFTWARE": "1", "MESA_GL_VERSION_OVERRIDE": "",
           "GITHUB_TOKEN": "ghs_secret", "MESA_SHADER_CACHE_DIR": "C:/cache", "PATH": "C:/Windows"}
    assert test_tiers.runner_host(GL, env)["mesa_env"] == {
        "GALLIUM_DRIVER": "llvmpipe", "LP_NUM_THREADS": "4", "LIBGL_ALWAYS_SOFTWARE": "1"}
    assert set(test_tiers.MESA_ENV) == {"GALLIUM_DRIVER", "LIBGL_ALWAYS_SOFTWARE", "LP_NUM_THREADS",
                                         "MESA_GL_VERSION_OVERRIDE", "MESA_GLSL_VERSION_OVERRIDE",
                                         "MESA_LOADER_DRIVER_OVERRIDE"}


def _gpu_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, before: dict[str, Any]) -> dict[str, Any]:
    """``python -m tooling.test_tiers gpu`` with pytest, the GL probe and the calibration stubbed, in ``tmp_path``."""
    monkeypatch.setattr(test_tiers, "__file__", str(tmp_path / "tooling" / "test_tiers.py"))
    calibrations = iter([before, {**CPU, **GL, "complete": True}])
    monkeypatch.setattr(test_tiers, "runner_calibration", lambda: next(calibrations))
    monkeypatch.setattr(test_tiers, "gl_renderer", lambda: "llvmpipe (LLVM 22.1.1, 256 bits) | 4.5 Mesa 26.0.3")
    for name, value in GITHUB.items():
        monkeypatch.setenv(name, value)

    def pytest_run(cmd: list[str], **_k: Any) -> int:
        junit = next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("--junitxml="))
        Path(junit).write_text(JUNIT, encoding="utf-8")
        return 0

    monkeypatch.setattr(test_tiers, "_run", pytest_run)
    assert test_tiers.main(["gpu", "--", "-k", "x"]) == 0
    return dict(json.loads((tmp_path / "artifacts" / "pytest_gpu_summary.json").read_text(encoding="utf-8")))


def test_the_gpu_summary_holds_the_runner_host_and_measurements(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _gpu_summary(tmp_path, monkeypatch, {**CPU, **GL, "complete": True})
    assert summary["runner"]["before"]["gl_frame_ms"] == 10.55 and summary["runner"]["after"]["complete"] is True
    assert summary["runner"]["host"]["image_version"] == "20261030.294"
    assert summary["runner"]["host"]["mesa_env"] == {"GALLIUM_DRIVER": "llvmpipe"}
    assert summary["measurements"]["terrain_stroke"]["commit_ms"] == 17.6 and summary["problems"] == []


def test_the_calibration_measures_this_runner() -> None:
    proc = subprocess.run([sys.executable, "-c", "from tooling import runner_calibration as c; "
                           "print(c.cpu_model(), c.cpu_ms())"], capture_output=True, text=True, cwd=REPO, check=True)
    model, ms = proc.stdout.strip().rsplit(" ", 1)
    assert model and float(ms) > 0


def test_the_terrain_stroke_is_recorded_before_its_unchanged_assertions() -> None:
    source = (REPO / "tests" / "test_terrain_gpu.py").read_text(encoding="utf-8")
    body = source[source.index("def test_studio_sculpts_live_one_stroke_one_undo_step"):]
    body = body[:body.index("\n\n\n")]
    record = body.index('record_testsuite_property("measure.terrain_stroke"')
    # The 60 ms limit and the rest of the assertion, byte for byte as before (#422: never weakened).
    limit = 'assert s["frame_ms"]["median"] < 60 and s["commit_ms"] < 200, s  # no room reload per click'
    assert body.count(limit) == 1
    assert record < body.index("    assert "), "recorded before any assertion, so failing runs report it too"


def _summary_step() -> str:
    text = (REPO / ".github" / "workflows" / "extended.yml").read_text(encoding="utf-8")
    return text[text.index("- name: Lane summary"):text.index("- name: Upload lane reports")]


def test_the_lane_summary_shows_the_runner_and_the_measurements() -> None:
    step = _summary_step()
    assert 'foreach ($when in "before", "after")' in step and "$s.runner.$when" in step
    assert "llvmpipe frame $frame" in step and 'else { "none ($($c.error))" }' in step
    assert "no calibration: $($c.error)" in step
    assert "$s.runner.host" in step and "Mesa $($h.mesa_version), LLVM $($h.llvm_version)" in step
    assert "$s.measurements.PSObject.Properties" in step


@pytest.mark.integration
@pytest.mark.skipif(not (shutil.which("pwsh") or shutil.which("powershell")), reason="needs PowerShell")
def test_the_job_summary_renders_a_real_gpu_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    incomplete = {**CPU, "complete": False, "error": "no gl_frame_ms"}
    summary = _gpu_summary(tmp_path, monkeypatch, incomplete)
    body = _summary_step().split("run: |", 1)[1]
    script = "\n".join(line[10:] for line in body.splitlines()).replace("${{ matrix.lane }}", "gpu").replace(
        "${{ matrix.os }}", "windows-latest").replace(
        "${{ matrix.shard && format(', shard {0}', matrix.shard) || '' }}", ", shard 2/2")
    (tmp_path / "step.ps1").write_text(script, encoding="utf-8")
    out = tmp_path / "summary.md"
    shell = shutil.which("pwsh") or shutil.which("powershell")
    subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-File", str(tmp_path / "step.ps1")], cwd=tmp_path,
                   env={**os.environ, "GITHUB_STEP_SUMMARY": str(out)}, check=True, timeout=60)
    text = out.read_text(encoding="utf-8-sig")
    # The before run couldn't draw; the host's GL strings come from the after run, which could.
    assert summary["runner"]["before"]["complete"] is False
    assert ("- host: Windows, image win25 20261030.294; GL Mesa | llvmpipe (LLVM 22.1.1, 256 bits) | "
            "4.5 (Compatibility Profile) Mesa 26.0.3 (git-1897b18965); Mesa 26.0.3, LLVM 22.1.1; "
            "Mesa settings: GALLIUM_DRIVER=llvmpipe") in text
    assert "- runner before: AMD EPYC 7763 64-Core Processor, 4 vCPU; cpu loop 24.5 ms; llvmpipe frame none " \
           "(no gl_frame_ms)" in text
    assert "- runner after: AMD EPYC 7763 64-Core Processor, 4 vCPU; cpu loop 24.5 ms; llvmpipe frame 10.55 ms" in text
    assert '- measured terrain_stroke: `{"frame_ms":{"median":57.1,"n":48},"commit_ms":17.6}`' in text
