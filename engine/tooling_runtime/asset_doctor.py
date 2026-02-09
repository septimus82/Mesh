from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def doctor_assets(
    *,
    repo_root: Path,
    fix: bool = False,
    strict: bool = False,
    packs: Iterable[str] | None = None,
) -> dict[str, Any]:
    from engine.tooling_runtime.doctor_assets_registry import (
        build_doctor_checks,
        build_doctor_context,
        finalize_doctor_payload,
    )

    ctx = build_doctor_context(repo_root=repo_root, fix=fix, strict=strict, packs=packs)
    for _spec, enabled, runner in build_doctor_checks():
        if enabled(ctx):
            runner(ctx)
    return finalize_doctor_payload(ctx)
