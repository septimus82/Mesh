from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from engine.tooling_runtime import asset_doctor as runtime_asset_doctor

__all__ = ["doctor_assets"]


def doctor_assets(
    *,
    repo_root: Path,
    fix: bool = False,
    strict: bool = False,
    packs: Iterable[str] | None = None,
) -> dict[str, Any]:
    return runtime_asset_doctor.doctor_assets(repo_root=repo_root, fix=fix, strict=strict, packs=packs)
