from __future__ import annotations

import argparse

import pytest

pytestmark = [pytest.mark.fast]


def test_build_web_out_is_passed_through_to_tooling_wrapper(monkeypatch) -> None:
    from mesh_cli.misc import _handle_build_web

    captured: dict[str, object] = {}

    class _Result:
        returncode = 0

    def _fake_run(cmd):  # noqa: ANN001
        captured["cmd"] = list(cmd)
        return _Result()

    monkeypatch.setattr("mesh_cli.misc.subprocess.run", _fake_run)

    rc = _handle_build_web(
        argparse.Namespace(
            entrypoint="web_main.py",
            out="artifacts/web_build",
            extra_arg=[],
            disable_sound_format_error=True,
        )
    )

    assert rc == 0
    command = captured["cmd"]
    assert isinstance(command, list)
    assert command[1:4] == ["-m", "tooling.build_web", "web_main.py"]
    assert "--out-dir" in command
    out_index = command.index("--out-dir")
    assert command[out_index + 1] == "artifacts/web_build"
