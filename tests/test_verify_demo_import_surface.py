import importlib
import subprocess
import sys


def test_verify_demo_import_has_no_side_effects(monkeypatch, capsys) -> None:
    # Make sure we execute the import body.
    sys.modules.pop("engine.tooling_runtime.verify_demo", None)
    sys.modules.pop("engine.tooling.verify_demo", None)

    def _boom(*_a, **_k):
        raise AssertionError("subprocess.run should not be called at import time")

    monkeypatch.setattr(subprocess, "run", _boom)

    importlib.import_module("engine.tooling_runtime.verify_demo")
    importlib.import_module("engine.tooling.verify_demo")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
