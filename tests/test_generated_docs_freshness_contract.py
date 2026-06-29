from __future__ import annotations

from pathlib import Path

import pytest

import mesh_cli
from engine.tooling.generate_docs import DOC_FILENAMES

pytestmark = pytest.mark.fast


def _headings(path: Path) -> list[str]:
    return [line[3:] for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("## ")]


def test_generated_docs_content_matches_live_sources(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"

    assert mesh_cli.main(["docs", "--out-dir", str(docs_dir)]) == 0

    behaviours = _headings(docs_dir / "behaviours.md")
    assert len(behaviours) == 60
    assert "Combat" in behaviours
    assert "EnemyAI" in behaviours
    assert "Vendor" in behaviours

    input_doc = (docs_dir / "input.md").read_text(encoding="utf-8")
    assert "KEY_" not in input_doc
    assert "| `attack` | `SPACE` |" in input_doc
    assert "| `show_character` | `C` |" in input_doc

    scenes = _headings(docs_dir / "scenes.md")
    assert "scenes/edited_scene.json" not in scenes
    assert "scenes/cellar.json" in scenes
    assert "scenes/test_scene.json" in scenes


def test_docs_verify_fails_on_each_stale_generated_doc_and_passes_when_fresh(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"

    assert mesh_cli.main(["docs", "--out-dir", str(docs_dir)]) == 0
    assert mesh_cli.main(["docs", "--out-dir", str(docs_dir), "--verify"]) == 0

    for filename in DOC_FILENAMES.values():
        stale_path = docs_dir / filename
        original = stale_path.read_text(encoding="utf-8")
        stale_path.write_text("stale\n", encoding="utf-8")

        assert mesh_cli.main(["docs", "--out-dir", str(docs_dir), "--verify"]) == 1

        stale_path.write_text(original, encoding="utf-8")
        assert mesh_cli.main(["docs", "--out-dir", str(docs_dir), "--verify"]) == 0
