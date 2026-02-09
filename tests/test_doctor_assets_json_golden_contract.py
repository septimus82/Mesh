from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

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


def _normalize_paths(value: Any, tmp_path: Path) -> Any:
    if isinstance(value, str):
        cooked = value.replace("\\", "/")
        tmp_norm = tmp_path.as_posix()
        if tmp_norm:
            cooked = cooked.replace(tmp_norm, "<TMP>")
        return cooked
    if isinstance(value, list):
        return [_normalize_paths(item, tmp_path) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_paths(val, tmp_path) for key, val in value.items()}
    return value


def _prune_payload(payload: dict[str, Any]) -> dict[str, Any]:
    missing = payload.get("missing", [])
    warnings = payload.get("warnings", [])
    pruned_missing = []
    for entry in missing if isinstance(missing, list) else []:
        if isinstance(entry, dict):
            pruned_missing.append(
                {
                    "prefab_id": entry.get("prefab_id"),
                    "field": entry.get("field"),
                    "path": entry.get("path"),
                    "source": entry.get("source"),
                }
            )
    pruned_warnings = []
    for entry in warnings if isinstance(warnings, list) else []:
        if isinstance(entry, dict):
            pruned_warnings.append(
                {
                    "prefab_id": entry.get("prefab_id"),
                    "field": entry.get("field"),
                    "path": entry.get("path"),
                    "warning": entry.get("warning"),
                    "source": entry.get("source"),
                }
            )
    return {
        "cmd": payload.get("cmd"),
        "ok": payload.get("ok"),
        "missing": pruned_missing,
        "warnings": pruned_warnings,
    }


def test_doctor_assets_json_golden_output(tmp_path: Path, monkeypatch, capsys) -> None:
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

    code = mesh_main(["doctor-assets", "--json"])
    output = capsys.readouterr().out.strip()
    assert code == 2
    payload = json.loads(output)
    normalized = _normalize_paths(payload, tmp_path)
    pruned = _prune_payload(normalized)

    expected = {
        "cmd": "doctor_assets",
        "ok": False,
        "missing": [
            {
                "prefab_id": "p_missing",
                "field": "entity.sprite",
                "path": "assets/sprites/missing.png",
                "source": "packs/alpha/data/prefabs.json",
            }
        ],
        "warnings": [
            {
                "prefab_id": "p_warn",
                "field": "entity.sprite_sheet",
                "path": "assets/sprites/sheet.png",
                "warning": "image size not divisible by frame size (1x1 % 2x2)",
                "source": "packs/alpha/data/prefabs.json",
            }
        ],
    }

    assert pruned == expected
    assert isinstance(payload.get("missing"), list)
    assert isinstance(payload.get("warnings"), list)
