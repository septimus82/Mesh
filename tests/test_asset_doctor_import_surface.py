import importlib
import pathlib
import sys


def _fresh_import(name: str):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_asset_doctor_imports_have_no_stdout_and_no_fs_walk(monkeypatch, capsys) -> None:
    # Guard against import-time filesystem discovery (glob/rglob/read_text/read_bytes).
    def _boom(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("unexpected filesystem access during import")

    monkeypatch.setattr(pathlib.Path, "glob", _boom, raising=True)
    monkeypatch.setattr(pathlib.Path, "rglob", _boom, raising=True)
    monkeypatch.setattr(pathlib.Path, "read_text", _boom, raising=True)
    monkeypatch.setattr(pathlib.Path, "read_bytes", _boom, raising=True)

    _fresh_import("engine.tooling.asset_doctor")
    _fresh_import("engine.tooling_runtime.asset_doctor")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
