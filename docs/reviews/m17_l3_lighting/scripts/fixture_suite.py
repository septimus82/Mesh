"""M17-L3 scratch: #459's own fixture room (tooling/hd2d_lighting_demo.fixture_check, the GPU test's evidence) with a
prototype applied: walls and the 0.23-0.33 m panel must still block; GPU and CPU must still agree.
Usage: fixture_suite.py OUT [--patch NAME]"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-l3")
sys.path.insert(0, r"D:\Games\Mesh-l3\tooling")
sys.path.insert(0, str(Path(__file__).parent))
out = Path(sys.argv[1])
patch = sys.argv[sys.argv.index("--patch") + 1] if "--patch" in sys.argv else None
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
import engine.hd2d.lighting as L  # noqa: E402

assert L.__file__.startswith(r"D:\Games\Mesh-l3")
if patch:
    import protos  # noqa: E402

    protos.apply(patch)
import hd2d_lighting_demo  # noqa: E402

from engine.project_scaffold import create_project  # noqa: E402

project = out / f"fixtures_{patch or 'base'}" / "Lamp fixtures"
assert not project.exists()
create_project(project, "Lamp fixtures", "hd2d_rpg")
res = hd2d_lighting_demo.fixture_check(project)
checks = {
    "fixtures": res["fixtures"] == {"lamp_a": ["lamp_a"], "lamp_b": ["lamp_b"]},
    "open_ground_lit": all(res["named"][n]["on"] == res["named"][n]["off"] or abs(res["named"][n]["on"] - res["named"][n]["off"]) <= 1e-3
                           for n in ("a_open_1m", "a_open_2m", "a_open_3m", "a_side_2m", "b_open_2m", "b_before_far_wall")),
    "near_wall_blocks": all(res["named"][n]["on"] == 0.0 for n in ("a_behind_near_wall_1.5m", "a_behind_near_wall_2.5m",
                                                                   "a_behind_near_wall_skew", "a_behind_near_wall_4m")),
    "panel_blocks": all(res["named"][n]["on"] == 0.0 for n in ("a_behind_panel_3.5m", "a_behind_panel_4m", "a_behind_panel_skew")),
    "far_wall_blocks": all(res["named"][n]["on"] == 0.0 for n in ("b_behind_far_wall_1.5m", "b_behind_far_wall_2.5m")),
    "gpu_cpu_agree": res["agreement"]["disagree"] == 0,
}
res["checks"] = checks
(out / f"fixture_suite_{patch or 'base'}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
print(json.dumps({"patch": patch, "checks": checks, "agreement": {k: v for k, v in res["agreement"].items() if k != "mismatches"}}))
