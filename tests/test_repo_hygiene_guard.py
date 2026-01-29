import sys
from pathlib import Path

from tests.subprocess_tools import run_checked


def test_repo_hygiene_checker_exits_clean() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    result = run_checked(
        [sys.executable, "-m", "tools.check_repo_hygiene"],
        cwd=str(repo_root),
    )
    assert result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()
    text = (result.stdout + result.stderr)
    assert ("OK" in text) or ("WARN" in text)
