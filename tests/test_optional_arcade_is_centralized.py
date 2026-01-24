from __future__ import annotations

from pathlib import Path


def _has_try_import_arcade(text: str) -> bool:
    in_try = False
    saw_import = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("try:"):
            in_try = True
            saw_import = False
            continue
        if in_try:
            if "import arcade" in line or line.startswith("from arcade"):
                saw_import = True
            if line.startswith("except"):
                if saw_import:
                    return True
                in_try = False
    return False


def test_optional_arcade_is_only_try_import_location() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    engine_root = repo_root / "engine"
    offenders: list[str] = []
    # Files allowed to use try/except arcade inside TYPE_CHECKING for mypy resilience
    allowed_exceptions = {
        "particles.py",
        "ui.py",
        "persistence.py",
        "__init__.py", # engine/lighting/__init__.py
    }

    for path in engine_root.rglob("*.py"):
        if path.name == "optional_arcade.py":
            continue
        if path.name in allowed_exceptions:
            continue
            
        text = path.read_text(encoding="utf-8")
        if _has_try_import_arcade(text):
            offenders.append(str(path))

    assert not offenders, f"Unexpected arcade try/except imports in: {offenders}"
