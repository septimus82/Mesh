from __future__ import annotations

from tooling.pytest_fast import parse_durations_output


def test_parse_durations_output() -> None:
    sample = """
============================= test session starts =============================
platform win32 -- Python 3.13.1, pytest-8.2.0
============================= slowest 25 durations =============================
1.23s call     tests/test_alpha.py::test_one
0.50s setup    tests/test_beta.py::test_two
0.01s call     tests/test_alpha.py::test_three

============================== 3 passed in 2.00s ===============================
"""
    result = parse_durations_output(sample)
    assert result == [
        {"nodeid": "tests/test_alpha.py::test_one", "seconds": 1.23},
        {"nodeid": "tests/test_beta.py::test_two", "seconds": 0.5},
        {"nodeid": "tests/test_alpha.py::test_three", "seconds": 0.01},
    ]
