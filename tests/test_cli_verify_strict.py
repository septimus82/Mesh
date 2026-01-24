import json

import mesh_cli


def _stub_config(*, world_file: str = "worlds/main_world.json"):
    return type(
        "C",
        (),
        {
            "width": 1,
            "height": 1,
            "title": "t",
            "fullscreen": False,
            "vsync": False,
            "start_scene": "scenes/test.json",
            "world_file": world_file,
        },
    )()


def test_cli_verify_strict_success_emits_canonical_json(monkeypatch, capsys):
    import mesh_cli.legacy_impl as mesh_cli_legacy

    monkeypatch.setattr(mesh_cli_legacy, "load_config", lambda: _stub_config(world_file="worlds/w.json"))

    def _fake_validate_all_main(argv):
        assert argv == ["worlds/w.json", "--strict", "--schema-strict"]
        return 0

    monkeypatch.setattr(mesh_cli.validate_all, "main", _fake_validate_all_main)

    rc = mesh_cli.main(["verify-strict"])
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert rc == 0
    assert payload == {
        "ok": True,
        "code": 0,
        "error": "",
        "world": "worlds/w.json",
        "checks": ["validate-all --strict", "validate-all --schema-strict"],
    }


def test_cli_verify_strict_failure_emits_error_and_nonzero(monkeypatch, capsys):
    import mesh_cli.legacy_impl as mesh_cli_legacy

    monkeypatch.setattr(mesh_cli_legacy, "load_config", lambda: _stub_config(world_file="worlds/w.json"))

    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 1)

    rc = mesh_cli.main(["verify-strict"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["ok"] is False
    assert payload["code"] == 1
    assert payload["error"] == "failed with code 1"
    assert payload["world"] == "worlds/w.json"
