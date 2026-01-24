import json

import mesh_cli
from engine.tooling.doctor import DoctorRunner


def test_doctor_json_schema(monkeypatch, capsys):
    monkeypatch.setattr(DoctorRunner, "_run_lock_audit", lambda self, world_path: None)
    monkeypatch.setattr("engine.tooling.doctor.validate_all.main", lambda argv=None: 0)
    monkeypatch.setattr("engine.tooling.doctor.check.run_check", lambda *a, **k: True)

    rc = mesh_cli.main(["doctor", "--world", "worlds/main_world.json", "--json"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == 1
    assert payload["world"] == "worlds/main_world.json"
    assert isinstance(payload["checks"], list)
    assert isinstance(payload["next"], list)
    assert isinstance(payload["artifacts"], list)
    # Check that we have checks corresponding to runs
    assert len(payload["checks"]) >= 2

