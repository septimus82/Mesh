from __future__ import annotations

from pathlib import Path


def test_legacy_impl_does_not_regrow() -> None:
    """
    Guard against `mesh_cli/legacy_impl.py` regrowing into a monolith.

    This test is intentionally text-based (no imports) to avoid side-effects and to keep it fast.
    """

    legacy_path = (Path(__file__).resolve().parents[1] / "mesh_cli" / "legacy_impl.py").resolve()
    assert legacy_path.exists(), f"missing legacy impl file: {legacy_path}"

    text = legacy_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    nonempty = [line for line in lines if line.strip()]

    # Baseline captured when this guard was introduced.
    BASELINE_NONEMPTY_LINES = 1566

    # Allow small incidental growth, but fail on large additions in a single PR.
    MAX_NONEMPTY_GROWTH = 30

    # Hard budget slightly above the current baseline.
    NONEMPTY_BUDGET = 1600

    assert len(nonempty) <= NONEMPTY_BUDGET, (
        f"{legacy_path} grew too large: nonempty_lines={len(nonempty)} > budget={NONEMPTY_BUDGET}. "
        "Move new CLI logic into `mesh_cli/*` modules and keep `legacy_impl.py` as wrappers only."
    )

    assert len(nonempty) <= BASELINE_NONEMPTY_LINES + MAX_NONEMPTY_GROWTH, (
        f"{legacy_path} regrew unexpectedly: nonempty_lines={len(nonempty)} > "
        f"baseline={BASELINE_NONEMPTY_LINES} + max_growth={MAX_NONEMPTY_GROWTH}. "
        "Move new CLI logic into `mesh_cli/*` modules and keep `legacy_impl.py` as wrappers only."
    )

