from __future__ import annotations

import base64
import json
from pathlib import Path

from mesh_cli.main import main as mesh_main


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _patch_repo_paths(monkeypatch, tmp_path: Path) -> None:
    def fake_resolve_path(path: str) -> Path:
        return tmp_path / path

    monkeypatch.setattr("mesh_cli.assets.get_repo_root", lambda start=None, strict=True: tmp_path)
    monkeypatch.setattr("engine.repo_root.get_repo_root", lambda start=None, strict=True: tmp_path)
    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])
    monkeypatch.setattr("engine.paths.resolve_path", fake_resolve_path)


def _normalize_output(text: str, tmp_path: Path) -> str:
    cooked = text.replace("\\", "/")
    tmp_norm = tmp_path.as_posix()
    if tmp_norm:
        cooked = cooked.replace(tmp_norm, "<TMP>")
    if cooked.endswith("\n"):
        cooked = cooked[:-1]
    return cooked


def test_doctor_assets_golden_output(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_json(tmp_path / "config.json", {})
    _write_json(tmp_path / "assets" / "data" / "quests.json", [])
    _write_json(tmp_path / "assets" / "data" / "events.json", [])
    _write_json(tmp_path / "assets" / "prefabs.json", [])

    sheet_path = tmp_path / "assets" / "sprites" / "sheet.png"
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
        )
    )
    _write_json(
        tmp_path / "packs" / "alpha" / "data" / "prefabs.json",
        [
            {"id": "p_missing", "entity": {"sprite": "assets/sprites/missing.png"}},
            {
                "id": "p_warn",
                "entity": {
                    "sprite_sheet": {
                        "image": "assets/sprites/sheet.png",
                        "frame_width": 2,
                        "frame_height": 2,
                    }
                },
            },
        ],
    )

    _patch_repo_paths(monkeypatch, tmp_path)

    code = mesh_main(["doctor-assets"])
    output = _normalize_output(capsys.readouterr().out, tmp_path)
    assert code == 2

    expected = "\n".join(
        [
            "[Assets][Warn] image size not divisible by frame size (1x1 % 2x2) field=entity.sprite_sheet "
            "prefab=p_warn source=packs/alpha/data/prefabs.json path=assets/sprites/sheet.png",
            "[Assets] missing entity.sprite prefab=p_missing source=packs/alpha/data/prefabs.json "
            "path=assets/sprites/missing.png",
            "[Assets] missing prefab asset refs: 1",
        ]
    )
    assert output == expected
