"""S1-0 part C section 3: CI and Extended timing from GitHub history (data/ci_runs.tsv, data/ci_jobs.tsv, written by
fetch_ci_history.sh). Standard library only; reads nothing else.

    py -3.13 docs/s1/evidence/ci_timing_analysis.py [--last 30]

* Run wall time: the first job's creation to the last job's completion (attempt 1), so queueing counts.
* Job duration: started -> completed; queue: created -> started (attempt 1).
* Critical path: the job that completed last in each run.
* Job-minutes: the sum of every job's duration in a run (what the run costs in runner time).
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def ts(value: str) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value and value != "null" else None


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(q * (len(values) - 1))))
    return values[k]


def load():
    runs = {}
    with (DATA / "ci_runs.tsv").open(encoding="utf-8") as fh:
        for wf, rid, event, branch, conclusion, attempt, created, updated, sha in csv.reader(fh, delimiter="\t"):
            runs[rid] = dict(wf=wf, id=rid, event=event, branch=branch, conclusion=conclusion, attempt=int(attempt),
                             created=ts(created), updated=ts(updated), sha=sha)
    jobs = defaultdict(list)
    with (DATA / "ci_jobs.tsv").open(encoding="utf-8") as fh:
        for wf, rid, attempt, name, conclusion, created, started, completed in csv.reader(fh, delimiter="\t"):
            jobs[rid].append(dict(attempt=int(attempt), name=name, conclusion=conclusion, created=ts(created),
                                  started=ts(started), completed=ts(completed)))
    return runs, jobs


def minutes(a: datetime | None, b: datetime | None) -> float | None:
    return None if a is None or b is None else (b - a).total_seconds() / 60


def report(title: str, selected: list[dict], jobs: dict) -> None:
    print(f"\n## {title}: {len(selected)} runs "
          f"({selected[-1]['created']:%Y-%m-%d} .. {selected[0]['created']:%Y-%m-%d})" if selected else f"\n## {title}: none")
    if not selected:
        return
    per_job_dur: dict[str, list[float]] = defaultdict(list)
    per_job_queue: dict[str, list[float]] = defaultdict(list)
    walls, costs, last_jobs, conclusions = [], [], Counter(), Counter()
    for run in selected:
        js = [j for j in jobs.get(run["id"], []) if j["attempt"] == 1 and j["started"] and j["completed"]]
        conclusions[run["conclusion"]] += 1
        if not js:
            continue
        start = min(j["created"] or j["started"] for j in js)
        end = max(j["completed"] for j in js)
        walls.append(minutes(start, end))
        cost = 0.0
        for j in js:
            d = minutes(j["started"], j["completed"]) or 0.0
            if j["conclusion"] == "skipped":
                continue
            per_job_dur[j["name"]].append(d)
            q = minutes(j["created"], j["started"])
            if q is not None:
                per_job_queue[j["name"]].append(q)
            cost += d
        costs.append(cost)
        last_jobs[max(js, key=lambda j: j["completed"])["name"]] += 1
    print(f"conclusions: {dict(conclusions)}")
    print(f"wall (min): median {statistics.median(walls):.1f}, p90 {pct(walls, 0.9):.1f}, max {max(walls):.1f}")
    print(f"job-minutes per run: median {statistics.median(costs):.0f}, p90 {pct(costs, 0.9):.0f}")
    print(f"completed last (critical path): {dict(last_jobs.most_common(4))}")
    print(f"{'job':58} {'n':>3} {'med':>6} {'p90':>6} {'max':>6} {'queue med':>9} {'queue p90':>9}")
    for name in sorted(per_job_dur, key=lambda n: -statistics.median(per_job_dur[n])):
        d, q = per_job_dur[name], per_job_queue[name]
        print(f"{name[:58]:58} {len(d):>3} {statistics.median(d):6.1f} {pct(d, 0.9):6.1f} {max(d):6.1f} "
              f"{statistics.median(q) if q else 0:9.2f} {pct(q, 0.9) if q else 0:9.2f}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--last", type=int, default=30)
    args = parser.parse_args()
    runs, jobs = load()
    ordered = sorted(runs.values(), key=lambda r: r["created"], reverse=True)

    def pick(wf: str, event: str, integration: bool) -> list[dict]:
        out = [r for r in ordered if r["wf"] == wf and r["event"] == event
               and (r["branch"] == "redesign/visual-editor") == integration and r["conclusion"] != "cancelled"]
        return out[: args.last]

    report("CI, push to redesign/visual-editor", pick("ci.yml", "push", True), jobs)
    report("Extended, push to redesign/visual-editor", pick("extended.yml", "push", True), jobs)
    report("CI, pull requests from feature branches", pick("ci.yml", "pull_request", False), jobs)
    report("Extended, workflow_dispatch on feature branches", pick("extended.yml", "workflow_dispatch", False), jobs)

    # Re-run attempts and attempt-1 failures (flake candidates; classified by hand from the logs in the report)
    print("\n## runs with more than one attempt")
    for r in ordered:
        if r["attempt"] > 1:
            failed = sorted({j["name"] for j in jobs.get(r["id"], []) if j["attempt"] == 1 and j["conclusion"] == "failure"})
            print(f"{r['wf']:13} {r['id']} {r['event']:12} {r['branch'][:34]:34} a{r['attempt']} {r['conclusion']:8} a1 failed: {failed}")
    print("\n## attempt-1 job failures (excluding fan-ins)")
    fails = Counter()
    for r in ordered:
        for j in jobs.get(r["id"], []):
            if j["attempt"] == 1 and j["conclusion"] == "failure" and not j["name"].startswith(("tests (", "gpu (ubuntu-latest, py3.11)", "gpu (windows-latest, py3.11)")):
                fails[(r["wf"], r["event"], r["branch"] == "redesign/visual-editor")] += 1
    for (wf, event, integ), n in fails.items():
        print(f"{wf:13} {event:18} {'integration' if integ else 'feature':11} {n}")

    # The same tree tested twice: a feature PR's CI and the push run of its merge
    pushes = [r for r in ordered if r["wf"] == "ci.yml" and r["event"] == "push" and r["branch"] == "redesign/visual-editor"]
    prs = [r for r in ordered if r["wf"] == "ci.yml" and r["event"] == "pull_request" and r["branch"] != "redesign/visual-editor"]
    ext_disp = [r for r in ordered if r["wf"] == "extended.yml" and r["event"] == "workflow_dispatch"]
    print(f"\nwindow: {len(pushes)} CI pushes, {len(prs)} feature-PR CI runs, {len(ext_disp)} Extended dispatches on feature branches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
