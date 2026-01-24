import mesh_cli
from engine.tooling.doctor import DoctorRunner


def test_doctor_no_issues(monkeypatch, capsys):
    monkeypatch.setattr(DoctorRunner, "_run_lock_audit", lambda self, world_path: None)
    monkeypatch.setattr("engine.tooling.doctor.validate_all.main", lambda argv=None: 0)
    monkeypatch.setattr("engine.tooling.doctor.check.run_check", lambda *a, **k: True)

    rc = mesh_cli.main(["doctor", "--world", "worlds/main_world.json"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "[DOCTOR] Summary: errors=0 warnings=0 checks=2" in out
    assert "[DOCTOR] Errors:" in out
    assert "[DOCTOR] Warnings:" in out
    assert "[DOCTOR] Suggested next commands:" in out
    assert "  - (none)" in out
