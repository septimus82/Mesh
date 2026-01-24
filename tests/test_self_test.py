import pytest

from engine.self_test import SelfTestManager


pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_selftest_behaviour_pass(monkeypatch):
    class GoodBehaviour:
        def __init__(self, entity, window, **config):
            self.entity = entity
            self.window = window

        def update(self, dt):
            self.entity.center_x += 1

    mgr = SelfTestManager(window=None, behaviour_registry={"Good": GoodBehaviour})
    monkeypatch.setattr(mgr, "_test_scenes", lambda: [])
    monkeypatch.setattr(mgr, "_test_worlds", lambda: [])
    monkeypatch.setattr(mgr, "_test_cutscenes", lambda: [])

    results = mgr.run_all()
    assert any(r.name == "behaviour:Good" and r.ok for r in results)
    summary = mgr.summary(results)
    assert "[SelfTest] 1/1 checks passed." in summary
    assert "warnings=" in summary


def test_selftest_reports_failure(monkeypatch):
    class FailingBehaviour:
        def __init__(self, entity, window, **config):
            pass

        def update(self, dt):
            raise RuntimeError("boom")

    mgr = SelfTestManager(window=None, behaviour_registry={"Fail": FailingBehaviour})
    monkeypatch.setattr(mgr, "_test_scenes", lambda: [])
    monkeypatch.setattr(mgr, "_test_worlds", lambda: [])
    monkeypatch.setattr(mgr, "_test_cutscenes", lambda: [])

    results = mgr.run_all()
    assert any(not r.ok for r in results)
    summary = mgr.summary(results)
    assert "Fail" in summary
    assert "boom" in summary
    assert "warnings=" in summary
