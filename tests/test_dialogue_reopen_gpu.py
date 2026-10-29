"""Watchfire R4, in Mesh Studio's real (hidden) window with its own mouse and keyboard events
(tooling/watchfire_r4_dialogue.py): a conversation of eleven lines (choices that set a flag and branch, a run-on after
the branch, an opening that needs the flag) written, saved, reopened, edited, undone and redone, left for another room
and back, saved and reopened again and twice more: its lines keep their numbers, "+ Next line" stays, a line added at
the end follows the last one; and it plays as written in the game and in an exported build. Silent.
GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import watchfire_r4_dialogue as r4

    out = tmp_path_factory.mktemp("r4")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    return r4.run(out)


def test_reopening_shows_the_same_numbers_openings_and_next_line_button(report: dict) -> None:
    written, reopened = report["A_written"], report["B_reopened"]
    assert reopened["stored"] == written["stored"], "the conversation itself survives saving"
    assert reopened["shown"] == written["shown"], "and the creator sees it numbered as written"
    assert written["shown"]["lines"][0].startswith("1. Traveller!") and written["shown"]["otherwise_line"] == "1"
    assert written["shown"]["openings"] == ["11"] and written["shown"]["next_line_button"] == ["+ Next line (after 11)"]


def test_a_line_added_at_the_end_after_reopening_follows_the_last_line(report: dict) -> None:
    assert report["B_add_line_at_the_end_follows"] == ["Back already? Is it lit?"]


def test_edits_after_reopening_keep_numbers_and_undo_redo(report: dict) -> None:
    edited = report["C_edited"]
    assert edited["undo_restored_the_line"] and edited["redo_same"]
    numbers = {t.split(". ", 1)[1][:12]: t.split(".", 1)[0] for t in edited["shown"]["lines"] if not t.startswith("1. start")}
    assert numbers["Traveller! T"] == "1" and numbers["Will you lig"] == "2" and numbers["Bless you, t"] == "3"
    assert numbers["It sparks on"] == "11", "a line inserted takes the next number; the others keep theirs"
    assert edited["shown"]["openings"] == ["10"], "after a deletion the opening still names its line (renumbered)"


def test_another_room_saving_and_reopening_change_nothing(report: dict) -> None:
    assert report["D_room_and_back"] == report["E_reopened"], "shown and stored alike after saving and reopening"
    assert report["F_repeat"]["files_identical"], "saving again without edits writes the same file"
    assert report["F_repeat"]["shown"] == report["E_reopened"]["shown"]
    assert report["F_repeat"]["stored"] == report["E_reopened"]["stored"]


def test_it_plays_as_written_in_the_game_and_the_exported_build(report: dict) -> None:
    game = report["G_game"]
    assert game["first_talk"][:4] == ["Traveller! The watchfire at the crossing has gone dark.",
                                      "Will you light it before nightfall?", "Bless you, traveller. Take my flint.",
                                      "It sparks on the first strike."]
    assert game["first_talk"][-1] == "Safe travels." and "Strike the flint on the dry kindling." not in game["first_talk"]
    assert game["flags"] == ["task_accepted"] and game["second_talk"] == ["Back already? Is it lit?"]
    assert report["H_export"]["exit"] == 0 and report["H_exported_game"] == game
