"""F13-C (#422): CI's Windows full suite as deterministic shards, and the proof that together they ran it once.

Windows' ``pytest`` job ran the whole default suite (``not slow and not e2e``) serially, the longest job of every run.
It is now two jobs, ``pytest (windows-latest, py3.11, shard 1/2)`` and ``2/2``, each running whole test modules (so a
module's fixtures and test order stay together; ``tooling/ci_shards_plugin.py`` keeps them):

- the ``PINNED`` modules, the heaviest by measured duration, go to the shard that balances the two;
- every other module, present or new, goes to ``sha256(path) % shards + 1``: fixed, whatever else changes.

Each shard collects the whole suite, then keeps its own modules, and writes a record (``ci_shards_plugin``). The
Windows ``tests`` fan-in runs ``python3 tooling/ci_shards.py check`` on both records, which fails unless every
check in ``check`` holds: both shards finished and passed, on the same commit, the same collection and the same scheme;
each ran exactly its modules' tests, no test twice, none missing, every selected test with an outcome. Linux runs the
whole suite unsharded, as before.

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

SHARDS = 2  # (Windows; .github/workflows/ci.yml and tooling/ci_require_jobs.py name the same two jobs)
SCHEME = "f13c-1"  # (bump when the assignment rule changes: records of another scheme are refused)
RECORD_SCHEMA = 1
OK_OUTCOMES = ("passed", "skipped", "xfailed", "xpassed")  # (what lets an unsharded run pass too)
# The 20 heaviest modules of the default suite, each on the shard that balances the two given where the hash puts the
# rest. Measured at a06783c (local Windows 11, setup + call + teardown): 485 s in all; the hash alone gave the rest
# 102/142 s, with the pins 245/240 s. Re-measure and re-pin (bumping SCHEME) when the shards drift far apart.
PINNED: dict[str, int] = {
    "tests/test_authoring_session_discovery.py": 1,  # 51.8 s
    "tests/test_exported_game_locales.py": 2,  # 32.2 s
    "tests/test_cli_release_bundle_command.py": 1,  # 15.3 s
    "tests/test_studio_ai_base_revision.py": 1,  # 15.0 s
    "tests/test_export_bundle.py": 2,  # 12.8 s
    "tests/test_perf_run_thresholds.py": 1,  # 12.7 s
    "tests/test_cli_doctor_assets.py": 2,  # 11.2 s
    "tests/test_scatter_diagnostics_hash_seeds.py": 1,  # 9.8 s
    "tests/test_release_bundle_self_verify_contract.py": 2,  # 9.2 s
    "tests/test_logging_policy_contract.py": 1,  # 7.8 s
    "tests/test_test_lanes_contract.py": 2,  # 7.2 s
    "tests/test_cocreative_live_bridge.py": 1,  # 7.1 s
    "tests/test_perf_run_replay_report.py": 2,  # 7.1 s
    "tests/test_cocreative_proposal_inbox.py": 1,  # 6.5 s
    "tests/test_verify_all_reuse_bundle.py": 2,  # 6.3 s
    "tests/test_authoring_session.py": 2,  # 6.2 s
    "tests/test_generated_docs_freshness_contract.py": 1,  # 5.9 s
    "tests/test_version_single_source_policy.py": 1,  # 5.7 s
    "tests/test_no_direct_singleton_imports_policy.py": 2,  # 5.7 s
    "tests/test_verify_all_reuse.py": 1,  # 5.5 s
}


def module_of(nodeid: str) -> str:
    """The test module a test (or collected node) belongs to, as a repository-relative path."""
    return nodeid.split("::", 1)[0].replace("\\", "/")


def shard_of(module: str, shards: int = SHARDS) -> int:
    """The shard (1-based) that runs ``module``: its pinned shard, else one fixed by its path's SHA-256."""
    if shards == 1:
        return 1
    if shards == SHARDS and module in PINNED:
        return PINNED[module]
    return int(hashlib.sha256(module.encode("utf-8")).hexdigest(), 16) % shards + 1


def scheme_digest(shards: int) -> str:
    """What decides the assignment, as one digest: two records agree on it, or they weren't split the same way."""
    scheme = {"scheme": SCHEME, "shards": shards, "pinned": dict(sorted(PINNED.items())) if shards == SHARDS else {}}
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
          junit: dict[int, dict[str, int] | None] | None = None) -> tuple[list[str], dict[str, Any]]:
    """``(problems, summary)`` for the records of one run's shards: no problems only when, together, they ran the
    whole collected suite exactly once, every test with an outcome a whole run would pass with, on one commit and
    scheme. With ``junit`` (each shard's JUnit counts, ``junit_counts``), each shard's report must agree with its
    record."""
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
    expected_scheme = scheme_digest(shards)
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
        expected = sorted(nodeid for nodeid in collected if shard_of(module_of(nodeid), shards) == k)
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
            expected_counts = {"tests": len(outcomes) + skips, "failures": 0, "errors": 0,
                               "skipped": sum(1 for o in outcomes.values() if o in ("skipped", "xfailed")) + skips}
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
    outcomes_all: dict[str, str] = {}
    for record in by_shard.values():
        outcomes_all.update(_outcomes(record))
    summary = {
        "commit": first.get("commit"), "collected": len(collected), "selected": len(selected_all),
        "passed": sum(1 for o in outcomes_all.values() if o == "passed"),
        "skipped": sum(1 for o in outcomes_all.values() if o == "skipped"),
        "collection_skips": len(_ids(first, "collection_skips")),  # (each shard collects them: counted once)
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
    args = parser.parse_args(argv)
    records, problems = load_records(args.folder)
    reports = {path.stem.removeprefix("junit-"): path for path in args.folder.rglob("junit-*.xml")}
    junit = {r["shard"]: junit_counts(reports[str(r["shard"])]) if str(r.get("shard")) in reports else None
             for r in records if isinstance(r.get("shard"), int)}
    found, summary = check(records, shards=args.shards, commit=args.commit, junit=junit)
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
