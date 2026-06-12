import json
from pathlib import Path

import engine.console_runtime.handlers_ai as ai_handler_module
from engine.console_controller import ConsoleController


def test_ai_job_calls_ops_and_reload(monkeypatch, tmp_path: Path):
    job = {"operations": []}
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")

    called = {"apply": False, "reload": False}

    class DummyOps:
        def __init__(self, *_args, **_kwargs):
            pass

        def apply_job(self, payload):
            called["apply"] = payload is job
            return {"ok": True, "results": []}

    def fake_load_job(path):
        assert str(path) == str(job_path)
        return job

    monkeypatch.setattr(ai_handler_module, "AIOps", DummyOps)
    monkeypatch.setattr(ai_handler_module, "load_job", fake_load_job)

    class DummyWindow:
        def __init__(self):
            self.lines = []

        def reload_scene(self):
            called["reload"] = True

    window = DummyWindow()
    controller = ConsoleController(window)
    controller.execute_command(f"ai_job {job_path}")

    assert called["apply"] is True
    assert called["reload"] is True
    assert any("[AI] Applied" in line for line in controller.lines)
