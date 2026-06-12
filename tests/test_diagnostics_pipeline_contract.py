from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_config_split_preset_failure_records_structured_diagnostic(tmp_path: Path) -> None:
    from engine.config import load_config
    from engine.diagnostics import clear_diagnostics, get_diagnostics_payload

    cfg_path = tmp_path / "config.json"
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir(parents=True, exist_ok=True)
    # Deliberately invalid split preset JSON to force inline fallback path.
    (presets_dir / "broken_preset.json").write_text("{", encoding="utf-8")
    cfg_path.write_text(
        json.dumps(
            {
                "presets": {"inline_demo": {"start_scene": "scenes/runtime_smoke_scene.json"}},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    clear_diagnostics()
    cfg = load_config(str(cfg_path))
    payload_a = get_diagnostics_payload()
    payload_b = get_diagnostics_payload()

    assert getattr(cfg, "_presets_source", "") == "config_inline"
    assert payload_a == payload_b
    assert isinstance(payload_a, list)
    codes = [str(item.get("code", "")) for item in payload_a if isinstance(item, dict)]
    assert "config.presets.split_load_failed" in codes
    assert "config.presets.fallback_inline" in codes
    assert codes.index("config.presets.split_load_failed") < codes.index("config.presets.fallback_inline")

    # Shape ratchet: each diagnostic keeps deterministic structured keys.
    for entry in payload_a:
        assert isinstance(entry, dict)
        assert {"severity", "code", "message", "source"} <= set(entry.keys())
