"""F13-C (#422): CI's Windows full suite as deterministic shards, and the proof that together they ran it once.

Windows' ``pytest`` job ran the whole default suite (``not slow and not e2e``) serially, the longest job of every run.
It is now two jobs, ``pytest (windows-latest, py3.11, shard 1/2)`` and ``2/2``, each running whole test modules (so a
module's fixtures and test order stay together; ``tooling/ci_shards_plugin.py`` keeps them):

- the ``PINNED`` modules, the heaviest by measured duration, go to the shard that balances the two;
- every other module, present or new, goes to ``sha256(path) % shards + 1``: fixed, whatever else changes.

Each shard collects the whole suite, then keeps its own modules, and writes a record (``ci_shards_plugin``). The
Windows ``tests`` fan-in runs ``python3 tooling/ci_shards.py check`` on both records, which fails unless every
check in ``check`` holds: both shards finished and passed, on the same commit, the same collection and the same scheme;
each ran exactly its modules' tests, no test twice, none missing, every selected test with an outcome, and the suite
holds at least ``DEFAULT_MIN_SELECTED`` tests. Since S1 5.9 Linux's suite is split the same way into
``pytest (ubuntu-latest, py3.11, shard 1/2)`` and ``2/2`` (plan ``default``), and Windows' into three,
``pytest (windows-latest, py3.11, shard 1/3)``, ``2/3`` and ``3/3``, by a plan of its own (``default-windows``, as
the gpu lane's OSes have theirs); each OS's ``tests`` fan-in runs the same check on its records with its plan and count
(``check --shards 1`` still checks a whole run as one shard, ``--mesh-shard 1/1``).

The gpu lane (``extended.yml``) is split the same way on Windows, by its own plan (``--plan gpu``: its own pins, so the
default suite's balance and the gpu lane's never move each other), into three shards since S1 5.9 (``PLAN_SHARDS``):
``gpu (windows-latest, py3.11, shard 1/3)``, ``2/3`` and ``3/3``, each collecting the whole ``gl`` selection, and a
fan-in named ``gpu (windows-latest, py3.11)`` that runs ``check --plan gpu --shards 3 --min-selected N``: the same
checks, plus the lane's ``min_selected`` applied to the whole selection.
Linux's gpu lane (#422 CI-422B) is split the same way by a plan of its own, ``gpu-linux`` (``--shard-plan gpu-linux``):
Linux's module costs aren't Windows' (the slowest Linux modules include one Windows' plan leaves to the hash), so each
OS's pins come from its own lane's timings and neither moves the other. Its fan-in is ``gpu (ubuntu-latest, py3.11)``.

Standard library only: the fan-in runs it with the runner's own ``python3``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

SHARDS = 2  # (the default split; a plan with another count says so in PLAN_SHARDS, e.g. Windows' default suite: 3)
# The default suite's floor (#648): CI's checks of it on both OSes (``check --min-selected``: each OS's fan-in over its
# two shards) fail when it collects fewer tests, so a conftest, marker or collection
# change that drops most of the suite turns CI red instead of green. Set just under the measured collection (13,979 at
# 721bd909, both OSes); tests/test_test_lanes_contract.py keeps it within 5% of what the suite collects. A legitimate
# test removal lowers it on purpose, in the same PR; growth past 5% raises it there too.
DEFAULT_MIN_SELECTED = 14_000
SCHEME = "f13c-2"  # (bump when the assignment rule changes: records of another scheme are refused; 2: S1 5.9's re-pin)
RECORD_SCHEMA = 1
OK_OUTCOMES = ("passed", "skipped", "xfailed", "xpassed")  # (what lets an unsharded run pass too)
# The 20 heaviest modules of the default suite, each on the shard that balances the two given where the hash puts the
# rest (S1 5.9). Measured on CI's Windows shards, the mean of 6 green push runs 45797221746-45839494752 (setup + call +
# teardown): 1,311 s in all, 1,944 modules; the hash alone gave the rest 348/397 s, with the pins 659/652 s (the old
# pins, from a06783c, had drifted to 577/733). Since Windows' suite has its own plan (``default-windows``, below), these
# pins split only Linux's two shards. Re-measure and re-pin (bumping SCHEME) when the shards drift far apart.
PINNED: dict[str, int] = {
    "tests/test_studio_project_ownership.py": 1,  # 53.5 s
    "tests/test_stale_plan_undo.py": 2,  # 52.9 s
    "tests/test_mcp_project_ownership.py": 1,  # 48.4 s
    "tests/test_authoring_session_discovery.py": 2,  # 46.8 s
    "tests/test_baseline_growth.py": 1,  # 32.0 s
    "tests/test_cli_write_guard.py": 1,  # 29.6 s
    "tests/test_cli_new_force_safety.py": 2,  # 28.3 s
    "tests/test_studio_object_identity.py": 1,  # 27.8 s
    "tests/test_mesh_net_prediction.py": 2,  # 27.7 s
    "tests/test_live_bridge_request_states.py": 1,  # 26.8 s
    "tests/test_exported_game_locales.py": 2,  # 26.6 s
    "tests/test_mesh_net_burst.py": 1,  # 22.8 s
    "tests/test_replay_tick_sample_pooling.py": 2,  # 21.7 s
    "tests/test_ai_write_paths.py": 1,  # 19.8 s
    "tests/test_legacy_file_ops_real_window.py": 2,  # 19.4 s
    "tests/test_water_passable.py": 1,  # 18.2 s
    "tests/test_export_bundle_replacement.py": 2,  # 16.7 s
    "tests/test_studio_ai_base_revision.py": 1,  # 16.2 s
    "tests/test_mesh_net_owed.py": 2,  # 15.3 s
    "tests/test_logging_policy_contract.py": 1,  # 15.3 s
}

# Windows' default suite (ci.yml's ``pytest (windows-latest, py3.11, shard K/3)``, ``--mesh-shard-plan
# default-windows``): three shards since S1 5.9's follow-up, its 30 heaviest modules pinned to balance the three given
# where the hash puts the rest. Measured on CI's Windows shards, the mean of 10 push runs 45867895620-45910493881
# (setup + call + teardown): 1,369 s in all, 1,955 modules; the hash alone gave the rest 214/254/158 s, with the pins
# 456/456/457 s (each run's three within 45 s of each other). Two shards ran 588-892 s each, CI's slowest jobs.
# Re-measure and re-pin (bumping SCHEME) when the shards drift far apart.
DEFAULT_WINDOWS_PINNED: dict[str, int] = {
    "tests/test_baseline_growth.py": 3,  # 56.8 s
    "tests/test_studio_project_ownership.py": 1,  # 49.2 s
    "tests/test_authoring_session_discovery.py": 3,  # 47.5 s
    "tests/test_mcp_project_ownership.py": 2,  # 46.6 s
    "tests/test_stale_plan_undo.py": 3,  # 46.4 s
    "tests/test_replay_tick_sample_pooling.py": 1,  # 41.9 s
    "tests/test_cli_write_guard.py": 2,  # 31.1 s
    "tests/test_studio_object_identity.py": 1,  # 29.5 s
    "tests/test_exported_game_locales.py": 3,  # 27.7 s
    "tests/test_live_bridge_request_states.py": 2,  # 27.0 s
    "tests/test_cli_new_force_safety.py": 1,  # 25.2 s
    "tests/test_mesh_net_prediction.py": 3,  # 24.4 s
    "tests/test_mesh_net_burst.py": 2,  # 22.8 s
    "tests/test_ai_write_paths.py": 1,  # 21.0 s
    "tests/test_replay_digest_scoping.py": 3,  # 19.7 s
    "tests/test_water_passable.py": 3,  # 19.4 s
    "tests/test_legacy_file_ops_real_window.py": 1,  # 18.6 s
    "tests/test_mesh_net_characters.py": 2,  # 18.5 s
    "tests/test_logging_policy_contract.py": 2,  # 16.0 s
    "tests/test_export_bundle.py": 1,  # 15.7 s
    "tests/test_studio_ai_base_revision.py": 3,  # 15.3 s
    "tests/test_mesh_net_world.py": 1,  # 15.3 s
    "tests/test_picker_behaviour_contract.py": 2,  # 15.1 s
    "tests/test_export_bundle_replacement.py": 3,  # 15.0 s
    "tests/test_cli_release_bundle_command.py": 1,  # 14.2 s
    "tests/test_mesh_net_combat.py": 2,  # 13.9 s
    "tests/test_mesh_net_owed.py": 3,  # 13.2 s
    "tests/test_version_single_source_policy.py": 3,  # 12.9 s
    "tests/test_project_scaffolding_data.py": 2,  # 11.8 s
    "tests/test_studio_undo_history_sharing.py": 1,  # 11.6 s
}


# The gpu lane's (``python -m tooling.test_tiers --shard K/3 gpu``): three shards since S1 5.9, its 30 heaviest modules
# pinned to balance the three given where the hash puts the rest. Measured on CI's Windows gpu lane (Mesa llvmpipe), the
# mean of 6 green Extended push runs 45797221431-45839494580 (setup + call + teardown): 3,530 s in all, 91 modules; the
# hash alone gave the rest 259/153/239 s, with the pins 1,175/1,178/1,177 s (each run's three within 67 s of each
# other). Two shards balanced too (1,738/1,791 s), but runners differ by up to 0.74-1.19x per job, which left the
# heavier of two near Extended's 40-minute limit at p90. The 5.7 (ii) HD-2D e2e leg is pinned to the lightest shard.
# Re-measure and re-pin (bumping SCHEME) when the shards drift far apart.
GPU_PINNED: dict[str, int] = {
    "tests/test_terrain_gpu.py": 2,  # 306.7 s
    "tests/test_hd2d_lighting_controls_gpu.py": 3,  # 222.0 s
    "tests/test_water_gpu.py": 1,  # 183.6 s
    "tests/test_mesh_net_hd2d_gpu.py": 1,  # 182.4 s
    "tests/test_dialogue_reopen_gpu.py": 2,  # 163.0 s
    "tests/test_fire_gpu.py": 3,  # 163.0 s
    "tests/test_studio_panel_scroll_gpu.py": 2,  # 153.7 s
    "tests/test_weather_authoring_gpu.py": 3,  # 143.8 s
    "tests/test_hd2d_m1b_scene_gpu.py": 1,  # 112.7 s
    "tests/test_scatter_gpu.py": 1,  # 104.2 s
    "tests/test_hd2d_bloom_gpu.py": 3,  # 92.4 s
    "tests/test_hd2d_asset_pipeline_gpu.py": 2,  # 86.1 s
    "tests/test_mesh_net_gpu.py": 1,  # 83.4 s
    "tests/test_river_falls_gpu.py": 3,  # 78.7 s
    "tests/test_hd2d_starter_gpu.py": 2,  # 77.6 s
    "tests/test_hd2d_haze_gpu.py": 1,  # 71.2 s
    "tests/test_hd2d_post_gpu.py": 3,  # 64.4 s
    "tests/test_weather_collisions_gpu.py": 2,  # 60.9 s
    "tests/test_studio_3d_selection_gpu.py": 1,  # 54.5 s
    "tests/test_hd2d_studio_gpu.py": 2,  # 54.0 s
    "tests/test_studio_workflow_polish_gpu.py": 3,  # 52.2 s
    "tests/test_river_tool_gpu.py": 1,  # 47.7 s
    "tests/test_river_gpu.py": 2,  # 46.3 s
    "tests/test_studio_workspace_gpu.py": 3,  # 44.3 s
    "tests/test_indoor_weather_gpu.py": 1,  # 41.5 s
    "tests/test_water_passable_gpu.py": 3,  # 39.8 s
    "tests/test_room_file_ownership_gpu.py": 2,  # 39.5 s
    "tests/test_start_room_music_gpu.py": 3,  # 36.7 s
    "tests/test_dof_studio_gpu.py": 1,  # 34.8 s
    "tests/test_room_transition_gl_lifetime_gpu.py": 2,  # 31.2 s
    "tests/test_e2e_creator_workflow.py": 2,  # 6.4 s (5.7 ii: the lightest shard without it, 1,172 s)
}
# Linux's gpu lane (``--shard 1/2 --shard-plan gpu-linux gpu``, #422 CI-422B): its 12 heaviest modules, pinned to balance
# the two given where the hash puts the rest. Measured on CI's Linux gpu lane (Xvfb + Mesa llvmpipe), the mean of 7
# green Extended runs at 1d11670-af380e7 on 5 CPU models (EPYC 9V45/9V74/7763, Xeon 8370C/6973P-C; setup + call +
# teardown): 1,129-1,863 s in all, 66 modules; the hash alone gave the rest 191/290 s, with the pins 767/767 s (each run
# within 3% of even). Re-measure and re-pin (bumping SCHEME) when the shards drift far apart. (S1 5.9 left these pins:
# Linux's gpu shards, at 913/816 s on the same 6 runs, are far off Extended's critical path; it only pinned the 5.7 (ii)
# HD-2D e2e leg to the lighter shard.)
GPU_LINUX_PINNED: dict[str, int] = {
    "tests/test_dialogue_reopen_gpu.py": 1,  # 176.4 s
    "tests/test_hd2d_lighting_controls_gpu.py": 1,  # 169.4 s
    "tests/test_terrain_gpu.py": 1,  # 163.4 s
    "tests/test_fire_gpu.py": 2,  # 81.5 s
    "tests/test_studio_workflow_polish_gpu.py": 2,  # 73.7 s
    "tests/test_weather_authoring_gpu.py": 2,  # 72.3 s
    "tests/test_water_gpu.py": 1,  # 67.7 s
    "tests/test_hd2d_asset_pipeline_gpu.py": 2,  # 59.6 s
    "tests/test_scatter_gpu.py": 2,  # 56.6 s
    "tests/test_hd2d_starter_gpu.py": 2,  # 49.9 s
    "tests/test_hd2d_post_gpu.py": 2,  # 48.5 s
    "tests/test_hd2d_studio_gpu.py": 2,  # 35.4 s
    "tests/test_e2e_creator_workflow.py": 2,  # 3.4 s (5.7 ii, the lighter shard)
}
# Each split's pins, by plan name: ``default`` is the default suite's on Linux and ``default-windows`` on Windows
# (ci.yml), ``gpu`` Windows' gpu lane's and ``gpu-linux`` Linux's (extended.yml).
PLANS: dict[str, dict[str, int]] = {"default": PINNED, "default-windows": DEFAULT_WINDOWS_PINNED, "gpu": GPU_PINNED,
                                    "gpu-linux": GPU_LINUX_PINNED}
# How many shards each plan's pins are for (its workflow's matrix and fan-in ``--shards``): a plan's pins apply only at
# its own count; split any other way, every module goes by the hash.
PLAN_SHARDS: dict[str, int] = {"default": SHARDS, "default-windows": 3, "gpu": 3, "gpu-linux": SHARDS}


def module_of(nodeid: str) -> str:
    """The test module a test (or collected node) belongs to, as a repository-relative path."""
    return nodeid.split("::", 1)[0].replace("\\", "/")


def shard_of(module: str, shards: int = SHARDS, plan: str = "default") -> int:
    """The shard (1-based) that runs ``module``: its pinned shard in ``plan``, else one fixed by its path's SHA-256."""
    if shards == 1:
        return 1
    pinned = PLANS[plan]
    if shards == PLAN_SHARDS[plan] and module in pinned:
        return pinned[module]
    return int(hashlib.sha256(module.encode("utf-8")).hexdigest(), 16) % shards + 1


def scheme_digest(shards: int, plan: str = "default") -> str:
    """What decides the assignment, as one digest: two records agree on it, or they weren't split the same way. (The
    plans' pins differ, so their digests do; the default plan's is what it was before plans.)"""
    scheme = {"scheme": SCHEME, "shards": shards,
              "pinned": dict(sorted(PLANS[plan].items())) if shards == PLAN_SHARDS[plan] else {}}
    return hashlib.sha256(json.dumps(scheme, sort_keys=True).encode("utf-8")).hexdigest()


def ids_digest(ids: list[str]) -> str:
    """One digest for a set of test ids, whatever their order."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def normalize(nodeid: str, root: str) -> str:
    """A test id with its checkout's absolute path (some parametrize over files) written as ``<repo>``, in any of the
    forms an id holds it: with either separator, or with backslashes escaped (pytest's ids double them)."""
    back = root.replace("/", "\\")
    for form in (back.replace("\\", "\\\\"), back, root.replace("\\", "/")):
        if form:
            nodeid = nodeid.replace(form, "<repo>")
    return nodeid


def _ids(record: dict[str, Any], key: str) -> list[str]:
    value = record.get(key)
    return [str(v) for v in value] if isinstance(value, list) else []


def _outcomes(record: dict[str, Any]) -> dict[str, str]:
    value = record.get("outcomes")
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


def check(records: list[dict[str, Any]], *, shards: int = SHARDS, commit: str | None = None,
          junit: dict[int, dict[str, int] | None] | None = None, plan: str = "default",
          min_selected: int = 0) -> tuple[list[str], dict[str, Any]]:
    """``(problems, summary)`` for the records of one run's shards: no problems only when, together, they ran the
    whole collected suite exactly once, every test with an outcome a whole run would pass with, on one commit and
    ``plan``'s scheme, and the suite holds at least ``min_selected`` tests (a lane's floor, for the whole of it). With
    ``junit`` (each shard's JUnit counts, ``junit_counts``), each shard's report must agree with its record. Skipped
    tests pass, as in an unsharded run, and the summary lists each."""
    if plan not in PLANS:
        return [f"no shard plan named {plan!r}"], {}
    problems: list[str] = []
    by_shard: dict[int, dict[str, Any]] = {}
    for record in records:
        shard = record.get("shard")
        if not isinstance(shard, int) or not 1 <= shard <= shards:
            problems.append(f"a record names no shard of {shards}: {shard!r}")
        elif shard in by_shard:
            problems.append(f"two records for shard {shard}/{shards}")
        else:
            by_shard[shard] = record
    missing = [k for k in range(1, shards + 1) if k not in by_shard]
    if missing:
        problems.append(f"no record from shard(s) {', '.join(f'{k}/{shards}' for k in missing)}: missing, cancelled "
                        "or stopped before it finished")
    if problems:
        return problems, {}
    expected_scheme = scheme_digest(shards, plan)
    first = by_shard[1]
    collected = _ids(first, "collected")
    for k, record in sorted(by_shard.items()):
        label = f"shard {k}/{shards}"
        if record.get("schema") != RECORD_SCHEMA or record.get("complete") is not True:
            problems.append(f"{label}: its record is incomplete or of another format")
            continue
        if record.get("shards") != shards:
            problems.append(f"{label}: split into {record.get('shards')} shards, not {shards}")
        if record.get("exitstatus") != 0:
            problems.append(f"{label}: pytest exited {record.get('exitstatus')}")
        if commit and record.get("commit") != commit:
            problems.append(f"{label}: ran commit {record.get('commit')}, this run is {commit}")
        if record.get("commit") != first.get("commit"):
            problems.append(f"{label}: ran commit {record.get('commit')}, shard 1/{shards} {first.get('commit')}")
        if record.get("scheme_digest") != expected_scheme:
            problems.append(f"{label}: assigned modules by another scheme")
        own = _ids(record, "collected")
        if record.get("collected_digest") != ids_digest(own):
            problems.append(f"{label}: its collection list doesn't match its own digest")
        if ids_digest(own) != ids_digest(collected) or record.get("collection_skips") != first.get("collection_skips"):
            problems.append(f"{label}: collected a different suite from shard 1/{shards}")
        selected = _ids(record, "selected")
        if len(set(selected)) != len(selected):
            problems.append(f"{label}: selected a test twice")
        expected = sorted(nodeid for nodeid in collected if shard_of(module_of(nodeid), shards, plan) == k)
        if sorted(selected) != expected:
            problems.append(f"{label}: ran {len(selected)} tests, its modules hold {len(expected)}")
        outcomes = _outcomes(record)
        without = sorted(set(selected) - set(outcomes))
        if without:
            problems.append(f"{label}: {len(without)} selected test(s) have no outcome, e.g. {without[0]}")
        extra = sorted(set(outcomes) - set(selected))
        if extra:
            problems.append(f"{label}: outcomes for {len(extra)} test(s) it didn't select, e.g. {extra[0]}")
        failed = sorted(nodeid for nodeid, outcome in outcomes.items() if outcome not in OK_OUTCOMES)
        if failed:
            problems.append(f"{label}: {len(failed)} test(s) didn't pass, e.g. {failed[0]} ({outcomes[failed[0]]})")
        if junit is not None:
            counts = junit.get(k)
            skips = len(_ids(record, "collection_skips"))
            raw = record.get("subtests")
            sub: dict[str, int] = {str(k): int(n) for k, n in raw.items()} if isinstance(raw, dict) else {}
            expected_counts = {"tests": len(outcomes) + skips + sum(sub.values()), "failures": 0, "errors": 0,
                               "skipped": sum(1 for o in outcomes.values() if o in ("skipped", "xfailed"))
                               + skips + sub.get("skipped", 0)}
            if counts is None:
                problems.append(f"{label}: no JUnit report")
            elif counts != expected_counts:
                problems.append(f"{label}: its JUnit report says {counts}, its record {expected_counts}")
    selected_all = [nodeid for record in by_shard.values() for nodeid in _ids(record, "selected")]
    twice = sorted(nodeid for nodeid, n in Counter(selected_all).items() if n > 1)
    if twice:
        problems.append(f"{len(twice)} test(s) ran in more than one shard, e.g. {twice[0]}")
    absent = sorted(set(collected) - set(selected_all))
    if absent:
        problems.append(f"{len(absent)} collected test(s) ran in no shard, e.g. {absent[0]}")
    if len(collected) < min_selected:
        problems.append(f"the shards' suite holds {len(collected)} tests, fewer than the {min_selected} it should")
    outcomes_all: dict[str, str] = {}
    for record in by_shard.values():
        outcomes_all.update(_outcomes(record))
    summary = {
        "plan": plan, "commit": first.get("commit"), "collected": len(collected), "selected": len(selected_all),
        "passed": sum(1 for o in outcomes_all.values() if o == "passed"),
        "skipped": sum(1 for o in outcomes_all.values() if o == "skipped"),
        "collection_skips": len(_ids(first, "collection_skips")),  # (each shard collects them: counted once)
        "skipped_tests": sorted(n for n, o in outcomes_all.items() if o in ("skipped", "xfailed")),
        "shards": {f"{k}/{shards}": {"tests": len(_ids(r, "selected")),
                                      "seconds": round(sum((r.get("durations") or {}).values()), 1)}
                   for k, r in sorted(by_shard.items())},
    }
    return problems, summary


def junit_counts(path: Path) -> dict[str, int] | None:
    """A JUnit report's test, failure, error and skip counts (summed over its suites); None when it can't be read."""
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return None
    return {key: sum(int(suite.get(key) or 0) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}


def load_records(folder: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Every ``shard-*.json`` record under ``folder``; unreadable ones are problems, not skipped."""
    records: list[dict[str, Any]] = []
    problems: list[str] = []
    for path in sorted(folder.rglob("shard-*.json")) if folder.is_dir() else []:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name} can't be read ({exc})")
            continue
        if isinstance(loaded, dict):
            records.append(loaded)
        else:
            problems.append(f"{path.name} isn't a shard record")
    return records, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that a run's shards together ran the whole suite once.")
    sub = parser.add_subparsers(dest="command", required=True)
    run_check = sub.add_parser("check", help="Check the shard records in a folder (the Windows fan-in).")
    run_check.add_argument("folder", type=Path)
    run_check.add_argument("--shards", type=int, default=SHARDS)
    run_check.add_argument("--commit", default=None, help="The commit this run tested (GITHUB_SHA).")
    run_check.add_argument("--plan", default="default", choices=sorted(PLANS),
                           help="Whose split: default, default-windows, gpu or gpu-linux.")
    run_check.add_argument("--min-selected", type=int, default=0, help="The lane's floor, for the whole suite.")
    args = parser.parse_args(argv)
    records, problems = load_records(args.folder)
    reports = {path.stem.removeprefix("junit-"): path for path in args.folder.rglob("junit-*.xml")}
    junit = {r["shard"]: junit_counts(reports[str(r["shard"])]) if str(r.get("shard")) in reports else None
             for r in records if isinstance(r.get("shard"), int)}
    found, summary = check(records, shards=args.shards, commit=args.commit, junit=junit, plan=args.plan,
                           min_selected=args.min_selected)
    problems += found
    for line in problems:
        print(f"FAILED  {line}")
    if summary:
        print(json.dumps(summary, indent=1, sort_keys=True))
    print("[Mesh][Shards] " + ("OK: the shards ran the whole suite, each test once" if not problems else
                               f"REFUSED: {len(problems)} problem(s)"))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
