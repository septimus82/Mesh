from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_search_controller import EditorSearchController


class _SearchFlowStub(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(query="", is_open=False)

    def update_query(self, text: str) -> None:
        self.query = str(text or "")

    def move_selection(self, _delta: int) -> None:
        return None

    def commit_selection(self) -> bool:
        return False

    def toggle_palette(self) -> None:
        self.is_open = not bool(self.is_open)

    def close_palette(self, cancel_preview: bool = False) -> None:  # noqa: ARG002
        self.is_open = False

    def _refresh_results(self) -> None:
        return None

    def _build_items(self) -> list[object]:
        return []

    def _get_problems(self, _scene: object, _window: object) -> list[object]:
        return []


def attach_search_stub(editor: object) -> EditorSearchController:
    """Attach a real EditorSearchController with a minimal UI flow stub."""
    search = EditorSearchController(editor, _SearchFlowStub())
    setattr(editor, "search", search)
    return search
