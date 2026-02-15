from __future__ import annotations

from dataclasses import dataclass

from .pipeline import VerifyStepContext, run_verify_steps


@dataclass(frozen=True, slots=True)
class Step:
    name: str


STEP_ORDER: tuple[str, ...] = (
    "verify-demo",
    "verify-replays",
    "verify-strict",
    "mypy-gate",
    "mypy-baseline-guard",
    "mypy-island",
    "exception-budget-guard",
    "pytest-fast",
    "pytest-fast-duration-guard",
    "world-progression-check",
    "spawn-placeholder-safety",
    "stamp-audit",
    "brush-audit",
    "macro-audit",
    "room-audit",
    "encounter-set-uniqueness",
    "encounter-set-variety",
    "prefab-lint-overrides",
    "encounter-coverage",
    "encounter-coverage-matrix",
    "doctor-assets",
    "content-audit",
    "encounter-audit",
    "list-scenes",
    "list-worlds",
)

STEP_REGISTRY: tuple[Step, ...] = tuple(Step(name) for name in STEP_ORDER)

__all__ = [
    "Step",
    "STEP_ORDER",
    "STEP_REGISTRY",
    "VerifyStepContext",
    "run_verify_steps",
]

