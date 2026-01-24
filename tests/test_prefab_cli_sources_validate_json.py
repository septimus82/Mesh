from __future__ import annotations

import json
from pathlib import Path

from mesh_cli.main import main as mesh_main


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_prefab_sources_and_validate_all_json(tmp_path, monkeypatch, capsys) -> None:
    assets_path = tmp_path / "assets" / "prefabs.json"
    alpha_path = tmp_path / "packs" / "alpha" / "data" / "prefabs.json"
    beta_path = tmp_path / "packs" / "beta" / "data" / "prefabs.json"

    _write_json(assets_path, [{"id": "p_tree", "entity": {}}])
    _write_json(alpha_path, [{"id": "p_alpha", "entity": {}}])
    beta_path.parent.mkdir(parents=True, exist_ok=True)
    beta_path.write_text("{", encoding="utf-8")

    def fake_resolve_path(path: str) -> Path:
        return tmp_path / path

    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])
    monkeypatch.setattr("engine.validators.prefab_validator.resolve_path", fake_resolve_path)

    assert mesh_main(["prefab", "sources", "--json"]) == 0
    sources_out = capsys.readouterr().out.strip()
    sources_lines = sources_out.splitlines()
    assert len(sources_lines) == 1
    sources_payload = json.loads(sources_lines[0])
    assert sources_payload["cmd"] == "prefab_sources"
    assert sources_payload["ok"] is True
    assert sources_payload["sources"] == [
        str(assets_path),
        str(alpha_path),
        str(beta_path),
    ]

    assert mesh_main(["prefab", "validate-all", "--json"]) == 1
    validate_out = capsys.readouterr().out.strip()
    validate_lines = validate_out.splitlines()
    assert len(validate_lines) == 1
    validate_payload = json.loads(validate_lines[0])
    assert validate_payload["cmd"] == "prefab_validate_all"
    assert validate_payload["ok"] is False

    results = validate_payload["results"]
    by_file = {entry["file"]: entry for entry in results}
    assert by_file[str(assets_path)]["ok"] is True
    assert by_file[str(alpha_path)]["ok"] is True
    assert by_file[str(beta_path)]["ok"] is False
    assert by_file[str(beta_path)]["error"]
