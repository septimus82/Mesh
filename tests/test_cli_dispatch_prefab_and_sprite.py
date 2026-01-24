import mesh_cli
import mesh_cli.assets as asset_commands
import mesh_cli.prefabs as prefab_commands


def test_cli_dispatch_prefab(monkeypatch):
    sentinel = 123
    called = {}

    def fake_handle(args):
        called["command"] = args.command
        return sentinel

    monkeypatch.setattr(prefab_commands, "handle", fake_handle)

    assert mesh_cli.main(["prefab", "validate"]) == sentinel
    assert called["command"] == "prefab"


def test_cli_dispatch_sprite_import_aseprite(monkeypatch):
    sentinel = 234
    called = {}

    def fake_handle(args):
        called["command"] = args.command
        called["sprite_command"] = args.sprite_command
        return sentinel

    monkeypatch.setattr(asset_commands, "handle", fake_handle)

    result = mesh_cli.main(
        [
            "sprite",
            "import-aseprite",
            "assets/sprites/example.json",
            "--prefab-id",
            "example",
            "--out",
            "assets/prefabs.json",
        ]
    )
    assert result == sentinel
    assert called["command"] == "sprite"
    assert called["sprite_command"] == "import-aseprite"
