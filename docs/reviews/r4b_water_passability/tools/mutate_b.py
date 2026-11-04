"""Mutation checks for R4B: each breaks one thing, runs the test meant to catch it, and puts the file back."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-rivers")
PY = r"C:\Users\slebb\AppData\Local\Programs\Python\Python313\python.exe"
SCR = r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river4\env3"
ENV = dict(os.environ, MESH_GL_SMOKE="1", APPDATA=SCR + r"\appdata", XDG_DATA_HOME=SCR + r"\xdg",
           MESH_USER_DIR=SCR + r"\user", MESH_PROJECTS_DIR=SCR + r"\projects")
H = "tests/test_water_passable.py"
G = "tests/test_water_passable_gpu.py"
T3 = H + "::test_out_of_carved_narrow_and_uneven_blocking_water_some_way_always_leads"
C = H + "::test_where_a_lake_and_its_inlet_overlap_players_and_npcs_get_out_down_the_crease"
MUTANTS = [
    ("its feet's edge held to where it was, not each step out (3f218ca re-review)", "engine/hd2d/world.py",
     "block = inb - 1e-6", "block = inb + 0.3",
     H + "::test_no_squeezing_along_a_gap_narrower_than_its_feet_between_blocking_ponds"),
    ("no route from a shore cell whose middle is water (3f218ca re-review)", "engine/hd2d/world.py",
     "a, b = node(start) or near(start), node(goal)", "a, b = node(start), node(goal)",
     H + "::test_npcs_that_walk_out_of_a_blocking_pond_go_on_with_their_route"),
    ("ashore, the ways out found far out are kept (3f218ca re-review)", "engine/behaviours/floor_route.py",
     "        if self._low <= -1e8:", "        if False:",
     H + "::test_an_npc_far_out_in_blocking_water_walks_out_though_no_way_out_is_within_reach"),
    ("blocking water lends its allowance to the water beyond (bb320df re-review)", "engine/hd2d/world.py",
     ('here = self.excess(x, y, z, hw, hh, "wading")', 'z, hw, hh, "wading") for i in (-1, 0, 1)'),
     ('here = self.excess(x, y, z, hw, hh)', 'z, hw, hh) for i in (-1, 0, 1)'),
     H + "::test_leaving_blocking_water_lends_no_deeper_wading_through_the_water_beyond"),
    ("its feet's edge goes further into blocking water (bb320df re-review)", "engine/hd2d/world.py",
     "block = inb - 1e-6", "block = 1e9",
     H + "::test_with_only_its_feet_s_edge_in_blocking_water_it_goes_no_further_in"),
    ("far out in blocking water with no way in reach: stranded (bb320df re-review)", "engine/behaviours/floor_route.py",
     "        held = world.blocked(fx / PX, fy / PX, z)\n        if held > 0.0:\n",
     "        held = world.blocked(fx / PX, fy / PX, z)\n        if held > 0.0 and self._ways:\n",
     H + "::test_an_npc_far_out_in_blocking_water_walks_out_though_no_way_out_is_within_reach"),
    ("no slide down a crease", "engine/hd2d/world.py",
     "if (fall > 0.0 and along > 0.5", "if (False and along > 0.5", C),
    ("an NPC in blocking water makes for its ways out, not down the fall", "engine/behaviours/floor_route.py",
     "        if held > 0.0:\n            # (in blocking water: whichever",
     "        if False:\n            # (in blocking water: whichever", C),
    ("the depth cap still holds one in blocking water (1eb0144 re-review)", "engine/hd2d/world.py",
     "block = 1e9  # water's ridge", "block = max(inb, DEEP_SLACK)  # water's ridge", T3),
    ("an unreachable point planned for every frame (1eb0144 re-review)", "engine/behaviours/floor_route.py",
     "self._waiting = max(self._waiting, 1.0)\n", "\n",
     H + "::test_an_npc_whose_route_point_can_t_be_reached_plans_again_once_a_second_not_every_frame"),
    ("held where blocking waters meet (1eb0144)", "engine/hd2d/world.py",
     "need = min(BLOCK_OUT, 0.5 * fall) if fall >= BLOCK_OUT else 0.0\n", "need = BLOCK_OUT\n", C),
    ("along blocking water (82018f8)", "engine/hd2d/world.py",
     "return there <= 0.0 or there < held - max(need * moved, 1e-6)",
     "                    return True",
     H + "::test_in_blocking_water_only_steps_out_along_a_canal_a_river_or_round_a_rim"),
    ("a blocking pond as deep everywhere (51fb...6c0288b)", "engine/hd2d/world.py",
     "BLOCK_EXCESS + within / PIXELS_PER_METRE)", "BLOCK_EXCESS + 0.0 * within / PIXELS_PER_METRE)",
     H + "::test_one_put_in_blocking_water_can_only_walk_out_never_across"),
    ("a blocked river as deep everywhere", "engine/hd2d/world.py",
     "depth + BLOCK_EXCESS + self.rivers.inset_at(px, py))", "depth + BLOCK_EXCESS + 0.0 * self.rivers.inset_at(px, py))",
     H + "::test_one_put_in_blocking_water_can_only_walk_out_never_across"),
    ("a raised pond blocking the ground under it", "engine/hd2d/world.py",
     '            if depth > 0.0 if pond.water.shore == "terrain" else -POND_DRY < depth < BODY:\n',
     '            if depth > 0.0 if pond.water.shore == "terrain" else -POND_DRY < depth:\n',
     H + "::test_a_pond_on_a_raised_floor_doesn_t_block_the_ground_under_it"),
    ("planning again and again without headway", "engine/behaviours/floor_route.py",
     "            if self._replans >= REPLANS:", "            if self._replans >= 10 ** 9:",
     H + "::test_a_wide_npc_judged_by_its_own_feet_plans_a_bounded_number_of_times_and_says_so_once"),
    ("removed water keeps a Block pond's wall", "engine/project_ops.py",
     '    blocking = _water_blocks((entity.get("behaviour_config") or {}).get("WaterSurface"))',
     '    blocking = ((entity.get("behaviour_config") or {}).get("WaterSurface") or {}).get("walkable") is False',
     H + "::test_blocking_set_and_cleared_through_every_path"),
    ("a behaviour setting leaves blocking unsynced", "engine/project_ops.py",
     "        _sync_water_solid(entity, water, was_blocking)  # (R4B: blocking or not, as set_water makes it)",
     "        pass",
     H + "::test_blocking_set_and_cleared_through_every_path"),
    ("a blocked river waded like auto", "engine/hd2d/world.py",
     '                if kind == "block":\n',
     '                if False:\n',
     H + "::test_a_river_s_water_is_walked_by_its_passable_not_its_look_or_carved_depth"),
    ("wade's own depth ignored", "engine/hd2d/world.py",
     'depth - (DEEP if kind == "auto" else wade))',
     'depth - DEEP)',
     H + "::test_a_river_s_water_is_walked_by_its_passable_not_its_look_or_carved_depth"),
    ("ponds not limiting", "engine/hd2d/world.py",
     "        for pond, box in self.ponds:\n", "        for pond, box in ():\n",
     H + "::test_a_blocking_pond_blocks_where_its_water_is_not_the_box_round_it"),
    ("a pond blocking by its box", "engine/hd2d/world.py",
     "            if not (box[0] <= px <= box[2] and box[1] <= py <= box[3]) or not inside(\n"
     "                    pond.water, pond.centre, (px * PIXELS_PER_METRE, py * PIXELS_PER_METRE)):\n",
     "            if not (box[0] <= px <= box[2] and box[1] <= py <= box[3]):\n",
     H + "::test_a_waded_pond_s_deep_basin_outside_its_outline_isn_t_its_water"),
    ("a sculpted shore blocking its dry ground", "engine/hd2d/world.py",
     '            if depth > 0.0 if pond.water.shore == "terrain" else -POND_DRY < depth < BODY:\n',
     "            if -POND_DRY < depth < BODY:\n",
     H + "::test_a_blocking_pond_blocks_where_its_water_is_not_the_box_round_it"),
    ("the pond's 2D box still met in a 3D room", "engine/hd2d/world.py",
     '                 and (getattr(s, "mesh_entity_data", None) or {}).get("id") not in self._pond_ids]',
     "                 and True]",
     G + "::test_a_blocking_pond_stops_the_player_at_its_shore_not_its_box"),
    ("an NPC never walks out", "engine/behaviours/floor_route.py",
     "        tx, ty, _tz = self._ways[0]\n", "        return\n        tx, ty, _tz = self._ways[0]\n",
     H + "::test_an_npc_put_in_deep_water_walks_out_never_deeper_and_then_keeps_its_route"),
    ("stranded said every frame", "engine/behaviours/floor_route.py",
     '        if not getattr(sprite, "mesh_hd2d_stranded", None):\n',
     "        if True:\n",
     H + "::test_an_npc_with_no_way_out_is_stranded_said_once_and_doesn_t_loop"),
    ("ways out unordered", "engine/hd2d/world.py",
     "        found.sort(key=lambda f: f[:3])\n", "        found.sort(key=lambda f: -f[0])\n",
     H + "::test_ways_out_are_the_nearest_standing_places_the_same_every_time"),
    ("passable not checked", "engine/hd2d/river.py",
     "    if passable not in water_mod.PASSABLE:\n", "    if False:\n",
     H + "::test_passable_is_stored_only_when_set_checked_and_older_rivers_and_ponds_are_as_they_were"),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


ok = True
for name, rel, old, new, test in MUTANTS:
    path = REPO / rel
    original = path.read_bytes()
    before = digest(path)
    text = original.decode("utf-8")
    for o, n in (zip(old, new) if isinstance(old, tuple) else [(old, new)]):  # (a tuple: several at once)
        assert text.count(o) == 1, (name, o)
        text = text.replace(o, n)
    try:
        path.write_bytes(text.encode("utf-8"))
        run = subprocess.run([PY, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider", test], cwd=REPO,
                             env=ENV, capture_output=True, text=True, timeout=900)
    finally:
        path.write_bytes(original)
    assert digest(path) == before
    caught = run.returncode != 0
    ok &= caught
    print(f"{'CAUGHT ' if caught else 'MISSED '} {name}: {run.stdout.strip().splitlines()[-1] if run.stdout else ''}")
sys.exit(0 if ok else 1)
