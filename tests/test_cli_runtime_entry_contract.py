from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.subprocess_tools import run_checked


pytestmark = [pytest.mark.fast]


def test_cli_parser_registers_play_runtime_subcommand() -> None:
    from mesh_cli.main import create_parser

    parser = create_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"  # noqa: SLF001
    )
    choices = set(subparsers_action.choices.keys())
    assert "play-runtime" in choices


def test_cli_parser_play_runtime_registers_diagnostics_flags() -> None:
    from mesh_cli.main import create_parser

    parser = create_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"  # noqa: SLF001
    )
    play_runtime_parser = subparsers_action.choices["play-runtime"]
    option_strings = {opt for action in play_runtime_parser._actions for opt in action.option_strings}  # noqa: SLF001
    assert "--diagnostics-artifact" in option_strings
    assert "--print-diagnostics-on-exit" in option_strings


def test_play_runtime_main_fast_path_does_not_import_editor_modules() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import json
import sys

from engine.runtime_only import is_forbidden_editor_import
from mesh_cli.main import main

before = set(sys.modules)
rc = int(main(["play-runtime"]))
after = set(sys.modules)

offenders = sorted(
    name
    for name in (after - before)
    if is_forbidden_editor_import(name)
)
print(
    json.dumps(
        {
            "offenders": offenders,
            "rc": rc,
        },
        sort_keys=True,
    )
)
"""
    result = run_checked([sys.executable, "-c", script], cwd=str(repo_root))
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    assert payload["rc"] == 0
    assert payload["offenders"] == []


def test_play_runtime_headless_smoke_main_fast_path_is_clean_and_writes_artifact(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    artifact = (tmp_path / "runtime_smoke.json").as_posix()
    script = """
import json
import sys

from engine.runtime_only import is_forbidden_editor_import
from mesh_cli.main import main

artifact_path = sys.argv[1]
before = set(sys.modules)
rc = int(main(["play-runtime", "--headless-smoke", "--smoke-artifact", artifact_path]))
after = set(sys.modules)

offenders = sorted(
    name
    for name in (after - before)
    if is_forbidden_editor_import(name)
)
print(
    json.dumps(
        {
            "offenders": offenders,
            "rc": rc,
        },
        sort_keys=True,
    )
)
"""
    result = run_checked([sys.executable, "-c", script, artifact], cwd=str(repo_root))
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    assert payload["rc"] == 0
    assert payload["offenders"] == []

    smoke_payload = json.loads(Path(artifact).read_text(encoding="utf-8"))
    assert smoke_payload["ok"] is True
    assert smoke_payload["ticks"] == 3
    assert smoke_payload["forbidden_imports_found"] == []
    assert "diagnostics" in smoke_payload
    assert isinstance(smoke_payload["diagnostics"], list)
    for entry in smoke_payload["diagnostics"]:
        assert isinstance(entry, dict)
        assert {"severity", "code", "message", "source"} <= set(entry.keys())


def test_play_runtime_handler_points_to_runtime_only_entry() -> None:
    source = Path("mesh_cli/misc.py").read_text(encoding="utf-8")
    assert "from engine.runtime_only import run_runtime_scene" in source


def test_play_runtime_help_includes_print_diagnostics_flag() -> None:
    from mesh_cli.runtime_only_cli import build_play_runtime_parser

    help_text = build_play_runtime_parser().format_help()
    assert "--diagnostics-artifact" in help_text
    assert "--print-diagnostics-on-exit" in help_text


def test_play_runtime_headless_smoke_writes_diagnostics_artifact_with_stable_schema(tmp_path: Path) -> None:
    from engine.runtime_only import run_runtime_scene

    smoke_a = tmp_path / "runtime_smoke_a.json"
    smoke_b = tmp_path / "runtime_smoke_b.json"
    diag_a = tmp_path / "diagnostics_a.json"
    diag_b = tmp_path / "diagnostics_b.json"

    rc_a = run_runtime_scene(
        headless_smoke=True,
        smoke_artifact=smoke_a.as_posix(),
        diagnostics_artifact=diag_a.as_posix(),
        quiet=True,
    )
    assert rc_a in (0, 1)

    rc_b = run_runtime_scene(
        headless_smoke=True,
        smoke_artifact=smoke_b.as_posix(),
        diagnostics_artifact=diag_b.as_posix(),
        quiet=True,
    )
    assert rc_b in (0, 1)

    payload_a = json.loads(diag_a.read_text(encoding="utf-8"))
    payload_b = json.loads(diag_b.read_text(encoding="utf-8"))
    assert payload_a["schema_version"] == 1
    assert isinstance(payload_a["ok"], bool)
    assert set(payload_a["counts"].keys()) == {"errors", "warnings", "info"}
    assert all(isinstance(payload_a["counts"][key], int) for key in ("errors", "warnings", "info"))
    assert isinstance(payload_a["diagnostics"], list)
    assert payload_a["context"]["mode"] == "headless_smoke"
    assert "scene_loaded" in payload_a["context"]
    assert "scene_requested" in payload_a["context"]
    assert payload_a["diagnostics"] == payload_b["diagnostics"]
    assert payload_a["counts"] == payload_b["counts"]
    assert payload_a["context"] == payload_b["context"]


def test_play_runtime_headless_smoke_projects_save_runtime_diagnostics_deterministically(tmp_path: Path) -> None:
    from engine.diagnostics import Diagnostic, DiagnosticLevel
    from engine.runtime_only import run_runtime_scene
    from engine.save_runtime import io as save_io
    from engine.save_runtime.save_diagnostics import SaveDiagnosticsAggregator

    def _record_failed_load_attempt() -> None:
        aggregator = SaveDiagnosticsAggregator()
        aggregator.add(
            (
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="LOAD_PARSE_FAILED",
                    message="forced save-load failure for smoke contract",
                    source="engine.savegame",
                    context={"pointer": "$"},
                    hint="create a fresh save file",
                ),
            )
        )
        save_io.record_load_attempt(
            kind="slot",
            path=Path("saves/slot_for_smoke.json"),
            ok=False,
            aggregator=aggregator,
        )

    artifact_a = tmp_path / "runtime_smoke_a.json"
    artifact_b = tmp_path / "runtime_smoke_b.json"

    _record_failed_load_attempt()
    rc_a = run_runtime_scene(headless_smoke=True, smoke_artifact=artifact_a.as_posix(), quiet=True)
    assert rc_a in (0, 1)
    payload_a = json.loads(artifact_a.read_text(encoding="utf-8"))

    _record_failed_load_attempt()
    rc_b = run_runtime_scene(headless_smoke=True, smoke_artifact=artifact_b.as_posix(), quiet=True)
    assert rc_b in (0, 1)
    payload_b = json.loads(artifact_b.read_text(encoding="utf-8"))

    assert payload_a["diagnostics"] == payload_b["diagnostics"]
    codes = [str(item.get("code", "")) for item in payload_a["diagnostics"] if isinstance(item, dict)]
    assert "LOAD_PARSE_FAILED" in codes


def test_play_runtime_print_diagnostics_on_exit_output_is_stable() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import sys
from mesh_cli.main import main

rc = int(main([\"play-runtime\", \"--headless-smoke\", \"--print-diagnostics-on-exit\"]))
print(f\"RC={rc}\")
"""
    result = run_checked([sys.executable, "-c", script], cwd=str(repo_root))
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stdout or ""
    assert "DIAGNOSTICS: E:" in out
