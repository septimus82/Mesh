import json
import os
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, bytes, bytes]:
    res = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True)
    return res.returncode, res.stdout, res.stderr


def test_list_worlds_output_is_deterministic_and_out_matches_stdout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "worlds").mkdir()
    (repo / "subdir" / "deep").mkdir(parents=True)

    (repo / "worlds" / "a.json").write_text(
        json.dumps(
            {
                "id": "w1",
                "start_scene": "s2",
                "scenes": {"s2": {"path": "scenes/b.json"}, "s1": {"path": "scenes/a.json"}},
                "links": [{}, {}],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "worlds" / "b.json").write_text(
        json.dumps({"id": "w2", "scenes": {"x": {"path": "scenes/x.json"}}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    here = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(here)

    out_path = repo / "out.json"
    cmd = [sys.executable, "-m", "mesh_cli", "list-worlds", "--out", str(out_path)]

    code1, stdout1, stderr1 = _run(cmd, cwd=repo / "subdir" / "deep", env=env)
    assert code1 == 0, stderr1.decode("utf-8", errors="replace")
    assert stderr1 == b""
    assert stdout1.endswith(b"\n")

    code2, stdout2, stderr2 = _run(cmd, cwd=repo / "subdir" / "deep", env=env)
    assert code2 == 0, stderr2.decode("utf-8", errors="replace")
    assert stderr2 == b""
    assert stdout2 == stdout1

    file_bytes = out_path.read_bytes()
    assert file_bytes.endswith(b"\n")
    assert file_bytes == stdout1

    payload = json.loads(stdout1.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["summary"]["world_count"] == 2

    paths = [w["path"] for w in payload["worlds"]]
    assert paths == ["worlds/a.json", "worlds/b.json"]

    a = payload["worlds"][0]
    assert a["world_id"] == "w1"
    assert a["scene_count"] == 2
    assert a["start_scene"] == "s2"
    assert a["start_scene_ok"] is True
    assert a["scene_ids_sample"] == ["s1", "s2"]
    assert a["issues"] == []

    b = payload["worlds"][1]
    assert b["world_id"] == "w2"
    assert b["scene_count"] == 1
    assert b["start_scene"] is None
    assert b["start_scene_ok"] is None
    assert b["scene_ids_sample"] == ["x"]
    assert b["issues"] == ["world.start_scene.required"]

