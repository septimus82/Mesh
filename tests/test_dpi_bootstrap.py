from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.fast


def test_set_process_dpi_unaware_imports_and_noops_without_raising() -> None:
    from engine.dpi_bootstrap import set_process_dpi_unaware

    set_process_dpi_unaware()
    set_process_dpi_unaware()


def test_set_process_dpi_unaware_skips_win32_apis_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import dpi_bootstrap

    monkeypatch.setattr(dpi_bootstrap, "_applied", False)
    monkeypatch.setattr(sys, "platform", "linux")

    dpi_bootstrap.set_process_dpi_unaware()

    monkeypatch.setattr(dpi_bootstrap, "_applied", False)
