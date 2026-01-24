from pathlib import Path

import mesh_cli


def test_cli_sprite_import_sheet_anim_validation_errors(tmp_path: Path, capsys):
    try:
        from PIL import Image
    except Exception:  # pragma: no cover
        return

    image_path = tmp_path / "sheet.png"
    Image.new("RGBA", (32, 16), (255, 0, 0, 255)).save(image_path)

    out_path = tmp_path / "prefabs.json"
    out_path.write_text("[]", encoding="utf-8")

    rc = mesh_cli.main(
        [
            "sprite",
            "import-sheet",
            str(image_path),
            "--prefab-id",
            "bad",
            "--frame-w",
            "16",
            "--frame-h",
            "16",
            "--anim",
            "idle:0-9:8",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "out of bounds" in out

    rc2 = mesh_cli.main(
        [
            "sprite",
            "import-sheet",
            str(image_path),
            "--prefab-id",
            "bad2",
            "--frame-w",
            "16",
            "--frame-h",
            "16",
            "--anim",
            "idle:0-1:0",
            "--out",
            str(out_path),
        ]
    )
    out2 = capsys.readouterr().out
    assert rc2 == 1
    assert "fps must be > 0" in out2

