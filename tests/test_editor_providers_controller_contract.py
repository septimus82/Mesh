from __future__ import annotations

from typing import Any, Dict

from engine.editor.editor_providers_controller import EditorProvidersController


class _FakeExplorer:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = dict(payload)

    def set_payload(self, payload: Dict[str, Any]) -> None:
        self._payload = dict(payload)

    def get_provider_payload(self, viewport_h: int, row_h: float, overscan: int = 5) -> dict[str, Any]:
        return dict(self._payload)

    def get_context_menu_payload(self) -> dict[str, Any]:
        return {"open": False, "items": [], "index": None}


class _FakeProblems:
    def __init__(self, payload: Dict[str, Any], issues: list[Any] | None = None) -> None:
        self._payload = dict(payload)
        self.issues = list(issues or [])

    def set_payload(self, payload: Dict[str, Any]) -> None:
        self._payload = dict(payload)

    def get_provider_payload(
        self,
        viewport_height: int,
        row_height: float,
        overscan: int = 5,
    ) -> dict[str, Any]:
        return dict(self._payload)


class _FakeEditor:
    def __init__(self, explorer: _FakeExplorer, problems: _FakeProblems) -> None:
        self.project_explorer = explorer
        self.problems = problems


def test_provider_payload_determinism_for_same_inputs() -> None:
    explorer = _FakeExplorer({"rows": [1, 2], "search_query": "x"})
    problems = _FakeProblems({"issues": [1]}, issues=[{"id": "a"}])
    editor = _FakeEditor(explorer, problems)
    providers = EditorProvidersController(editor)

    payload_a = providers.get_project_explorer_payload(720, 18.0, 5)
    payload_b = providers.get_project_explorer_payload(720, 18.0, 5)
    assert payload_a == payload_b

    problems_a = providers.get_problems_panel_payload(720, 18.0, 5)
    problems_b = providers.get_problems_panel_payload(720, 18.0, 5)
    assert problems_a == problems_b


def test_provider_cache_does_not_leak_between_calls() -> None:
    explorer = _FakeExplorer({"rows": [1], "search_query": ""})
    problems = _FakeProblems({"issues": []})
    editor = _FakeEditor(explorer, problems)
    providers = EditorProvidersController(editor)

    first = providers.get_project_explorer_payload(720, 18.0, 5)
    explorer.set_payload({"rows": [1, 2, 3], "search_query": "q"})
    second = providers.get_project_explorer_payload(720, 18.0, 5)
    assert first != second

    explorer.set_payload({"rows": [1], "search_query": ""})
    third = providers.get_project_explorer_payload(720, 18.0, 5)
    assert first == third

    problems.issues = [{"id": "x"}]
    palette = providers.get_palette_problems({"scene": "ok"}, object())
    assert palette == [{"id": "x"}]
