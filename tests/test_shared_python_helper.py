"""tests._shared_python answers as a fresh interpreter would: a snippet whose watched modules are already loaded runs in
a fresh one; the arcade-less interpreter never had arcade; a failing snippet fails the test."""

from __future__ import annotations

import subprocess

import pytest

from tests._shared_python import run_python

pytestmark = pytest.mark.fast

_LOADED = "import sys; print('json.decoder' in sys.modules)"


def test_a_watched_module_already_loaded_gets_a_fresh_interpreter() -> None:
    run_python("import json.decoder")  # the shared interpreter now has it loaded
    assert run_python(_LOADED).strip() == "True", "unwatched: answered by the shared interpreter"
    assert run_python(_LOADED, watch=["json.decoder"]).strip() == "False", "watched: answered by a fresh one"


def test_without_arcade_means_arcade_cannot_be_imported() -> None:
    code = "try:\n    import arcade\n    print('imported')\nexcept ImportError:\n    print('unavailable')"
    assert run_python(code, without_arcade=True).strip() == "unavailable"
    assert run_python(code, watch=["arcade"], without_arcade=True).strip() == "unavailable"


def test_a_failing_snippet_fails() -> None:
    with pytest.raises(AssertionError, match="ZeroDivisionError"):
        run_python("1 / 0")
    run_python("import json.decoder")
    with pytest.raises(subprocess.CalledProcessError):
        run_python("import sys; 1 / 0", watch=["json.decoder"])
