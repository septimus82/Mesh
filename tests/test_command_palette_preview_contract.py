from __future__ import annotations

import pytest

from engine.command_palette_preview import build_arg_preview
from engine.ui_overlays.command_palette import format_command_palette_overlay_lines

pytestmark = pytest.mark.fast


def test_build_arg_preview_align_success_normalizes_token() -> None:
    payload = build_arg_preview("selection.align", "left")
    assert payload == {"ok": True, "preview": "axis=x|mode=left|reference=primary", "error": None}


def test_build_arg_preview_distribute_success_normalizes_kv() -> None:
    payload = build_arg_preview("selection.distribute", "axis=y|mode=center|ref=primary")
    assert payload == {"ok": True, "preview": "axis=y|mode=center|reference=primary", "error": None}


def test_build_arg_preview_snap_invalid_error_is_stable() -> None:
    payload = build_arg_preview("selection.snap_to_grid", "snap_floor")
    assert payload["ok"] is False
    assert payload["preview"] is None
    assert payload["error"] == "invalid_step"


def test_build_arg_preview_unknown_command_is_noop_success() -> None:
    payload = build_arg_preview("selection.scatter", "n=10")
    assert payload == {"ok": True, "preview": None, "error": None}


def test_build_arg_preview_uses_registry_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.command_palette_registry as registry

    called = {"value": False}

    def _fake_parse(_arg: str | None) -> dict[str, object]:
        called["value"] = True
        return {"ok": True, "deg": 30.0, "about": "group"}

    monkeypatch.setattr(registry, "_parse_rotate_args", _fake_parse)
    payload = build_arg_preview("selection.rotate", "cw")
    assert called["value"] is True
    assert payload == {"ok": True, "preview": "deg=30|about=group", "error": None}


def test_overlay_lines_show_prompt_preview_and_error() -> None:
    payload_ok = {
        "enabled": True,
        "query": "sel",
        "dirty": False,
        "rev": 1,
        "armed": False,
        "undo": 0,
        "redo": 0,
        "active_mode": "none",
        "prompt_active": True,
        "prompt_kind": "text",
        "prompt_title": "Selection: Align…",
        "prompt_text": "left",
        "prompt_placeholder": "left / center / right",
        "prompt_preview": "axis=x|mode=left|reference=primary",
    }
    lines_ok = format_command_palette_overlay_lines(payload_ok)
    assert "arg preview: axis=x|mode=left|reference=primary" in lines_ok

    payload_err = dict(payload_ok)
    payload_err["prompt_preview"] = ""
    payload_err["prompt_error"] = "unknown_align_token: bogus"
    lines_err = format_command_palette_overlay_lines(payload_err)
    assert "arg error: unknown_align_token: bogus" in lines_err
