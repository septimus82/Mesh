from __future__ import annotations

import json
import types

from engine.tooling import prefab_cli


def test_prefab_explain_json_includes_source_and_chain(monkeypatch, capsys) -> None:
    class _Manager:
        def __init__(self) -> None:
            self.prefabs = {"p_tree": {"id": "p_tree"}}
            self.prefab_sources = {"p_tree": "packs/beta/data/prefabs.json"}
            self.prefab_source_chain = {
                "p_tree": [
                    "assets/prefabs.json",
                    "packs/alpha/data/prefabs.json",
                    "packs/beta/data/prefabs.json",
                ]
            }

        def load(self, force: bool = False) -> None:
            return

        def get_prefab(self, prefab_id: str):
            return {"id": prefab_id, "entity": {"sprite": "beta.png"}}

    monkeypatch.setattr(prefab_cli, "get_prefab_manager", lambda: _Manager())

    args = types.SimpleNamespace(id="p_tree", json=True)
    code = prefab_cli.handle_explain(args)
    assert code == 0

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["ok"] is True
    assert payload["source"] == "packs/beta/data/prefabs.json"
    assert payload["chain"] == [
        "assets/prefabs.json",
        "packs/alpha/data/prefabs.json",
        "packs/beta/data/prefabs.json",
    ]
    assert isinstance(payload["prefab"], dict)
