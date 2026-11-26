"""The skips a verify-all run on a synthetic repo (a ``tmp_path`` with ``pyproject.toml``) meets (#624).

Such a repo has none of the engine checkout's step inputs, so those steps report ``skipped: <reason>``, which verify-all
fails unless ``pipeline.ALLOWED_SKIPS`` lists it. Tests that use a synthetic repo to check something else (artifact
shapes, flags, the stdout contract) allow exactly these for their own run; the shared run of this checkout never does.
"""

from __future__ import annotations

from typing import Any

SYNTHETIC_REPO_SKIPS: dict[tuple[str, str], str] = {
    ("runtime-player-smoke", "skipped: no smoke scene"): "no scenes/ in a synthetic repo",
    ("player-package-gate", "skipped: no engine/ and mesh_cli/ sources"): "no sources in a synthetic repo",
    ("player-package-gate", "skipped: no scenes/runtime_smoke_scene.json"): "no scenes/ in a synthetic repo",
    ("web-smoke", "skipped: web target unavailable"): "no web_main.py / pygbag.toml in a synthetic repo",
    ("perf-baseline-compare", "skipped: no perf scene set or baseline"): "no tooling/perf_baselines in a synthetic repo",
    ("content-audit", "skipped: no content roots"): "no content roots in a synthetic repo",
}


def allow_synthetic_repo_skips(monkeypatch: Any, *, except_for: tuple[str, str] | None = None) -> None:
    """Let this test's verify-all pass the synthetic repo's skips (all but ``except_for``)."""
    import mesh_cli.verify_steps.pipeline as pipeline

    extra = {key: why for key, why in SYNTHETIC_REPO_SKIPS.items() if key != except_for}
    monkeypatch.setattr(pipeline, "ALLOWED_SKIPS", {**pipeline.ALLOWED_SKIPS, **extra})
