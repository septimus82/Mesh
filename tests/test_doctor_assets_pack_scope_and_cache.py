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


def test_doctor_assets_pack_scope(tmp_path, monkeypatch, capsys) -> None:
    _write_json(tmp_path / "config.json", {})
    _write_json(tmp_path / "assets" / "data" / "quests.json", [])
    _write_json(tmp_path / "assets" / "data" / "events.json", [])
    _write_json(tmp_path / "assets" / "prefabs.json", [])

    _write_json(
        tmp_path / "packs" / "alpha" / "data" / "prefabs.json",
        [
            {
                "display_name": "Alpha Missing",
                "id": "p_alpha_missing",
                "tags": [
                    "test",
                ],
                "entity": {
                    "sprite": "assets/sprites/alpha.png",
                },
            }
        ],
    )
    _write_json(
        tmp_path / "packs" / "beta" / "data" / "prefabs.json",
        [
            {
                "display_name": "Beta Missing",
                "id": "p_beta_missing",
                "tags": [
                    "test",
                ],
                "entity": {
                    "sprite": "assets/sprites/beta.png",
                },
            }
        ],
    )

    _patch_repo_paths(monkeypatch, tmp_path)

    code = mesh_main(["doctor-assets", "--pack", "alpha"])
    output = capsys.readouterr().out
    assert code == 2
    assert "prefab=p_alpha_missing" in output
    assert "prefab=p_beta_missing" not in output
    assert "path=assets/sprites/alpha.png" in output
    assert "\\" not in output

    code = mesh_main(["doctor-assets", "--pack", "alpha", "--json"])
    output = capsys.readouterr().out.strip()
    assert code == 2
    payload = json.loads(output)
    assert payload["packs"] == ["alpha"]
    cache = payload.get("cache")
    assert isinstance(cache, dict)
    assert isinstance(cache.get("hits"), int)
    assert isinstance(cache.get("misses"), int)
    assert isinstance(cache.get("entries"), int)
    missing = payload["missing"]
    assert isinstance(missing, list)
    assert missing and missing[0]["prefab_id"] == "p_alpha_missing"


def test_doctor_assets_image_cache(tmp_path, monkeypatch, capsys) -> None:
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
            {
                "display_name": "Sheet Warn",
                "id": "p_sheet_warn",
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

    _patch_repo_paths(monkeypatch, tmp_path)

    code = mesh_main(["doctor-assets", "--pack", "alpha", "--json"])
    output = capsys.readouterr().out.strip()
    assert code == 0
    payload = json.loads(output)
    cache_stats = payload.get("cache")
    assert isinstance(cache_stats, dict)
    assert cache_stats.get("misses", 0) >= 1
    assert cache_stats.get("entries", 0) >= 1

    cache_path = tmp_path / ".mesh" / "cache" / "image_sizes.json"
    assert cache_path.exists()
    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert any(key.startswith("assets/sprites/sheet.png|") for key in cache_payload)

    code = mesh_main(["doctor-assets", "--pack", "alpha", "--json"])
    output = capsys.readouterr().out.strip()
    assert code == 0
    payload_again = json.loads(output)
    cache_stats_again = payload_again.get("cache")
    assert isinstance(cache_stats_again, dict)
    assert cache_stats_again.get("hits", 0) >= 1
    cache_payload_again = json.loads(cache_path.read_text(encoding="utf-8"))
    assert any(key.startswith("assets/sprites/sheet.png|") for key in cache_payload_again)


def test_doctor_assets_cache_corruption(tmp_path, monkeypatch, capsys) -> None:
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
            {
                "display_name": "Sheet Cache",
                "id": "p_sheet_cache",
                "tags": [
                    "test",
                ],
                "entity": {
                    "sprite_sheet": {
                        "image": "assets/sprites/sheet.png",
                        "frame_width": 1,
                        "frame_height": 1,
                    }
                },
            }
        ],
    )

    cache_path = tmp_path / ".mesh" / "cache" / "image_sizes.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{not json", encoding="utf-8")

    _patch_repo_paths(monkeypatch, tmp_path)

    code = mesh_main(["doctor-assets", "--pack", "alpha", "--json"])
    output = capsys.readouterr().out.strip()
    assert code == 0
    payload = json.loads(output)
    assert isinstance(payload.get("cache"), dict)
    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert isinstance(cache_payload, dict)
