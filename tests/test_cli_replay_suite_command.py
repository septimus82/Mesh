from __future__ import annotations

import json
from pathlib import Path

import mesh_cli


def test_cli_replay_suite_prints_json_to_stdout(monkeypatch, tmp_path, capsys):
    folder = tmp_path / "suite"
    folder.mkdir()
    (folder / "a.json").write_text(json.dumps({"steps": []}), encoding="utf-8")

    monkeypatch.setattr(
        mesh_cli.replay_suite,
        "run_replay_suite",
        lambda _folder: {
            "failed": 0,
            "passed": 1,
            "total": 1,
            "results": [
                {
                    "script": "01_pass.json",
                    "ok": True,
                    "error": "",
                    "state": {"last_zone_id": "ZoneOK"},
                }
            ],
        },
    )

    assert mesh_cli.main(["replay-suite", str(folder)]) == 0
    out = capsys.readouterr().out
    assert json.loads(out) == {
        "failed": 0,
        "passed": 1,
        "total": 1,
        "results": [
            {
                "script": "01_pass.json",
                "ok": True,
                "error": "",
                "state": {"last_zone_id": "ZoneOK"},
            }
        ],
    }


def test_cli_replay_suite_writes_file_when_out_provided(monkeypatch, tmp_path):
    folder = tmp_path / "suite"
    folder.mkdir()
    (folder / "a.json").write_text(json.dumps({"steps": []}), encoding="utf-8")

    monkeypatch.setattr(
        mesh_cli.replay_suite,
        "run_replay_suite",
        lambda _folder: {
            "failed": 0,
            "passed": 1,
            "total": 1,
            "results": [
                {
                    "script": "01_pass.json",
                    "ok": True,
                    "error": "",
                    "state": {"last_zone_id": "ZoneOK"},
                }
            ],
        },
    )

    out_path = tmp_path / "summary.json"
    assert mesh_cli.main(["replay-suite", str(folder), "--out", str(out_path)]) == 0

    data = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert data == {
        "failed": 0,
        "passed": 1,
        "total": 1,
        "results": [
            {
                "script": "01_pass.json",
                "ok": True,
                "error": "",
                "state": {"last_zone_id": "ZoneOK"},
            }
        ],
    }
    assert Path(out_path).read_bytes().endswith(b"\n")
