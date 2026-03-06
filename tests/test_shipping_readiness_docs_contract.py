from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

REPO_ROOT = Path(__file__).resolve().parents[1]


def _assert_exact_lines_present(path: Path, expected_lines: tuple[str, ...]) -> None:
    assert path.exists(), f"Missing required docs file: {path.as_posix()}"
    lines = path.read_text(encoding="utf-8").splitlines()
    missing = [line for line in expected_lines if line not in lines]
    assert not missing, (
        f"Missing required exact line(s) in {path.as_posix()}:\n"
        + "\n".join(missing)
    )


def test_shipping_readiness_doc_contains_required_commands_and_gates_contract() -> None:
    _assert_exact_lines_present(
        REPO_ROOT / "docs" / "ShippingReadiness.md",
        (
            "python -m mesh_cli verify-all --artifacts artifacts --ci-bundle",
            "artifacts/player_pkg/manifest.json",
            "artifacts/web_smoke.json",
            "artifacts/perf_compare.json",
            "player-package-gate",
            "perf-baseline-compare",
        ),
    )
