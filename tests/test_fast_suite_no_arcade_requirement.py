from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.mark.fast
def test_fast_suite_does_not_require_arcade() -> None:
    from tests import test_no_arcade_static_imports_policy as no_arcade_policy
    from tests import test_pytest_fast_headless_contract as headless_contract

    with tempfile.TemporaryDirectory() as tmpdir:
        headless_contract.test_pytest_fast_headless_contract(Path(tmpdir))
    no_arcade_policy.test_no_arcade_imports()
