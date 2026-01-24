from __future__ import annotations

from pathlib import Path
import tomllib

import pytest


@pytest.mark.fast
def test_pygbag_toml_contract() -> None:
    path = Path("pygbag.toml")
    assert path.exists()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = data.get("pygbag")
    assert isinstance(cfg, dict)

    include = cfg.get("include")
    exclude = cfg.get("exclude")
    output = cfg.get("output")

    assert isinstance(include, list)
    assert isinstance(exclude, list)
    assert isinstance(output, str)

    for required in ("packs/**", "assets/**", "config.json"):
        assert required in include
    for required in ("tests/**", "artifacts/**"):
        assert required in exclude
