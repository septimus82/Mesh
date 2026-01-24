from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable


def copy_minipack_repo(tmp_path: Path) -> Path:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "minipack"
    repo_root = tmp_path / "repo"
    if repo_root.exists():
        shutil.rmtree(repo_root)
    shutil.copytree(fixture_root, repo_root)
    return repo_root


def mutate_file(repo_root: Path, rel_path: str, transform: Callable[[dict], dict]) -> None:
    target = repo_root / rel_path
    payload = json.loads(target.read_text(encoding="utf-8"))
    updated = transform(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_dump_json(updated), encoding="utf-8")


def write_text(repo_root: Path, rel_path: str, text: str) -> None:
    target = repo_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _dump_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
