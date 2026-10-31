"""HD-2D cutaway, headless: the per-structure ``cutaway`` setting is validated where rooms are read and where they are
edited (project_ops.set_structure: Mesh Studio's See-through button, AI tools). The rendering is
tests/test_hd2d_cutaway_gpu.py."""

from __future__ import annotations

import pytest

from engine import project_ops as ops
from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

pytestmark = pytest.mark.fast

MODEL = "assets/models/cottage.glb"


def test_cutaway_is_off_unless_a_structure_asks_for_it() -> None:
    hd = parse_hd2d({"structures": [{"id": "a", "model": MODEL}, {"id": "b", "model": MODEL, "cutaway": True}]})
    assert [(st.id, st.cutaway) for st in hd.structures] == [("a", False), ("b", True)]
    with pytest.raises(Hd2dSettingsError, match="cutaway must be true or false"):
        parse_hd2d({"structures": [{"id": "a", "model": MODEL, "cutaway": "yes"}]})


def test_the_edit_turns_it_on_and_off_and_refuses_anything_else() -> None:
    scene = {"entities": [], "settings": {"hd2d": {"structures": [{"id": "house", "model": MODEL, "x": 64, "y": 64}]}}}
    on = ops.set_structure(scene, "house", cutaway=True)
    assert ops.find_structure(on, "house")["cutaway"] is True
    off = ops.set_structure(on, "house", cutaway=False)
    assert "cutaway" not in ops.find_structure(off, "house"), "off is the default: nothing written"
    assert ops.set_structure(scene, "house", x=96)["settings"]["hd2d"]["structures"][0].get("cutaway") is None
    with pytest.raises(ops.OpError, match="cutaway must be true or false"):
        ops.set_structure(scene, "house", cutaway=1)
