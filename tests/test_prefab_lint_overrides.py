import argparse
import json
from pathlib import Path

import engine.tooling.prefab_cli as prefab_cli
from engine.prefabs import PrefabManager


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _prefab(prefab_id: str, sprite: str) -> dict[str, object]:
    return {
        "display_name": prefab_id,
        "entity": {"sprite": sprite},
        "id": prefab_id,
        "tags": ["test"],
    }


def _setup_prefabs(tmp_path: Path, monkeypatch) -> PrefabManager:
    assets_path = tmp_path / "assets" / "prefabs.json"
    alpha_path = tmp_path / "packs" / "alpha" / "data" / "prefabs.json"
    beta_path = tmp_path / "packs" / "beta" / "data" / "prefabs.json"

    _write_json(
        assets_path,
        [
            _prefab("p_tree", "base.png"),
        ],
    )
    _write_json(
        alpha_path,
        [
            _prefab("p_tree", "alpha.png"),
        ],
    )
    _write_json(
        beta_path,
        [
            _prefab("p_tree", "beta.png"),
        ],
    )

    def fake_resolve_path(path: str) -> Path:
        return tmp_path / path

    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])

    manager = PrefabManager()
    monkeypatch.setattr(prefab_cli, "get_prefab_manager", lambda: manager)
    return manager


def test_prefab_lint_overrides_reports_unexpected(tmp_path, monkeypatch, capsys) -> None:
    _setup_prefabs(tmp_path, monkeypatch)

    args = argparse.Namespace(json=False, allow=str(tmp_path / "nope.json"), strict=False)
    code = prefab_cli.handle_lint_overrides(args)
    out = capsys.readouterr().out

    assert code == 2
    assert "override id=p_tree" in out
    assert "packs/beta/data/prefabs.json" in out


def test_prefab_lint_overrides_allowlist_ok(tmp_path, monkeypatch, capsys) -> None:
    _setup_prefabs(tmp_path, monkeypatch)
    allow_path = tmp_path / ".mesh" / "prefab_overrides_allow.json"
    _write_json(
        allow_path,
        {"allow": [{"prefab_id": "p_tree", "winner": "packs/beta/data/prefabs.json"}]},
    )

    args = argparse.Namespace(json=True, allow=str(allow_path), strict=False)
    code = prefab_cli.handle_lint_overrides(args)
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["count"]["unexpected"] == 0
    assert payload["count"]["allowed"] == 1
    assert "\n" not in out.strip("\n")


def test_prefab_lint_overrides_allowlist_mismatch(tmp_path, monkeypatch, capsys) -> None:
    _setup_prefabs(tmp_path, monkeypatch)
    allow_path = tmp_path / ".mesh" / "prefab_overrides_allow.json"
    _write_json(
        allow_path,
        {"allow": [{"prefab_id": "p_tree", "winner": "packs/alpha/data/prefabs.json"}]},
    )

    args = argparse.Namespace(json=True, allow=str(allow_path), strict=False)
    code = prefab_cli.handle_lint_overrides(args)
    out = capsys.readouterr().out

    assert code == 2
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["count"]["unexpected"] == 1
