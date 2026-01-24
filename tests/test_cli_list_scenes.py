import json
import os
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, bytes, bytes]:
    res = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True)
    return res.returncode, res.stdout, res.stderr


def test_list_scenes_output_is_deterministic_and_out_matches_stdout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "scenes").mkdir()
    (repo / "packs" / "p1" / "scenes").mkdir(parents=True)
    (repo / "subdir").mkdir()

    (repo / "scenes" / "a.json").write_text(
        json.dumps(
            {
                "entities": [
                    {"id": " A ", "name": "Hero"},
                    {"id": "a", "name": "Hero2"},
                    {"name": "MissingId"},
                    {"behaviours": ["TriggerZone"], "behaviour_config": {"TriggerZone": {}}},
                    {"behaviours": ["TriggerZone"], "behaviour_config": {"TriggerZone": {"zone_id": " Z "}}},
                    {"behaviours": ["TriggerZone"], "behaviour_config": {"TriggerZone": {"zone_id": "z"}}},
                    {"behaviours": ["SceneTransition"]},
                    {"mesh_name": "MeshOnly"},
                    {"mesh_name": " meshonly "},
                ]
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    (repo / "packs" / "p1" / "scenes" / "b.json").write_text(
        json.dumps({"entities": [{"id": "B"}]}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    here = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(here)

    out_path = repo / "out.json"
    cmd = [sys.executable, "-m", "mesh_cli", "list-scenes", "--out", str(out_path)]

    code1, stdout1, stderr1 = _run(cmd, cwd=repo / "subdir", env=env)
    assert code1 == 0, stderr1.decode("utf-8", errors="replace")
    assert stderr1 == b""
    assert stdout1.endswith(b"\n")

    code2, stdout2, stderr2 = _run(cmd, cwd=repo / "subdir", env=env)
    assert code2 == 0, stderr2.decode("utf-8", errors="replace")
    assert stderr2 == b""
    assert stdout2 == stdout1

    file_bytes = out_path.read_bytes()
    assert file_bytes.endswith(b"\n")
    assert file_bytes == stdout1

    payload = json.loads(stdout1.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["summary"]["scene_count"] == 2

    paths = [s["path"] for s in payload["scenes"]]
    assert paths == ["packs/p1/scenes/b.json", "scenes/a.json"]

    a = payload["scenes"][1]
    assert a["entity_count"] == 9
    assert a["trigger_zone_count"] == 3
    assert a["transition_count"] == 1
    assert a["id"] == {"duplicates": 1, "missing": 7, "unique": 1}
    assert a["zone_id"] == {"duplicates": 1, "missing": 1, "unique": 1}
    assert a["mesh_name"] == {"duplicates": 1, "missing": 4, "unique": 4}
    assert a["issues"] == [
        "entity.id.required",
        "trigger_zone.zone_id.required",
        "entity.id.duplicate",
        "trigger_zone.zone_id.duplicate",
    ]

    b = payload["scenes"][0]
    assert b["issues"] == []
