from __future__ import annotations

import pytest

from engine import config

pytestmark = [pytest.mark.fast]


def test_coerce_type_sampled_logging_logs_first_and_later_failures(monkeypatch, caplog) -> None:
    class ExplodingType:
        __name__ = "ExplodingType"

        def __new__(cls, _value):
            raise RuntimeError("boom")

    calls = iter([True, False, True])
    monkeypatch.setattr(config, "should_log", lambda _site: next(calls))
    logged: list[str] = []

    def _capture(message: str, *args, **kwargs) -> None:
        logged.append(message % args)

    monkeypatch.setattr(config._log, "error", _capture)

    value = {"demo": True}
    first = config._coerce_type(value, ExplodingType)
    second = config._coerce_type(value, ExplodingType)
    third = config._coerce_type(value, ExplodingType)

    assert first is value
    assert second is value
    assert third is value

    assert len(logged) == 2
    assert all("[Mesh][Config] ERROR coercing config value" in message for message in logged)
    assert all("target_type=ExplodingType" in message for message in logged)


def test_coerce_type_still_returns_original_on_failure(monkeypatch) -> None:
    class ExplodingType:
        def __new__(cls, _value):
            raise RuntimeError("boom")

    monkeypatch.setattr(config, "should_log", lambda _site: True)

    original = {"keep": "original"}
    assert config._coerce_type(original, ExplodingType) is original