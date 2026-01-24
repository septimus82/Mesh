import mesh_cli
from engine.tooling.doctor import DoctorRunner


def test_doctor_nonzero_on_errors(monkeypatch, capsys):
    monkeypatch.setattr(DoctorRunner, "_run_lock_audit", lambda self, world_path: (_ for _ in ()).throw(AssertionError("lock should not run")))
    monkeypatch.setattr("engine.tooling.doctor.validate_all.main", lambda argv=None: 0)
    monkeypatch.setattr("engine.tooling.doctor.check.run_check", lambda *a, **k: False)

    rc = mesh_cli.main(["doctor", "--world", "worlds/main_world.json"])
    assert rc == 1

    out = capsys.readouterr().out
    assert "[DOCTOR] Summary: errors=1 warnings=0 checks=2" in out
    assert "  - Quality gate failed." in out
    assert "  - mesh check --world worlds/main_world.json" in out

