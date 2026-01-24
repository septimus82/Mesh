import mesh_cli
from engine.tooling.doctor import DoctorRunner


def test_doctor_suggests_validate_all_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(DoctorRunner, "_run_lock_audit", lambda self, world_path: None)

    def validate_main(argv=None):
        print('{"code":"scene.name.required","path":"name","message":"bad thing"}')
        return 1

    monkeypatch.setattr("engine.tooling.doctor.validate_all.main", validate_main)
    monkeypatch.setattr("engine.tooling.doctor.check.run_check", lambda *a, **k: (_ for _ in ()).throw(AssertionError("check should not run")))

    rc = mesh_cli.main(["doctor", "--world", "worlds/main_world.json"])
    assert rc == 1

    out = capsys.readouterr().out
    assert "[DOCTOR] Summary: errors=1 warnings=0 checks=1" in out
    assert "  - bad thing" in out
    assert "  - mesh validate-all worlds/main_world.json" in out

