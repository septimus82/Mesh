"""Mutation checks for R4A: each breaks one thing, runs the test meant to catch it, and puts the file back."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-rivers")
PY = r"C:\Users\slebb\AppData\Local\Programs\Python\Python313\python.exe"
ENV = dict(os.environ, MESH_GL_SMOKE="1")
SCR = r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river4\env"
ENV.update(APPDATA=SCR + r"\appdata", XDG_DATA_HOME=SCR + r"\xdg", MESH_USER_DIR=SCR + r"\user",
           MESH_PROJECTS_DIR=SCR + r"\projects")
MUTANTS = [
    ("a meander's other limb counted as its bank (adddade)", "engine/hd2d/river.py",
     "                       or any(abs(rib.u[s] - rib.u[k]) > far\n", "                       or any(False\n",
     "tests/test_river_mouth.py::test_a_meander_s_close_limbs_carve_once_and_a_bed_carved_before_its_mouth_stays_pond_water"),
    ("the pond's opening fades along the river (51fb208)", "engine/water.py",
     "            open = max(open, (h - across) * (1.0 - smoothstep(0.0, MOUTH_BLEND, max(-sd, 0.0))));\n",
     "            open = max(open, (h - across) * (1.0 - smoothstep(0.0, MOUTH_BLEND, max(along, 0.0))));\n",
     "tests/test_river_mouth_gpu.py::test_no_seam_where_the_shore_crosses_the_stream_at_a_slant"),
    ("carving digs on into the pond (51fb208)", "engine/hd2d/river.py",
     "            continue  # (the pond's ground, but for a cell in from its shore: what the shore's cells are read from)\n", "            pass\n",
     "tests/test_river_mouth.py::test_flowing_into_a_pond_its_bed_eases_out_and_nothing_is_dug_in_the_pond"),
    ("a mouth's bed doesn't ease out", "engine/hd2d/river.py",
     "            ease = min(1.0, max(0.0, (mouth.u - s) / BLEND_M))\n",
     "            ease = 1.0\n",
     "tests/test_river_mouth.py::test_flowing_into_a_pond_its_bed_eases_out_and_nothing_is_dug_in_the_pond"),
    ("sinking reads its own bed's corners (51fb208)", "engine/hd2d/river.py",
     "                    continue  # (in its own water: its bed)\n", "                    pass\n",
     "tests/test_river_mouth.py::test_carving_a_river_twice_is_carving_once_even_at_the_ground_s_level"),
    ("classic ponds joined", "engine/hd2d/river.py",
     "    if pond.water.preset in water_mod.CLASSIC:\n", "    if False:\n",
     "tests/test_river_mouth.py::test_review_refusals_classic_ponds_banks_in_the_pond_a_drop_by_the_shore_and_flagged_ponds"),
    ("banks in the pond upstream accepted", "engine/hd2d/river.py",
     "    if banked is not None:\n", "    if False:\n",
     "tests/test_river_mouth.py::test_review_refusals_classic_ponds_banks_in_the_pond_a_drop_by_the_shore_and_flagged_ponds"),
    ("river water drawn in the pond", "engine/water.py", "        if (sd < 0.0) discard;\n", "",
     "tests/test_river_mouth_gpu.py::test_studio_draws_one_water_surface_where_the_stream_enters_the_pond"),
    ("pond bank drawn over the stream", "engine/water.py",
     "        if (open >= 0.0 && sd >= 0.0) discard;  // the river's water, not this pond's bank\n", "",
     "tests/test_river_mouth_gpu.py::test_studio_draws_one_water_surface_where_the_stream_enters_the_pond"),
    ("round cap not drawn", "engine/water.py",
     "    if (cap0 > 0.0 && u < cap0 && length(vec2(cap0 - u, across)) > cap0) discard;\n", "",
     "tests/test_river_mouth_gpu.py::test_studio_draws_one_water_surface_where_the_stream_enters_the_pond"),
    ("RiverIndex keeps water in the pond / past caps", "engine/hd2d/river.py",
     "        found = self._ends.get(index)\n        if found is None:\n            return False\n",
     "        found = None\n        if found is None:\n            return False\n",
     "tests/test_river_mouth.py"),
    ("sinking measures only at the points", "engine/hd2d/river.py",
     "        if known and level > min(known):  # (standing over it: its stretch sunk)\n",
     "        if known and level > min(known) and any(abs(rib.u[k] - m) < 0.13 for m in rib.marks):\n",
     "tests/test_river_mouth.py::test_sinking_finds_a_dip_between_points_and_keeps_a_mouth_at_its_pond"),
    ("sinking measures a neighbour's bed", "engine/hd2d/river.py",
     "for f in (0.0, 0.5, 1.0)):\n                    continue\n", "for f in (0.0, 0.5, 1.0)):\n                    pass\n",
     "tests/test_river_mouth.py::test_carving_beside_a_pond_or_another_river_measures_their_shore_not_their_bed"),
    ("a mouth sunk below its pond", "engine/hd2d/river.py",
     "        level = p[3] - d if pond is None else max(min(p[3], pond.level), p[3] - d)\n",
     "        level = p[3] - d\n",
     "tests/test_river_mouth.py::test_sinking_finds_a_dip_between_points_and_keeps_a_mouth_at_its_pond"),
    ("no bowl at a round end", "engine/hd2d/river.py",
     "        if bowl is not None:  # a round end: measured from the middle of its half circle\n",
     "        if False:  # a round end: measured from the middle of its half circle\n",
     "tests/test_river_mouth.py::test_carving_a_round_end_makes_a_bowl_and_no_trough_past_it"),
    ("level mismatch not refused", "engine/hd2d/river.py",
     "    if abs(gap) > MOUTH_LEVEL_PX:\n", "    if abs(gap) > 99.0:\n",
     "tests/test_river_mouth.py::test_refusals_say_what_to_change_and_change_nothing"),
    ("two crossings not refused", "engine/hd2d/river.py",
     "    if early is not None:\n        x, y = rib.centre[early]\n", "    if False:\n        x, y = rib.centre[early]\n",
     "tests/test_river_mouth.py::test_a_course_in_and_out_of_the_pond_and_one_flowing_out_of_it_are_refused"),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


ok = True
for name, rel, old, new, test in MUTANTS:
    path = REPO / rel
    original = path.read_bytes()
    before = digest(path)
    text = original.decode("utf-8")
    assert text.count(old) == 1, (name, old)
    try:
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        run = subprocess.run([PY, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider", test], cwd=REPO,
                             env=ENV, capture_output=True, text=True, timeout=900)
    finally:
        path.write_bytes(original)
    assert digest(path) == before
    caught = run.returncode != 0
    ok &= caught
    print(f"{'CAUGHT ' if caught else 'MISSED '} {name}: {run.stdout.strip().splitlines()[-1] if run.stdout else ''}")
sys.exit(0 if ok else 1)
