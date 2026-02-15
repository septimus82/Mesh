from __future__ import annotations

from pathlib import Path

import pytest

from mesh_cli import verify as verify_mod

pytestmark = [pytest.mark.fast]


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_exception_budget_guard_passes_when_not_grown(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    for rel in verify_mod._EXCEPTION_BUDGET_FILES:
        _write_file(repo / rel, "try:\n    pass\nexcept Exception:\n    pass\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("3\n", encoding="utf-8")

    code, error, current, baseline_count, per_file = verify_mod._evaluate_exception_budget_guard(repo, baseline)

    assert code == 0
    assert error == ""
    assert current == 3
    assert baseline_count == 3
    assert sum(per_file.values()) == 3


def test_exception_budget_guard_fails_on_growth(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    for rel in verify_mod._EXCEPTION_BUDGET_FILES:
        _write_file(repo / rel, "try:\n    pass\nexcept Exception:\n    pass\n")
    _write_file(repo / verify_mod._EXCEPTION_BUDGET_FILES[0], "except Exception:\n    pass\nexcept Exception as exc:\n    pass\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("3\n", encoding="utf-8")

    code, error, current, baseline_count, _ = verify_mod._evaluate_exception_budget_guard(repo, baseline)

    assert code == 2
    assert "exception budget grew" in error
    assert "update baseline with: python -c" in error
    assert baseline_count == 3
    assert current == 4


def test_exception_budget_guard_ignores_comments_and_strings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = (
        "def fn():\n"
        "    text = 'except Exception: in string'\n"
        "    # except Exception: in comment\n"
        "    try:\n"
        "        pass\n"
        "    except Exception:\n"
        "        pass\n"
    )
    _write_file(repo / verify_mod._EXCEPTION_BUDGET_FILES[0], source)
    for rel in verify_mod._EXCEPTION_BUDGET_FILES[1:]:
        _write_file(repo / rel, "pass\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("1\n", encoding="utf-8")

    code, error, current, baseline_count, per_file = verify_mod._evaluate_exception_budget_guard(repo, baseline)

    assert code == 0
    assert error == ""
    assert baseline_count == 1
    assert current == 1
    assert per_file[verify_mod._EXCEPTION_BUDGET_FILES[0]] == 1


def test_exception_budget_count_deterministic_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    for index, rel in enumerate(verify_mod._EXCEPTION_BUDGET_FILES):
        _write_file(repo / rel, ("except Exception:\n    pass\n" * (index + 1)))

    total_a, per_file_a = verify_mod._count_exception_budget(repo, verify_mod._EXCEPTION_BUDGET_FILES)
    total_b, per_file_b = verify_mod._count_exception_budget(repo, verify_mod._EXCEPTION_BUDGET_FILES)

    assert total_a == total_b
    assert per_file_a == per_file_b
    assert list(per_file_a.keys()) == sorted(verify_mod._EXCEPTION_BUDGET_FILES)


def test_exception_budget_payload_schema_and_sorting() -> None:
    payload = verify_mod._build_exception_budget_payload(
        ok=True,
        current_count=7,
        baseline_count=6,
        files_scanned=["b.py", "a.py"],
        per_file_counts={"b.py": 3, "a.py": 4},
    )
    assert payload["schema_version"] == 1
    assert payload["ok"] is True
    assert payload["current_count"] == 7
    assert payload["baseline_count"] == 6
    assert payload["files_scanned"] == ["a.py", "b.py"]
    assert list(payload["per_file_counts"].keys()) == ["a.py", "b.py"]


def test_exception_budget_count_semantics_tuple_includes_exception_baseexception_excluded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = (
        "def fn():\n"
        "    try:\n"
        "        pass\n"
        "    except (Exception, ValueError):\n"
        "        pass\n"
        "    try:\n"
        "        pass\n"
        "    except (Exception,):\n"
        "        pass\n"
        "    try:\n"
        "        pass\n"
        "    except BaseException:\n"
        "        pass\n"
    )
    _write_file(repo / verify_mod._EXCEPTION_BUDGET_FILES[0], source)
    for rel in verify_mod._EXCEPTION_BUDGET_FILES[1:]:
        _write_file(repo / rel, "pass\n")

    total, per_file = verify_mod._count_exception_budget(repo, verify_mod._EXCEPTION_BUDGET_FILES)

    assert total == 2
    assert per_file[verify_mod._EXCEPTION_BUDGET_FILES[0]] == 2
