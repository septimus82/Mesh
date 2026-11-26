"""S1-0 part C section 2: small, hand-written mutation probes (no mutation framework).

    py -3.13 docs/s1/evidence/mutation_probe.py            # list the groups
    bash docs/s1/evidence/mutation_run.sh vendor           # one group: baseline, then each mutant

The mutant table lives here; mutation_run.sh drives it so that only ONE Python process ever runs at a time (the
owner's CPU rule): per group it copies the module aside, runs the module's own test files unmutated (they must pass),
then for each mutant: ``--apply GROUP ID`` (writes it and exits), one pytest process (the repo's default addopts, as
CI's pytest job selects, ``-x``, no cache), then copies the module back and checks its SHA-256. pytest exit 0 = the
mutant SURVIVED; 1 (a test failed) or 2 (collection errors) = KILLED; anything else (4 usage error, 5 no tests
collected: a stale test id) = ERROR, never a kill. A mutant is one exact text replacement that must match exactly once:
an anchor found 0 or 2+ times is an ERROR (exit 2, from ``--check`` before the baseline and from ``--apply``), so a
stale anchor can never pass for a killed mutant. ``--apply`` refuses a module with uncommitted changes.

E11 (S1 5.5, #650): ``e11_<id>`` groups run one named mutant against only the test named to kill it
(``bash docs/s1/evidence/mutation_run.sh e11_Q1``, and so on for each id in ``E11``).
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# group -> (module, test files, [(mutant id, what it breaks, old text, new text)])
GROUPS: dict[str, tuple[str, list[str], list[tuple[str, str, str, str]]]] = {
    "save_entity_state": (
        "engine/save_runtime/entity_state.py",
        ["tests/test_b01_save_identity.py", "tests/test_b02_primary_tag.py", "tests/test_room_memory.py",
         "tests/test_rv1_carried_room.py", "tests/test_save_entity_quest_state.py",
         "tests/test_save_serialization_strictness.py"],
        [
            ("S1", "loaded position not written back to the entity's data dict (a re-save after load keeps the old x)",
             '            entity_data["x"] = float(state.x)\n', '            pass\n'),
            ("S2", "behaviour saveable_state never serialised",
             "                    if isinstance(bstate, dict) and bstate:\n",
             "                    if False:\n"),
            ("S3", "recorded primary tag not restored (B-02)",
             "                if state.primary_tag:\n                    sprite.mesh_tag = state.primary_tag\n",
             "                if False:\n                    sprite.mesh_tag = state.primary_tag\n"),
            ("S4", "strict save swallows a failing saveable_state",
             "                    if strict:\n                        raise SaveSerializationError(msg) from exc\n",
             "                    if False:\n                        raise SaveSerializationError(msg) from exc\n"),
            ("S5", "twins bind ambiguously by position (B-01 identity)",
             "        if len(found) == 1 and claimed_by[found[0]] == 1:\n",
             "        if len(found) >= 1:\n"),
        ],
    ),
    "project_save": (
        "engine/project_save.py",
        ["tests/test_project_save_transaction.py", "tests/test_room_file_ownership.py",
         "tests/test_safe_scene_creation.py", "tests/test_studio_room_undo_save.py"],
        [
            ("P1", "a file changed by something else between staging and commit is overwritten",
             "            if now != target.stamp:\n", "            if False:\n"),
            ("P2", "no .outside-change.bak backup of a file edited outside Studio",
             "    if seen is None or not target.is_file() or target.stat().st_mtime == seen:\n",
             "    if True:\n"),
            ("P3", "rollback does not put the original back (reports restored)",
             "                _replace(target.original, path)\n                target.original = None\n",
             "                target.original = None\n"),
            ("P4", "staging no longer refuses a path the project never wrote (F15; commit still uses publish_new)",
             "            if target.rel in fresh and os.path.lexists(path):\n",
             "            if False:\n"),
            ("P5", "after a save, 'seen' is not refreshed (next save backs up Studio's own file as an outside change)",
             "        seen[target.rel] = (root / target.rel).stat().st_mtime\n        _discard(target.staged, leftovers, root)",
             "        _discard(target.staged, leftovers, root)"),
        ],
    ),
    "vendor": (
        "engine/behaviours/vendor.py",
        ["tests/test_vendor_shop.py", "tests/test_vendor_purchase_integrity.py", "tests/test_inventory.py"],
        [
            ("V1", "an item costing exactly your gold is refused (< becomes <=)",
             "        if current_currency < price:\n", "        if current_currency <= price:\n"),
            ("V2", "out-of-stock items can still be bought",
             "        if quantity == 0:\n", "        if quantity == -999:\n"),
            ("V3", "finite stock never decreases",
             '            item["quantity"] = quantity - 1\n', '            item["quantity"] = quantity\n'),
            ("V4", "selling an item you don't have pays gold",
             "        if not inv.has_item(item_id, 1):\n", "        if False:\n"),
            ("V5", "selling keeps the item",
             "        inv.remove_item(item_id, 1)\n        gs.add_counter(self.currency_counter, payout)\n",
             "        gs.add_counter(self.currency_counter, payout)\n"),
        ],
    ),
    "quests": (
        "engine/quest_runtime/progress.py",
        ["tests/test_quest_manager.py", "tests/test_quest_dict_form_ids.py", "tests/test_quest_dict_form_readers.py",
         "tests/test_quest_gating_flags.py", "tests/test_quest_gating_semantics_regression.py",
         "tests/test_quest_normalization_regression.py", "tests/test_quest_stage_progress_roundtrip.py",
         "tests/test_quest_system_unification_contract.py", "tests/test_quest_toast_order_regression.py",
         "tests/test_quest_validation.py", "tests/test_quest_runner_integration.py", "tests/test_quest_runner_golden.py",
         "tests/test_replace_state_quest_sync.py", "tests/test_demo_quest_contract.py",
         "tests/test_perk_effects_rewards.py", "tests/test_new_game_isolation.py",
         "tests/test_quest_progress_guards.py"],
        [
            ("Q1", "a stage keyed on payload_value completes for any value (kill wolf vs kill boar)",
             '        if "payload_value" in spec and payload.get(payload_field) != spec.get("payload_value"):\n',
             "        if False:\n"),
            ("Q2", "one event pass instead of two (cross-quest same-event starts)",
             "    for _ in range(2):\n", "    for _ in range(1):\n"),
            ("Q3", "completing an already completed quest pays its reward again",
             '    if state.get("status") == "completed":\n        return\n    state["status"] = "completed"\n',
             '    state["status"] = "completed"\n'),
            ("Q4", "quest reward inc_counters never applied",
             "        manager.window.inc_counter(counter, float(amount))\n", "        pass\n"),
            ("Q5", "complete_stage completes a stage that is not the current one",
             '    if state.get("current_stage") != stage["id"]:\n        return\n    completed = state.get("completed_stages", [])\n',
             '    completed = state.get("completed_stages", [])\n'),
        ],
    ),
    "entity_factory": (
        "engine/scene_controller_parts/entity_factory.py",
        ["tests/test_behaviour_teardown_on_entity_removal.py", "tests/test_behaviour_teardown_on_delete_paths.py",
         "tests/test_behaviour_unsubscribe_on_end.py", "tests/test_state_lifecycle.py",
         "tests/test_authoring_playable_prefabs_contract.py", "tests/test_milestone8_runtime_fixes.py"],
        [
            ("E1", "on_destroy may run twice for one removal",
             '    if getattr(sprite, "_mesh_behaviours_ended", False):\n        return\n',
             '    if getattr(sprite, "_mesh_behaviours_ended", False):\n        pass\n'),
            ("E2", "removal never calls on_destroy",
             "        try:\n            on_destroy()\n", "        try:\n            pass\n"),
            ("E3", "a behaviour rebuild keeps the old subscriptions (listeners double on every live edit)",
             '    for unsubscribe in getattr(sprite, "mesh_behaviour_unsubscribes", None) or ():\n        unsubscribe()\n',
             '    for unsubscribe in getattr(sprite, "mesh_behaviour_unsubscribes", None) or ():\n        pass\n'),
            ("E4", "subscriptions not tracked by the scene (room exit leaks listeners)",
             "    for unsubscribe in made:\n        self.track_scene_subscription(unsubscribe)\n",
             "    for unsubscribe in made:\n        pass\n"),
            ("E5", "rebuilt behaviours are marked already ended (their removal never ends them)",
             "    cast(Any, sprite)._mesh_behaviours_ended = False", "    cast(Any, sprite)._mesh_behaviours_ended = True"),
        ],
    ),
    "project_ops": (
        "engine/project_ops.py",
        ["tests/test_project_ops.py", "tests/test_project_ops_authoring.py", "tests/test_project_ops_lighting.py"],
        [
            ("O1", "remove_entity of an unknown id silently succeeds",
             "    find_entity(scene, entity_id)\n    out = copy.deepcopy(scene)\n    out[\"entities\"] = [e for e in entities(out) if e.get(\"id\") != entity_id]\n",
             "    out = copy.deepcopy(scene)\n    out[\"entities\"] = [e for e in entities(out) if e.get(\"id\") != entity_id]\n"),
            ("O2", "renaming a person no longer renames the dialogue speaker that used the old name",
             '    if dialogue is not None and dialogue.get("speaker") in (None, "", old):\n', "    if False:\n"),
            ("O3", "set_solid(False) cannot make an object passable again",
             "    return set_entity_fields(scene, entity_id, solid=True if solid else None)\n",
             "    return set_entity_fields(scene, entity_id, solid=True)\n"),
            ("O4", "the conversation's 'Only once' toggle always stores True",
             '        config["once"] = bool(once)\n', '        config["once"] = True\n'),
            ("O5", "move_entity writes x into y",
             '    entity["x"], entity["y"] = round(float(x), 2), round(float(y), 2)\n',
             '    entity["x"], entity["y"] = round(float(x), 2), round(float(x), 2)\n'),
        ],
    ),
    "scene_room": (
        "mesh_net/scene_room.py",
        ["tests/test_mesh_net_scene.py", "tests/test_mesh_net_combat.py"],
        [
            ("N1", "a one_shot lever can be used again",
             '            if not event or size is None or (cfg.get("one_shot") and lever_id in self.used):\n',
             "            if not event or size is None:\n"),
            ("N2", "a lever behind the player (beyond contact) can be used",
             "            if alignment < 0.0 and d > max(8.0, (max(p.body.width, p.body.height) + max(size)) * 0.5):\n",
             "            if False:\n"),
            ("N3", "one hitbox hits the same enemy on every tick of its lifetime",
             "            if enemy_id in box.hit or enemy.state.dead or not shapes_overlap(box.area, entity_shape(target)):\n",
             "            if enemy.state.dead or not shapes_overlap(box.area, entity_shape(target)):\n"),
            ("N4", "attacks hit enemies on another floor/level",
             "            if not self._level(p.body, target):\n                continue\n            box.hit.add(enemy_id)\n",
             "            box.hit.add(enemy_id)\n"),
            ("N5", "a client accepts a snapshot with duplicate player rows",
             "        if (not isinstance(row, list) or len(row) != 8 or not wire.integer(row[0], 1) or row[0] in seen\n",
             "        if (not isinstance(row, list) or len(row) != 8 or not wire.integer(row[0], 1)\n"),
        ],
    ),
    "editor_file_ops": (
        "engine/editor/asset_ops/editor_file_ops_controller.py",
        ["tests/test_editor_file_ops_case_only_rename.py", "tests/test_editor_file_ops_controller_contract.py",
         "tests/test_editor_file_ops_refactor_e2e.py", "tests/test_editor_file_ops_refactor_integration.py",
         "tests/test_editor_file_ops_rename_safety_618.py", "tests/test_safe_refactor_ops_rollback_matrix_contract.py"],
        [
            ("F1", "plan no longer refuses an occupied destination (the final move still refuses)",
             "            if os.path.lexists(dst) and not (case_only and _same_file(src, dst)):\n", "            if False:\n"),
            ("F2", "two items may be renamed to the same destination",
             "            if key in claimed:\n", "            if False:\n"),
            ("F3", "a folder may be moved inside itself",
             '            if f"{step.dst_rel}/".startswith(f"{step.src_rel}/"):\n', "            if False:\n"),
            ("F4", "names ending in a space or dot (Windows drops them) are accepted",
             '    if name.rstrip(" .") != name:\n', "    if False:\n"),
            ("F5", "the Windows final move overwrites (the #618 defect, os.rename -> os.replace)",
             "        os.rename(src, dst)  # MoveFileEx without REPLACE_EXISTING",
             "        os.replace(src, dst)  # MoveFileEx without REPLACE_EXISTING"),
        ],
    ),
}


# The quest survivors again, against a wider net: every test file with "quest" in its name or that imports a quest
# manager or quest_runtime (data/quests_wide_tests.txt, 69 files), to tell "untested" from "tested elsewhere".
GROUPS["quests_wide"] = (
    GROUPS["quests"][0],
    (Path(__file__).resolve().parent / "data" / "quests_wide_tests.txt").read_text(encoding="utf-8").split(),
    [m for m in GROUPS["quests"][2] if m[0] in ("Q1", "Q3", "Q4", "Q5")],
)

# The project_ops survivors against every test that calls set_solid / set_conversation / remove_entity, plus the Studio,
# MCP and AI-ops tests that mention "solid" or "once" (data/project_ops_wide_tests.txt).
GROUPS["project_ops_wide"] = (
    GROUPS["project_ops"][0],
    (Path(__file__).resolve().parent / "data" / "project_ops_wide_tests.txt").read_text(encoding="utf-8").split(),
    [m for m in GROUPS["project_ops"][2] if m[0] in ("O1", "O3", "O4")],
)

# The scene_room survivor against the HD-2D net tests, where levels are exercised.
GROUPS["scene_room_wide"] = (
    GROUPS["scene_room"][0],
    ["tests/test_mesh_net_hd2d.py", "tests/test_hd2d_same_level.py", "tests/test_mesh_net_lag_compensation.py"],
    [m for m in GROUPS["scene_room"][2] if m[0] == "N4"],
)


# E11 (#650): each named survivor and the one test that must kill it, as its own group (one mutant, one test).
_QG, _OA, _VP = ("tests/test_quest_progress_guards.py::", "tests/test_project_ops_authoring.py::",
                 "tests/test_vendor_purchase_integrity.py::")
E11: dict[str, tuple[str, str]] = {
    "Q1": ("quests", _QG + "test_a_stage_keyed_on_payload_value_completes_only_for_that_value"),
    "Q3": ("quests", _QG + "test_completing_a_completed_quest_pays_its_reward_once"),
    "Q5": ("quests", _QG + "test_complete_stage_leaves_a_stage_that_is_not_current_alone"),
    "O1": ("project_ops", _OA + "test_removing_an_object_that_is_not_there_is_refused"),
    "O3": ("project_ops", _OA + "test_unticking_solid_makes_the_object_passable_again"),
    "O4": ("project_ops", _OA + "test_unticking_only_once_stores_false"),
    "V1": ("vendor", _VP + "test_an_item_costing_exactly_your_gold_is_bought"),
    "V2": ("vendor", _VP + "test_an_out_of_stock_item_is_refused"),
    "V4": ("vendor", _VP + "test_selling_an_item_no_longer_carried_pays_nothing"),
}
for _mid, (_group, _test) in E11.items():
    GROUPS[f"e11_{_mid}"] = (GROUPS[_group][0], [_test], [m for m in GROUPS[_group][2] if m[0] == _mid])


def _anchor_error(module: str, text: str, mid: str, old_text: str) -> str | None:
    found = text.count(old_text)
    if found == 1:
        return None
    what = "anchor not found" if found == 0 else f"anchor matches {found} times"
    return f"ERROR: {mid}: {what} in {module} (refresh its text in mutation_probe.py)"


def _module_text(module: str) -> str:
    # (a Windows checkout with core.autocrlf: the table is written with LF, so compare with LF)
    return (REPO / module).read_bytes().decode("utf-8").replace("\r\n", "\n")


def check(name: str) -> int:
    """Every anchor of group ``name`` matches its module exactly once, and every test file exists; else exit 2."""
    module, tests, mutants = GROUPS[name]
    text = _module_text(module)
    errors = [e for mid, _w, old, _n in mutants if (e := _anchor_error(module, text, mid, old))]
    errors += [f"ERROR: test file not found: {t}" for t in tests if not (REPO / t.split("::")[0]).is_file()]
    for error in errors:
        print(error)
    return 2 if errors else 0


def apply(name: str, mid: str) -> int:
    """Write mutant ``mid`` of group ``name`` into its module (the driver restores the module afterwards)."""
    module, _tests, mutants = GROUPS[name]
    path = REPO / module
    if subprocess.run(["git", "diff", "--quiet", "--", module], cwd=REPO).returncode != 0:
        print(f"refusing: {module} has uncommitted changes")
        return 2
    text = path.read_bytes().decode("utf-8")
    for each, _what, old_text, new_text in mutants:
        if each == mid:
            if "\r\n" in text:  # (a Windows checkout with core.autocrlf: the table is written with \n)
                old_text, new_text = old_text.replace("\n", "\r\n"), new_text.replace("\n", "\r\n")
            if error := _anchor_error(module, text, mid, old_text):
                print(error)
                return 2
            path.write_bytes(text.replace(old_text, new_text, 1).encode("utf-8"))
            return 0
    print(f"no mutant {mid} in {name}")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", nargs=2, metavar=("GROUP", "MUTANT"))
    parser.add_argument("--plan", action="store_true", help="tab-separated: group, module, tests, mutant ids")
    parser.add_argument("--describe", nargs=2, metavar=("GROUP", "MUTANT"))
    parser.add_argument("--check", metavar="GROUP", help="exit 2 if an anchor or test file is stale ('all': every group)")
    args = parser.parse_args()
    if args.apply:
        return apply(*args.apply)
    if args.check:
        return max(check(name) for name in (GROUPS if args.check == "all" else [args.check]))
    if args.describe:
        group, mid = args.describe
        print(next(what for each, what, _o, _n in GROUPS[group][2] if each == mid))
        return 0
    for name, (module, tests, mutants) in GROUPS.items():
        if args.plan:
            print("	".join([name, module, " ".join(tests), " ".join(m[0] for m in mutants)]))
        else:
            print(f"{name:18} {module}  ({len(mutants)} mutants, {len(tests)} test files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
