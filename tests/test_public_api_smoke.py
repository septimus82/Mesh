from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


def test_public_api_smoke_import_has_expected_symbols() -> None:
    import engine.public_api as public_api

    for name in (
        "EntityId",
        "ScenePath",
        "Vec2",
        "get_project_root",
        "resolve_asset_path",
        "load_scene_payload",
        "run_game",
    ):
        assert hasattr(public_api, name), f"missing public API symbol: {name}"

