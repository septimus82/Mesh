from __future__ import annotations

from pathlib import Path


def test_input_module_facade_policy() -> None:
    path = Path("engine/editor_runtime/input.py")
    text = path.read_text(encoding="utf-8")
    non_empty = [line for line in text.splitlines() if line.strip()]

    # Ratchet: keep the facade thin.
    assert len(non_empty) <= 27

    # Input facade should not define functions.
    assert "def " not in text

    # Must re-export handle_input from the dispatcher.
    assert "editor_input_dispatch" in text
    assert "handle_input as handle_input" in text

    # Avoid reintroducing heavy routing logic in the facade.
    assert "editor_input_router" not in text
    assert "editor_input_legacy_handlers" not in text
