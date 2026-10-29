"""Watchfire R4: a conversation's lines keep their numbers through saving and reopening.

Saving writes a room through ``json_io.dumps_stable`` (keys sorted), so a conversation's lines come back sorted by name
(``line_10``, ``line_11``, ``line_2`` ... ``root``), not in the order they were written. Their ids and every link
between them survive; but Studio numbered the lines by the dictionary's order, so after reopening every number meant
another line, and "add a line at the end" followed whichever line sorted last. ``project_ops.line_order`` is the
written order, the same before and after saving."""

from __future__ import annotations

import json

import pytest

from engine import project_ops as ops
from engine.json_io import dumps_stable

pytestmark = pytest.mark.fast


def _written() -> tuple[dict, str]:
    """An object's conversation of eleven lines, written as Studio writes one: its first line, then lines after it."""
    scene, eid = ops.place_blank({"name": "Start", "schema_version": 1, "version": 1, "entities": []}, "start", "Warden", 320, 200)
    scene = ops.set_dialogue_text(scene, eid, "Line one.")
    for k in range(2, 12):
        scene, _ = ops.add_line(scene, eid, text=f"Line {k}.")
    return scene, eid


def _saved_and_reopened(scene: dict) -> dict:
    return json.loads(dumps_stable(scene))  # (what Studio writes, read back)


def _nodes(scene: dict, eid: str) -> dict:
    return ops.conversation(ops.find_entity(scene, eid))["nodes"]


def test_the_written_order_is_root_then_the_lines_by_number_then_other_names() -> None:
    nodes = dict.fromkeys(["line_10", "line_2", "root", "greet", "line_3", "farewell", "line_11"])
    assert ops.line_order(nodes) == ["root", "line_2", "line_3", "line_10", "line_11", "farewell", "greet"]
    assert ops.line_order({}) == []


def test_saving_reorders_the_file_but_not_the_lines_numbers_or_links() -> None:
    scene, eid = _written()
    before, after = _nodes(scene, eid), _nodes(_saved_and_reopened(scene), eid)
    assert list(before) != list(after), "(the file's order changes: this is why numbering can't use it)"
    assert after == before, "every line, its words and its links survive"
    assert ops.line_order(after) == ops.line_order(before) == ["root"] + [f"line_{k}" for k in range(2, 12)]
    assert [after[n]["text"] for n in ops.line_order(after)] == ["Line one."] + [f"Line {k}." for k in range(2, 12)]
    again = _saved_and_reopened(_saved_and_reopened(scene))
    assert dumps_stable(again) == dumps_stable(_saved_and_reopened(scene)), "saving again changes nothing"


def test_a_line_added_at_the_end_after_reopening_follows_the_last_line() -> None:
    scene, eid = _saved_and_reopened(_written()[0]), _written()[1]
    scene, new = ops.add_line(scene, eid, text="One more.")
    nodes = _nodes(scene, eid)
    assert nodes["line_11"]["next"] == new and "next" not in nodes[new], "after the last line written, not 'root'"
    assert nodes["root"]["next"] == "line_2", "the first line still leads to the second"


def test_removing_the_first_line_makes_the_first_numbered_line_the_opening() -> None:
    scene, eid = _written()
    scene = ops.set_line(scene, eid, "root", next_line=None)  # (it leads nowhere: nothing to follow on to)
    scene = ops.remove_line(_saved_and_reopened(scene), eid, "root")
    talk = ops.conversation(ops.find_entity(scene, eid))
    assert talk["start"] == "line_2", "the line now numbered 1, whatever order the file has"
