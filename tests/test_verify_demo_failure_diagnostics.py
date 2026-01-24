from __future__ import annotations

from types import SimpleNamespace

import engine.tooling_runtime.verify_demo as verify_demo


def test_verify_demo_failure_writes_log(tmp_path, monkeypatch) -> None:
    def fake_run(_cmd, capture_output=False):  # noqa: ARG001
        return SimpleNamespace(
            returncode=2,
            stdout=b"pytest stdout line\n",
            stderr=b"pytest stderr line\n",
        )

    monkeypatch.setattr(verify_demo, "iter_missing_paths", lambda _paths: [])
    monkeypatch.setattr(verify_demo.subprocess, "run", fake_run)

    log_path = tmp_path / "verify_demo.log"
    code = verify_demo.run_verify_demo(capture_output=True, quiet=True, log_path=log_path)

    assert code == 2
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "pytest stdout line" in content
    assert "pytest stderr line" in content
