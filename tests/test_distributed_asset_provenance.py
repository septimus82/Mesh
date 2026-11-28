"""Nothing Mesh distributes is AI-generated, and nothing ships without a provenance entry (owner decision D6,
2026-11-22; docs/asset_licensing.md).

The records are the existing ones: assets/NOTICE.md's table (one row per bundled file or pattern: files, what and
where from, licence), the starter kit's PROVENANCE.md table and its catalog.json. A generated file names its generator
in its provenance record; this check refuses any such record among the distributed files, any allow-listed file
(pyproject.toml's [tool.setuptools.data-files]) without a NOTICE row, and any starter-kit file not on the allow-list.
Development assets made with PixelLab live in a separate private project, never here.
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from tooling.installed_product_check import allow_list

pytestmark = [pytest.mark.fast]

REPO = Path(__file__).resolve().parents[1]
KIT = "assets/hd2d_starter"
AI_GENERATOR = re.compile(
    r"pixel\s*lab|\bai[- ]generated|generated (?:by|with|using) (?:an? )?(?:ai|generative)\b|generative ai"
    r"|stable[- ]diffusion|midjourney|dall[- ]?e\b|open ?rail",
    re.IGNORECASE,
)


def notice_rows(text: str) -> list[tuple[list[str], str]]:
    """(file patterns, the row's other cells) for each table row of a NOTICE.md. A bare name in the files cell is in
    the folder of the path before it (``assets/sprites/a.png``, ``b.png``)."""
    rows = []
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        files, _, rest = line.strip().strip("|").partition("|")
        folder, patterns = "", []
        for token in re.findall(r"`([^`]+)`", files):
            if "/" in token:
                folder = token.rsplit("/", 1)[0] + "/"
                patterns.append(token)
            else:
                patterns.append(folder + token)
        rows.append((patterns, rest))
    return rows


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def refusals(notice: str, allowed: list[str], kit_files: Iterable[str], kit_provenance: str,
             catalog: Any) -> list[str]:
    """Why these distributed files and records may not ship; empty when they may."""
    rows = notice_rows(notice)
    found = [f"{f}: bundled without a row in assets/NOTICE.md" for f in allowed
             if not any(fnmatch.fnmatchcase(f, p) for patterns, _ in rows for p in patterns)]
    found += [f"{f}: in the starter kit but not on the allow-list" for f in sorted(set(kit_files) - set(allowed))]
    found += [f"assets/NOTICE.md row {patterns}: names an AI generator" for patterns, rest in rows
              if AI_GENERATOR.search(rest)]
    found += [f"{KIT}/PROVENANCE.md: names an AI generator: {line.strip()[:80]}"
              for line in kit_provenance.splitlines() if line.startswith("|") and AI_GENERATOR.search(line)]
    found += [f"{KIT}/catalog.json: names an AI generator: {s[:80]}" for s in _strings(catalog) if AI_GENERATOR.search(s)]
    return found


def _tree() -> tuple[str, list[str], list[str], str, Any]:
    kit_files = [p.relative_to(REPO).as_posix() for p in (REPO / KIT).rglob("*") if p.is_file()]
    return ((REPO / "assets/NOTICE.md").read_text(encoding="utf-8"), allow_list(), kit_files,
            (REPO / KIT / "PROVENANCE.md").read_text(encoding="utf-8"),
            json.loads((REPO / KIT / "catalog.json").read_text(encoding="utf-8")))


def test_nothing_distributed_is_ai_generated_or_without_provenance() -> None:
    notice, allowed, kit_files, kit_provenance, catalog = _tree()
    assert allowed and kit_files and notice_rows(notice)
    assert refusals(notice, allowed, kit_files, kit_provenance, catalog) == []


def test_the_guard_refuses_generated_unlisted_and_stray_files() -> None:
    notice, allowed, kit_files, kit_provenance, catalog = _tree()
    generated = notice + "\n| `assets/sprites/knight.png` | Generated with PixelLab (create-image-pixflux) | Owner's |\n"
    assert refusals(generated, allowed + ["assets/sprites/knight.png"], kit_files, kit_provenance, catalog) == [
        "assets/NOTICE.md row ['assets/sprites/knight.png']: names an AI generator"]
    assert refusals(notice, allowed + ["assets/sprites/knight.png"], kit_files, kit_provenance, catalog) == [
        "assets/sprites/knight.png: bundled without a row in assets/NOTICE.md"]
    assert refusals(notice, allowed, [*kit_files, f"{KIT}/textures/moss.png"], kit_provenance, catalog) == [
        f"{KIT}/textures/moss.png: in the starter kit but not on the allow-list"]
    row = "| `textures/moss.png` | AI-generated texture, hand-edited |"
    assert refusals(notice, allowed, kit_files, kit_provenance + row + "\n", catalog) == [
        f"{KIT}/PROVENANCE.md: names an AI generator: {row}"]
    marked = {**catalog, "models": [{**catalog["models"][0], "generator": "PixelLab v2 API"}]}
    assert refusals(notice, allowed, kit_files, kit_provenance, marked) == [
        f"{KIT}/catalog.json: names an AI generator: PixelLab v2 API"]
    assert not AI_GENERATOR.search("drawn in code with PIL; made by Mesh's own scripts; pixel textures; detail")
