from __future__ import annotations

import pytest


@pytest.mark.fast
def test_tests_utils_imports_cleanly() -> None:
    import tests.utils  # noqa: F401
    from tests.utils import args_factory  # noqa: F401

    assert hasattr(args_factory, "make_doctor_args")
