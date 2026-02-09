from __future__ import annotations

from pathlib import Path

from tooling.repo_hygiene_policy import scan_repo_hygiene, format_hygiene_failure


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_repo_hygiene_policy_flags_forbidden_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    _touch(root / "dist" / "bundle.txt")
    _touch(root / "engine" / "__pycache__" / "mod.pyc")
    _touch(root / "seb" / "notes.txt")
    _touch(root / "tests" / "fixtures" / "__pycache__" / "ok.pyc")

    result = scan_repo_hygiene(root)
    offenders = list(result.offenders)

    assert "dist" in offenders
    assert "engine/__pycache__" in offenders
    assert "seb" in offenders
    assert "tests/fixtures/__pycache__" not in offenders

    message = format_hygiene_failure(offenders)
    assert "dist" in message
    assert "engine/__pycache__" in message
    assert "Hint:" in message


def test_repo_hygiene_policy_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    _touch(root / ".venv" / "pyvenv.cfg")
    _touch(root / "build" / "output.bin")

    first = scan_repo_hygiene(root).offenders
    second = scan_repo_hygiene(root).offenders
    assert first == second
