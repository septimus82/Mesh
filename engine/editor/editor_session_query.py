from __future__ import annotations

from typing import Any, cast

from engine.editor.editor_session_model import EditorSessionSnapshot


def get_session_snapshot(controller: Any) -> EditorSessionSnapshot:
    return cast(EditorSessionSnapshot, controller.session.get_snapshot())
