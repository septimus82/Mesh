from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


def test_cli_parser_registers_web_build_and_smoke_commands() -> None:
    from mesh_cli.main import create_parser

    parser = create_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"  # noqa: SLF001
    )
    choices = set(subparsers_action.choices.keys())
    assert "build-web" in choices
    assert "web-smoke" in choices
    build_parser = subparsers_action.choices["build-web"]
    option_strings = {opt for action in build_parser._actions for opt in action.option_strings}  # noqa: SLF001
    assert "--disable-sound-format-error" in option_strings


def test_web_smoke_checker_passes_for_canned_valid_directory(tmp_path: Path) -> None:
    from mesh_cli.web_smoke import run_web_smoke

    build_dir = tmp_path / "web_build"
    build_dir.mkdir(parents=True)
    (build_dir / "index.html").write_text(
        "<!doctype html><title>Mesh</title><script src='app.js'></script>",
        encoding="utf-8",
    )
    (build_dir / "app.js").write_text("console.log('mesh');", encoding="utf-8")
    artifact_path = tmp_path / "web_smoke.json"

    rc = run_web_smoke(build_dir=build_dir.as_posix(), artifact_path=artifact_path.as_posix())
    assert rc == 0

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["ok"] is True
    assert payload["selected_root"] == build_dir.as_posix()
    assert payload["outputs_present"] == {
        "data_bundle": False,
        "index_html": True,
        "js_bundle": True,
        "wasm_bundle": False,
    }
    assert payload["file_count"] == 2
    assert payload["files_sample"] == ["app.js", "index.html"]
    assert payload["diagnostics"] == []


def test_web_smoke_checker_fails_when_index_does_not_reference_existing_js(tmp_path: Path) -> None:
    from mesh_cli.web_smoke import run_web_smoke

    build_dir = tmp_path / "web_build_missing_js"
    build_dir.mkdir(parents=True)
    (build_dir / "index.html").write_text("<!doctype html><title>Mesh</title>", encoding="utf-8")
    (build_dir / "app.js").write_text("console.log('mesh');", encoding="utf-8")
    artifact_path = tmp_path / "web_smoke_missing.json"

    rc = run_web_smoke(build_dir=build_dir.as_posix(), artifact_path=artifact_path.as_posix())
    assert rc == 1

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["outputs_present"]["index_html"] is True
    assert payload["outputs_present"]["js_bundle"] is False
    codes = [str(item.get("code", "")) for item in payload["diagnostics"] if isinstance(item, dict)]
    assert "WEB_JS_BUNDLE_MISSING" in codes


def test_web_smoke_selects_nested_layout_deterministically(tmp_path: Path) -> None:
    from mesh_cli.web_smoke import run_web_smoke

    build_dir = tmp_path / "web_build_nested"
    nested_build = build_dir / "build"
    nested_dist = build_dir / "dist"
    nested_build.mkdir(parents=True)
    nested_dist.mkdir(parents=True)
    (nested_build / "index.html").write_text(
        "<!doctype html><title>Mesh</title><script src='bundle.js'></script>",
        encoding="utf-8",
    )
    (nested_build / "bundle.js").write_text("console.log('build');", encoding="utf-8")
    (nested_dist / "index.html").write_text(
        "<!doctype html><title>Mesh</title><script src='bundle.js'></script>",
        encoding="utf-8",
    )
    (nested_dist / "bundle.js").write_text("console.log('dist');", encoding="utf-8")
    artifact_path = tmp_path / "web_smoke_nested.json"

    rc = run_web_smoke(build_dir=build_dir.as_posix(), artifact_path=artifact_path.as_posix())
    assert rc == 0

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["selected_root"] == nested_build.as_posix()
    codes = [str(item.get("code", "")) for item in payload["diagnostics"] if isinstance(item, dict)]
    assert "WEB_BUILD_NESTED_DIR_DETECTED" in codes


def test_web_smoke_writes_failure_artifact_for_missing_build_dir(tmp_path: Path) -> None:
    from mesh_cli.web_smoke import run_web_smoke

    missing_dir = tmp_path / "does_not_exist"
    artifact_path = tmp_path / "web_smoke_missing_dir.json"
    rc = run_web_smoke(build_dir=missing_dir.as_posix(), artifact_path=artifact_path.as_posix())

    assert rc == 1
    assert artifact_path.is_file()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    codes = [str(item.get("code", "")) for item in payload["diagnostics"] if isinstance(item, dict)]
    assert "WEB_BUILD_DIR_MISSING" in codes


def test_build_web_wrapper_enables_disable_sound_format_error_by_default(monkeypatch) -> None:
    import tooling.build_web as build_web

    captured: dict[str, object] = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, *, capture_output, text):  # noqa: ANN001
        captured["cmd"] = list(cmd)
        assert capture_output is True
        assert text is True
        return _Result()

    monkeypatch.setattr(build_web.subprocess, "run", _fake_run)
    rc = build_web.main(["web_main.py"])
    assert rc == 0
    command = captured["cmd"]
    assert isinstance(command, list)
    assert "--disable-sound-format-error" in command


def test_build_web_wrapper_reports_tooling_failure_diagnostic_for_mp3_error(monkeypatch, capsys) -> None:
    import tooling.build_web as build_web

    class _Result:
        returncode = 1
        stdout = ""
        stderr = (
            "RuntimeError: Audio file '.venv/Lib/site-packages/arcade/resources/assets/music/1918.mp3' "
            "has a common unsupported format."
        )

    def _fake_run(cmd, *, capture_output, text):  # noqa: ANN001
        _ = (cmd, capture_output, text)
        return _Result()

    monkeypatch.setattr(build_web.subprocess, "run", _fake_run)
    rc = build_web.main(["web_main.py"])
    out = capsys.readouterr()

    assert rc == 1
    assert "WEB_BUILD_TOOLING_FAILED" in out.err
    assert "--disable-sound-format-error" in out.err
