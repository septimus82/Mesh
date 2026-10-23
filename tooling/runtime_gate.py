"""The runtime-validation gate: every real-window suite, one after another.

Unit tests can't see a light drawn in the wrong place or a sequence that never finishes; these
suites drive Mesh Studio in its real window and measure what the running engine does. They take
about 40 minutes and need the desktop, so they are not part of the quick test cycle. Run the gate
before merging, after any change to rendering, lighting, movement, scene loading or saving, and
at the end of a milestone:

    py -3.13 tooling/runtime_gate.py [--out DIR] [--only NAME ...] [--old PROJECT ...]

(MESH_GUI_AT / MESH_GUI_POLITE as for the GUI tests.) Each suite writes its report and screenshots
to DIR/<suite>; DIR/gate_summary.json lists every result. The exit code is 0 only if every suite
passed. Never run it at the same time as the pytest suite: both are heavy and the GUI tests time
out.

A failed suite is run once more: OS-level input is occasionally dropped (a click the window never
receives), and a second run tells that apart from a real failure. Both attempts are reported, and a
suite that only passed on its retry is marked FLAKY in the summary, never silently green.

The launcher suite opens copies of "older projects" (it checks the originals are untouched). Pass
them with --old; without it the gate uses ./mygame when present, else a freshly generated project,
which makes that one step weaker (said so in the summary).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUITES = [  # name, script, what it covers
    ("first_workflow", "acceptance_first_workflow.py", "Milestone 1: first creation workflow"),
    ("map_building", "acceptance_map_building.py", "Milestone 2: visual map building"),
    ("map_tools", "acceptance_map_tools.py", "Milestone 3: map tools"),
    ("launcher", "acceptance_launcher.py", "Milestone 4: launcher and templates"),
    ("event_authoring", "acceptance_event_authoring.py", "Milestone 5: visual event authoring"),
    ("ai_coauthoring", "acceptance_ai_coauthoring.py", "Milestone 6: human and AI co-authoring"),
    ("persistence", "acceptance_persistence.py", "Milestone 8: game state across rooms, saves and a restart"),
    ("lighting", "acceptance_lighting.py", "Milestone 10: lighting a game in Mesh Studio"),
    ("capability_lab", "capability_lab.py", "Milestone 7+: engine capabilities, measured"),
]
RESULT = re.compile(r"^(\d+)/(\d+) (?:steps|checks) passed", re.MULTILINE)


def older_projects(given: list[Path], out: Path) -> tuple[list[Path], str]:
    if given:
        return given, "given with --old"
    if (REPO / "mygame").is_dir():
        return [REPO / "mygame"], "./mygame (copied by the suite; checked unchanged)"
    sys.path.insert(0, str(REPO))
    from engine.project_scaffold import create_project

    generated = out / "generated_older_project"
    shutil.rmtree(generated, ignore_errors=True)
    create_project(generated, "Older Project", template_id="adventure")
    return [generated], "a freshly generated project (weaker: not really older)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "runtime_gate")
    parser.add_argument("--only", nargs="*", help="suite names: " + ", ".join(name for name, _, _ in SUITES))
    parser.add_argument("--old", type=Path, nargs="*", default=[], help="older projects for the launcher suite")
    parser.add_argument("--retries", type=int, default=1, help="reruns of a failed suite (default 1)")
    args = parser.parse_args()
    out: Path = args.out
    shutil.rmtree(out, ignore_errors=True)  # one reused folder: no pile of old runs
    out.mkdir(parents=True)
    summary: list[dict[str, object]] = []
    for name, script, about in SUITES:
        if args.only and name not in args.only:
            continue
        command = [sys.executable, str(REPO / "tooling" / script), "--out", str(out / name)]
        note = ""
        if name == "launcher":
            old, note = older_projects(args.old, out)
            command += ["--old", *map(str, old)]
        print(f"=== {name}: {about}", flush=True)
        attempts = []
        for attempt in range(1 + max(0, args.retries)):
            start = time.time()
            done = subprocess.run(command, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
            text = done.stdout + done.stderr
            (out / f"{name}{'' if attempt == 0 else f'.retry{attempt}'}.log").write_text(text, encoding="utf-8")
            found = RESULT.findall(text)
            passed, total = (int(found[-1][0]), int(found[-1][1])) if found else (0, 0)
            failures = [line for line in text.splitlines() if line.startswith(("[FAIL]", "[ERROR]"))]
            ok = done.returncode == 0 and bool(found) and passed == total
            attempts.append({"passed": passed, "total": total, "ok": ok, "failures": failures,
                             "minutes": round((time.time() - start) / 60, 1)})
            word = "PASS" if ok else "FAIL"
            print(f"    {word if attempt == 0 else 'retry: ' + word} {passed}/{total}" + (f"  ({note})" if note else ""), flush=True)
            for line in failures:
                print(f"    {line[:200]}", flush=True)
            if ok:
                break
            if (out / name).exists():  # keep the failed attempt's evidence beside the retry's
                shutil.move(str(out / name), str(out / f"{name}.attempt{attempt + 1}"))
        ok = attempts[-1]["ok"]
        summary.append({"suite": name, "about": about, "ok": ok, "flaky": ok and len(attempts) > 1,
                        "attempts": attempts, "note": note})
    (out / "gate_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    bad = [s["suite"] for s in summary if not s["ok"]]
    flaky = [s["suite"] for s in summary if s["flaky"]]
    print(f"gate: {len(summary) - len(bad)}/{len(summary)} suites passed" + (f"; failing: {', '.join(bad)}" if bad else "")
          + (f"; FLAKY (passed only on retry): {', '.join(flaky)}" if flaky else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
