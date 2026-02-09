"""Policy tests for workspace IO orchestration."""

from __future__ import annotations

from pathlib import Path


def test_editor_controller_has_no_workspace_io() -> None:
    text = Path("engine/editor_controller.py").read_text(encoding="utf-8")
    # Allow TYPE_CHECKING imports for type hints
    import re
    # Remove TYPE_CHECKING blocks for policy check
    text_without_type_checking = re.sub(
        r'if TYPE_CHECKING:.*?(?=\n\S|\Z)', '', text, flags=re.DOTALL
    )
    # Forbidden tokens for workspace settings IO
    # Note: write_json_atomic is allowed for prefab IO but not workspace settings
    forbidden = (
        "from engine.workspace_settings",
        "import engine.workspace_settings",
        "runtime_settings_storage",
        "engine.projects",
        "projects.json",
        "user_settings.json",
        "json.dump(",  # Use with parenthesis to be more specific
    )
    for token in forbidden:
        assert token not in text_without_type_checking, f"Found forbidden token: {token}"
