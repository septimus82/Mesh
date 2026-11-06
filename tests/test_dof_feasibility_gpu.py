"""#460 Phase A EVIDENCE ONLY (branch evidence/460-dof-phase-a, never merged): runs the scratch depth-of-field lab
(docs/reviews/dof_phase_a/dof_lab.py, a prototype pass attached to one process's renderer, no product change) on the
HD-2D template's village and cottage in a hidden window, so CI's Mesa llvmpipe (Windows and Ubuntu) reports what the
pass costs and does there. Numbers are recorded (``measure.dof_phase_a``) and the lab's report is kept under
artifacts/ as a .log; nothing is judged against a budget. GL-gated: set MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]

REPO = Path(__file__).resolve().parents[1]


def test_dof_phase_a_lab_on_the_template(tmp_path: Path, record_testsuite_property) -> None:
    from engine.project_scaffold import create_project

    project = tmp_path / "template"
    create_project(project, "DoF Template", template_id="hd2d_rpg")
    out = tmp_path / "lab"
    env = {**os.environ, "ACC_REPO": str(REPO)}
    proc = subprocess.run([sys.executable, str(REPO / "docs/reviews/dof_phase_a/dof_lab.py"), str(project), str(out),
                           "--set", "template", "--frames", "20", "--motion", "15", "--loops", "40"],
                          cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=3000)
    report_path = out / "report.json"
    keep = REPO / "artifacts" / "dof_phase_a"
    keep.mkdir(parents=True, exist_ok=True)
    tag = f"{sys.platform}"
    (keep / f"lab_stdout_{tag}.log").write_text(proc.stdout[-20000:] + "\n--- stderr ---\n" + proc.stderr[-20000:],
                                                encoding="utf-8")
    if report_path.exists():
        shutil.copy(report_path, keep / f"report_{tag}.json.log")
    assert proc.returncode == 0, proc.stderr[-3000:]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    compact = {"gl": report["gl"], "size": report["size"],
               "zero_strength_bit_identical_to_off": report.get("zero_strength_bit_identical_to_off"),
               "hud": report.get("hud"), "motion": report.get("motion"),
               "views": {name: {"timing": v["timing"], "same_row": v["same_row_comparisons"][:2],
                                "player_pixels_diff": v.get("player_pixels_diff")}
                         for name, v in report["views"].items()},
               "resizes": {k: {"dof_ms": v["dof_ms"]} for k, v in report["gl_objects"]["after_resizes"].items()}}
    record_testsuite_property("measure.dof_phase_a", json.dumps(compact))
    assert report.get("zero_strength_bit_identical_to_off") is True
