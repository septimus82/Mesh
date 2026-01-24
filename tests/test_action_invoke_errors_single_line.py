from __future__ import annotations

from engine.action_runtime import invoke


def test_unknown_action_error_is_single_line_and_deterministic() -> None:
    ok, err = invoke.invoke("nope", object(), actions={}, catch_exceptions=True)
    assert ok is False
    assert "\n" not in err
    assert err == "Unknown action 'nope'"


def test_exception_error_is_single_line_and_deterministic() -> None:
    def boom(_window: object) -> None:
        raise ValueError("bad\nthings\r\nhappen")

    ok, err = invoke.invoke("boom", object(), actions={"boom": boom}, catch_exceptions=True)
    assert ok is False
    assert "\n" not in err
    assert err == "ValueError: bad things happen"

