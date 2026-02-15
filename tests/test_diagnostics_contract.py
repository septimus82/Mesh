from __future__ import annotations

import json
from pathlib import Path

from engine.diagnostics import (
    Diagnostic,
    DiagnosticLevel,
    diagnostics_to_json,
    diagnostics_to_text,
    sort_diagnostics,
)
from engine.log_utils import normalize_path


def test_sort_diagnostics_is_stable_and_deterministic() -> None:
    raw = (
        Diagnostic(DiagnosticLevel.INFO, "z.info", "zzz", {"b": 2, "a": 1}),
        Diagnostic(DiagnosticLevel.ERROR, "a.error", "boom", {"pointer": "$/x", "file": "b.json"}),
        Diagnostic(DiagnosticLevel.WARN, "m.warn", "watch", {"file": "a.json"}),
        Diagnostic(DiagnosticLevel.ERROR, "a.error", "boom", {"pointer": "$/a", "file": "a.json"}),
    )
    ordered = sort_diagnostics(raw)
    assert [item.level for item in ordered][:2] == [DiagnosticLevel.ERROR, DiagnosticLevel.ERROR]
    assert ordered[0].context["file"] == "a.json"
    assert ordered[1].context["file"] == "b.json"


def test_diagnostics_json_text_roundtrip_stable() -> None:
    diags = (
        Diagnostic(DiagnosticLevel.ERROR, "content.missing", "missing file", {"file": "assets/data/events.json"}),
        Diagnostic(DiagnosticLevel.WARN, "content.warn", "warn", {"pointer": "$/x"}, hint="check schema"),
    )
    payload = diagnostics_to_json(diags)
    parsed = json.loads(payload)
    rebuilt = tuple(Diagnostic.from_dict(item) for item in parsed)
    assert [item.to_dict() for item in rebuilt] == [item.to_dict() for item in sort_diagnostics(diags)]

    text = diagnostics_to_text(diags)
    assert "[error] content.missing:" in text
    assert "hint: check schema" in text


def test_normalize_path_strips_absolute_and_drive_components(tmp_path: Path) -> None:
    win_path = r"C:\Games\Mesh\assets\data\events.json"
    assert normalize_path(win_path).endswith("assets/data/events.json")

    abs_path = tmp_path / "folder" / "file.txt"
    assert "/" not in normalize_path(abs_path)[:1]

