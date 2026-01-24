import json
import os
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, bytes, bytes]:
    res = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True)
    return res.returncode, res.stdout, res.stderr


def test_list_encounter_presets_output_is_deterministic_and_out_matches_stdout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
    (repo / "packs" / "core_regions" / "data").mkdir(parents=True)
    (repo / "subdir" / "deep").mkdir(parents=True)

    (repo / "packs" / "core_regions" / "data" / "encounter_presets.json").write_text(
        json.dumps(
            {
                "presets": [
                    {"id": "zeta"},
                    {"id": "alpha"},
                    {"id": "normal", "elite_cap": 2},
                ]
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    here = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(here)

    out_path = repo / "out.json"
    cmd = [sys.executable, "-m", "mesh_cli", "list-encounter-presets", "--out", str(out_path)]

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
    assert payload["summary"]["preset_count"] == 3
    assert payload["issues"] == []
    assert [p["id"] for p in payload["presets"]] == ["alpha", "normal", "zeta"]

