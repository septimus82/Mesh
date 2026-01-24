from __future__ import annotations

import json
from pathlib import Path

import mesh_cli


def test_cli_replay_script_prints_json_to_stdout(monkeypatch, tmp_path, capsys):
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps({"steps": []}), encoding="utf-8")

    monkeypatch.setattr(mesh_cli.replay_script, "load_replay_script", lambda p: {"steps": []})
    monkeypatch.setattr(mesh_cli.replay_script, "run_replay_script", lambda _s, **_kw: {"b": 2, "a": 1})

    assert mesh_cli.main(["replay-script", str(script_path)]) == 0
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": 1, "b": 2}


def test_cli_replay_script_writes_file_when_out_provided(monkeypatch, tmp_path):
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps({"steps": []}), encoding="utf-8")

    monkeypatch.setattr(mesh_cli.replay_script, "load_replay_script", lambda p: {"steps": []})
    monkeypatch.setattr(mesh_cli.replay_script, "run_replay_script", lambda _s, **_kw: {"b": 2, "a": 1})

    out_path = tmp_path / "final.json"
    assert mesh_cli.main(["replay-script", str(script_path), "--out", str(out_path)]) == 0

    data = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert data == {"a": 1, "b": 2}
    assert Path(out_path).read_bytes().endswith(b"\n")


def test_cli_replay_script_expect_state_mismatch_exits_nonzero_and_does_not_write_out(monkeypatch, tmp_path):
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps({"steps": [], "expect_state": {"gold": 1}}), encoding="utf-8")

    monkeypatch.setattr(mesh_cli.replay_script, "load_replay_script", lambda p: {"steps": [], "expect_state": {"gold": 1}})
    monkeypatch.setattr(
        mesh_cli.replay_script,
        "run_replay_script",
        lambda _s, **_kw: (_ for _ in ()).throw(ValueError("expect_state mismatch: gold expected 1 got 0")),
    )

    out_path = tmp_path / "final.json"
    assert mesh_cli.main(["replay-script", str(script_path), "--out", str(out_path)]) != 0
    assert not out_path.exists()


def test_cli_replay_script_expect_state_file_failure_does_not_write_out(tmp_path):
    # Real runner: expect_state_file mismatch should exit non-zero and not write output.
    (tmp_path / "expected.json").write_text(json.dumps({"gold": 1}), encoding="utf-8")
    script_path = tmp_path / "script.json"
    script_path.write_text(
        json.dumps({"steps": [{"dump_state": True}], "expect_state_file": "expected.json"}),
        encoding="utf-8",
    )

    out_path = tmp_path / "final.json"
    rc = mesh_cli.main(["replay-script", str(script_path), "--out", str(out_path)])
    assert rc != 0
    assert not out_path.exists()
