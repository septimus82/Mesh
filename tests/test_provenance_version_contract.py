from __future__ import annotations

import json
import re

import engine.provenance as provenance_mod
from mesh_cli.version_info import get_tool_version


def test_provenance_uses_canonical_tool_version(monkeypatch) -> None:
    monkeypatch.setattr(provenance_mod, "_git_commit", lambda: None)
    monkeypatch.setattr(provenance_mod, "_git_dirty", lambda: None)
    monkeypatch.setattr(provenance_mod, "_git_describe", lambda: None)

    canonical = get_tool_version()
    prov = provenance_mod.get_provenance(deterministic=True)
    payload = provenance_mod.provenance_to_dict(prov)
    text = provenance_mod.format_provenance_text(prov)

    assert payload["tool_version"] == canonical
    assert canonical in text

    combined = json.dumps(payload, sort_keys=True) + "\n" + text
    assert "0.1.0" not in combined

    zero_major_versions = sorted(set(re.findall(r"\b0\.\d+\.\d+\b", combined)))
    assert zero_major_versions == [canonical], (
        "stale zero-major tool version detected in provenance output: "
        f"{zero_major_versions} (expected only {canonical})"
    )
