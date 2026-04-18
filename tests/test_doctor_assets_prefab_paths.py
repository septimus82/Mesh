from __future__ import annotations

import base64
import json
from pathlib import Path

from mesh_cli.main import main as mesh_main


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_doctor_assets_prefab_paths(tmp_path, monkeypatch, capsys) -> None:
    _write_json(tmp_path / "config.json", {})
    _write_json(tmp_path / "assets" / "data" / "quests.json", [])
    _write_json(tmp_path / "assets" / "data" / "events.json", [])

    sprite_ok = tmp_path / "assets" / "sprites" / "ok.png"
    sprite_ok.parent.mkdir(parents=True, exist_ok=True)
    sprite_ok.write_text("", encoding="utf-8")

    _write_json(
        tmp_path / "assets" / "prefabs.json",
        [
            {
                "display_name": "OK",
                "id": "p_ok",
                "tags": [
                    "test",
                ],
                "entity": {
                    "sprite": "assets/sprites/ok.png",
                },
            }
        ],
    )
    _write_json(
        tmp_path / "packs" / "alpha" / "data" / "prefabs.json",
        [
            {
                "display_name": "Missing",
                "id": "p_missing",
                "tags": [
                    "test",
                ],
                "entity": {
                    "sprite": "assets/sprites/missing.png",
                },
            }
        ],
    )

    def fake_resolve_path(path: str) -> Path:
        return tmp_path / path

    monkeypatch.setattr("engine.repo_root.get_repo_root", lambda start=None, strict=True: tmp_path)
    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])
    monkeypatch.setattr("engine.paths.resolve_path", fake_resolve_path)

    code = mesh_main(["doctor-assets"])
    output = capsys.readouterr().out.strip()
    assert code == 2
    assert "[Assets] missing entity.sprite prefab=p_missing" in output
    assert "source=packs/alpha/data/prefabs.json" in output
    assert "path=assets/sprites/missing.png" in output
    assert "[Assets] missing prefab asset refs: 1" in output

    code = mesh_main(["doctor-assets", "--json"])
    output = capsys.readouterr().out.strip()
    assert code == 2
    lines = output.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["cmd"] == "doctor_assets"
    assert payload["ok"] is False
    missing = payload["missing"]
    assert isinstance(missing, list)
    assert missing and missing[0]["prefab_id"] == "p_missing"
    assert missing[0]["path"] == "assets/sprites/missing.png"
    assert "\\" not in missing[0]["path"]

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
            {
                "display_name": "Warn",
                "id": "p_warn",
                "tags": [
                    "test",
                ],
                "entity": {
                    "sprite_sheet": {
                        "image": "assets/sprites/sheet.png",
                        "frame_width": 2,
                        "frame_height": 2,
                    }
                },
            }
        ],
    )

    code = mesh_main(["doctor-assets", "--json"])
    output = capsys.readouterr().out.strip()
    assert code == 0
    payload = json.loads(output)
    assert payload["ok"] is True
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert warnings and warnings[0]["prefab_id"] == "p_warn"
