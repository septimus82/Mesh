"""Cutscene runtime - deterministic timeline scripting for Mesh Engine.

This module provides:
- CutsceneRunner for deterministic cutscene execution
- Schema validation with actionable errors
- Migration framework for versioned scripts
- Save/restore compatibility
"""

from __future__ import annotations

from .schema import (
    CUTSCENE_SCHEMA_VERSION,
    CutsceneValidationError,
    migrate_cutscene_script,
    register_cutscene_migration,
    sort_cutscene_validation_errors,
    validate_cutscene_command,
    validate_cutscene_script,
)
from .runner import (
    CutsceneRunner,
    CutsceneRunnerState,
    CutsceneCommand,
)

__all__ = [
    # Schema
    "CUTSCENE_SCHEMA_VERSION",
    "CutsceneValidationError",
    "migrate_cutscene_script",
    "register_cutscene_migration",
    "sort_cutscene_validation_errors",
    "validate_cutscene_command",
    "validate_cutscene_script",
    # Runner
    "CutsceneRunner",
    "CutsceneRunnerState",
    "CutsceneCommand",
]
