from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


def test_public_api_version_constants_exist() -> None:
    import engine.public_api as public_api

    assert isinstance(public_api.PUBLIC_API_VERSION, str)
    assert isinstance(public_api.PUBLIC_API_SEMVER, str)
    assert public_api.PUBLIC_API_VERSION
    assert public_api.PUBLIC_API_SEMVER

