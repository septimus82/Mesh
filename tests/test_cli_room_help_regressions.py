from __future__ import annotations

import re
import sys
from pathlib import Path

from tests.subprocess_tools import run_checked


def test_room_help_text_is_stable() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    cp = run_checked(
        [sys.executable, "-m", "mesh_cli", "room", "--help"],
        cwd=str(repo_root),
        check=True,
    )

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    out = _norm(cp.stdout)
    out_ws_stripped = re.sub(r"\s+", "", cp.stdout)

    assert " room " in out
    assert "Room subcommand" in out
    assert "scaffold" in out

    # Argparse can hard-wrap help output and even split words mid-token.
    # For these stability checks, ignore all whitespace.
    assert "usage:__main__.pyroom[-h]{scaffold}" in out_ws_stripped

    def assert_in_order(haystack: str, needles: list[str]) -> None:
        idx = 0
        for needle in needles:
            j = haystack.find(needle, idx)
            assert j != -1, f"missing: {needle}"
            idx = j + len(needle)

    assert_in_order(
        out,
        [
            "scaffold",
        ],
    )


def test_room_scaffold_help_text_is_stable() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    cp = run_checked(
        [sys.executable, "-m", "mesh_cli", "room", "scaffold", "--help"],
        cwd=str(repo_root),
        check=True,
    )

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    out = _norm(cp.stdout)
    out_ws_stripped = re.sub(r"\s+", "", cp.stdout)

    assert " room scaffold " in out
    assert "Pathtoworldfile" in out_ws_stripped
    assert "SourcesceneJSONpath" in out_ws_stripped
    assert "Macroassettoapplytofrom-scene" in out_ws_stripped
    assert "NewsceneJSONpath" in out_ws_stripped
    assert "StampJSONpathtoapplyintoto-scene" in out_ws_stripped
    assert "--worldWORLD" in out_ws_stripped
    assert "--from-sceneFROM_SCENE" in out_ws_stripped
    assert "--door-macroDOOR_MACRO" in out_ws_stripped
    assert "--to-sceneTO_SCENE" in out_ws_stripped
    assert "--to-stampTO_STAMP" in out_ws_stripped
    assert "--gridGRID" in out_ws_stripped
    assert "--tileTILE" in out_ws_stripped
    assert "--layersLAYERS" in out_ws_stripped
    assert "--collision-layerCOLLISION_LAYER" in out_ws_stripped
    assert "--stamp-originSTAMP_ORIGIN" in out_ws_stripped
    assert "--spawn-idSPAWN_ID" in out_ws_stripped
    assert "--anchor{primary,cursor,player}" in out_ws_stripped
    assert "--id-prefixID_PREFIX" in out_ws_stripped
    assert "--argARG" in out_ws_stripped

    def assert_in_order(haystack: str, needles: list[str]) -> None:
        idx = 0
        for needle in needles:
            j = haystack.find(needle, idx)
            assert j != -1, f"missing: {needle}"
            idx = j + len(needle)

    assert_in_order(
        out_ws_stripped,
        [
            "--worldWORLD",
            "--from-sceneFROM_SCENE",
            "--door-macroDOOR_MACRO",
            "--to-sceneTO_SCENE",
            "--to-stampTO_STAMP",
            "--gridGRID",
            "--tileTILE",
            "--layersLAYERS",
            "--collision-layerCOLLISION_LAYER",
            "--stamp-originSTAMP_ORIGIN",
            "--spawn-idSPAWN_ID",
            "--anchor{primary,cursor,player}",
            "--id-prefixID_PREFIX",
            "--argARG",
        ],
    )
