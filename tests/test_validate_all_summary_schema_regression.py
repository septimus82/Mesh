from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from engine.tooling.validate_all import UnifiedValidator


@dataclass
class _SceneReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def test_validate_all_summary_and_error_order_regression(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    # Ensure resolve_path() doesn't print "no config" noise.
    (tmp_path / "config.json").write_text(json.dumps({"content_roots": ["."], "world_file": None}, indent=2), encoding="utf-8")

    (tmp_path / "scenes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "worlds").mkdir(parents=True, exist_ok=True)

    (tmp_path / "scenes" / "ok.json").write_text(json.dumps({"entities": []}, indent=2), encoding="utf-8")
    (tmp_path / "scenes" / "bad.json").write_text(
        json.dumps({"entities": [{"x": 0, "y": "bad"}]}, indent=2),
        encoding="utf-8",
    )

    world_path = tmp_path / "worlds" / "world.json"
    world_path.write_text(
        json.dumps(
            {
                "scenes": {
                    "bad": {"path": "scenes/bad.json"},
                    "missing": {"path": "scenes/missing.json"},
                    "ok": {"path": "scenes/ok.json"},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    validator = UnifiedValidator(
        tmp_path,
        check_events=False,
        check_prefabs=False,
        strict=False,
        schema_strict=False,
    )

    # Keep scene loader checks from pulling in real content dependencies.
    monkeypatch.setattr(
        validator.scene_loader,
        "validate_scene_file",
        lambda *_a, **_k: _SceneReport(),
    )

    # Keep transition validation from adding extra findings.
    monkeypatch.setattr(
        validator.transition_validator,
        "validate",
        lambda *_a, **_k: True,
    )
    validator.transition_validator.errors = []
    validator.transition_validator.warnings = []

    assert validator.validate_path(Path(world_path)) is False
    rc = validator.print_report()
    assert rc == 1

    out = capsys.readouterr().out
    json_lines = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    assert json_lines, "Expected JSON lines from validate-all report"

    summary = json_lines[-1]
    assert summary == {"errors": 3, "ok": False, "warnings": 0}

    error_codes = [obj["code"] for obj in json_lines[:-1]]
    assert error_codes == ["entity.position.required", "world.scene_file.missing", "validate_all.legacy"]
