from __future__ import annotations

import pytest

from engine.ui_toasts import ToastManager


@pytest.mark.fast
def test_toast_push_and_ordering() -> None:
    mgr = ToastManager()
    mgr.push_toast("First", ttl_s=1.0)
    mgr.push_toast("Second", ttl_s=1.0)
    assert mgr.get_active_toasts() == ["First", "Second"]


@pytest.mark.fast
def test_toast_expires_after_ttl() -> None:
    mgr = ToastManager()
    mgr.push_toast("Short", ttl_s=0.2)
    mgr.tick(0.19)
    assert mgr.get_active_toasts() == ["Short"]
    mgr.tick(0.02)
    assert mgr.get_active_toasts() == []


@pytest.mark.fast
def test_toast_fade_factor_is_deterministic() -> None:
    mgr = ToastManager()
    mgr.push_toast("Fade", ttl_s=1.0)
    mgr.tick(0.6)
    entries = mgr.get_active_entries()
    assert len(entries) == 1
    _, alpha = entries[0]
    assert alpha == pytest.approx(0.8)
