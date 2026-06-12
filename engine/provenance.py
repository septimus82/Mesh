"""
Provenance metadata for Mesh Engine artifacts.

Provides a frozen ``Provenance`` dataclass that captures tool version,
git state, Python version, and platform info.  Every major CLI artifact
(demo report, release report, bundle manifest, export manifest) embeds
a provenance block produced by ``get_provenance()``.

Deterministic mode (``deterministic=True``) omits volatile fields like
timestamps so that repeated runs with the same inputs produce
byte-identical output.
"""
from __future__ import annotations

import platform as _platform
import sys
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Version — single source of truth
# ---------------------------------------------------------------------------

def _engine_version() -> str:
    """Return the engine version string."""
    try:
        from engine.version import ENGINE_VERSION

        return str(ENGINE_VERSION)
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Git helpers (safe: never crash)
# ---------------------------------------------------------------------------

def _git_commit() -> str | None:
    try:
        import subprocess

        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _git_dirty() -> bool | None:
    try:
        import subprocess

        r = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return None
        return len(r.stdout.strip()) > 0
    except Exception:
        return None


def _git_describe() -> str | None:
    try:
        import subprocess

        r = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _utc_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Provenance dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Provenance:
    """Frozen provenance metadata embedded in artifacts."""

    tool_name: str = "Mesh Engine"
    tool_version: str = ""
    build_timestamp_utc: str | None = None
    python_version: str = ""
    platform: str = ""
    git_commit: str | None = None
    git_dirty: bool | None = None
    git_describe: str | None = None


def get_provenance(*, deterministic: bool = False) -> Provenance:
    """Build a ``Provenance`` snapshot.

    When *deterministic* is True, volatile fields (timestamps) are
    omitted so that outputs are reproducible.
    """
    return Provenance(
        tool_name="Mesh Engine",
        tool_version=_engine_version(),
        build_timestamp_utc=None if deterministic else _utc_iso(),
        python_version=_platform.python_version(),
        platform=sys.platform,
        git_commit=_git_commit(),
        git_dirty=_git_dirty(),
        git_describe=_git_describe(),
    )


def provenance_to_dict(prov: Provenance) -> dict[str, Any]:
    """Convert *prov* to a stable dict (sorted keys, None fields omitted)."""
    d: dict[str, Any] = {
        "tool_name": prov.tool_name,
        "tool_version": prov.tool_version,
        "python_version": prov.python_version,
        "platform": prov.platform,
    }
    if prov.build_timestamp_utc is not None:
        d["build_timestamp_utc"] = prov.build_timestamp_utc
    if prov.git_commit is not None:
        d["git_commit"] = prov.git_commit
    if prov.git_dirty is not None:
        d["git_dirty"] = prov.git_dirty
    if prov.git_describe is not None:
        d["git_describe"] = prov.git_describe
    return d


def format_provenance_text(prov: Provenance) -> str:
    """Human-readable provenance block."""
    lines = [
        f"Tool: {prov.tool_name} {prov.tool_version}",
        f"Python: {prov.python_version}",
        f"Platform: {prov.platform}",
    ]
    if prov.build_timestamp_utc:
        lines.append(f"Timestamp: {prov.build_timestamp_utc}")
    if prov.git_commit:
        dirty = " (dirty)" if prov.git_dirty else ""
        lines.append(f"Git: {prov.git_commit}{dirty}")
    if prov.git_describe:
        lines.append(f"Describe: {prov.git_describe}")
    return "\n".join(lines)
