import json
from pathlib import Path

import mesh_cli


def test_cli_sprite_import_sheet_idempotent(tmp_path: Path):
    try:
        from PIL import Image
    except Exception:  # pragma: no cover
        return

    image_path = tmp_path / "sheet.png"
    Image.new("RGBA", (64, 32), (255, 0, 0, 255)).save(image_path)

    out_path = tmp_path / "prefabs.json"
    out_path.write_text("[]", encoding="utf-8")

    argv = [
        "sprite",
        "import-sheet",
        str(image_path),
        "--prefab-id",
        "test_sheet",
        "--frame-w",
        "16",
        "--frame-h",
        "16",
        "--anim",
        "idle:0-3:8",
        "--out",
        str(out_path),
    ]
    rc = mesh_cli.main(argv)
    assert rc == 0
    first_text = out_path.read_text(encoding="utf-8")

    rc2 = mesh_cli.main(argv)
    assert rc2 == 0
    second_text = out_path.read_text(encoding="utf-8")
    assert second_text == first_text

    payload = json.loads(first_text)
    prefab = next(entry for entry in payload if entry.get("id") == "test_sheet")
    entity = prefab["entity"]
    assert entity["sprite_sheet"]["frame_width"] == 16
    assert entity["sprite_sheet"]["frame_height"] == 16
    assert "idle" in entity["animations"]
    assert entity["animations"]["idle"]["frames"] == [0, 1, 2, 3]
    assert entity["animations"]["idle"]["fps"] == 8.0
    assert entity["animations"]["idle"]["loop"] is True

