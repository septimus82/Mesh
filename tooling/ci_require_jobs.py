"""The CI fan-in (H3, #422 F13): one OS's ``tests`` result is green only when every job it is made of succeeded.

Each OS's work runs as two parallel jobs, ``pytest (<os>, py3.11)`` (the full default suite) and ``verify (<os>,
py3.11)`` (verify-all, the release bundle and its strict verification, the artifacts). The ``tests (<os>, py3.11)``
job, the check reviews and merges look at, runs after both (``if: always()``) and calls this: it reads the run's
latest jobs from the GitHub API (``filter=latest``, so "re-run failed jobs" counts the jobs carried over from the
earlier attempt) and fails unless each required job is there and concluded ``success``. Failed, cancelled, skipped,
timed-out or missing jobs fail it, each named. (``needs.<job>.result`` can't tell one OS's leg of a matrix from the
other's; the jobs list can.) ``always()`` rather than ``!cancelled()`` on purpose: a cancelled run then gives a red
``tests``, never a skipped one, which branch protection would count as passing.

    python tooling/ci_require_jobs.py --os ubuntu-latest --python 3.11
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from typing import Any

COMPONENTS = ("pytest", "verify")


def required_jobs(os_name: str, python: str) -> list[str]:
    return [f"{part} ({os_name}, py{python})" for part in COMPONENTS]


def verdict(jobs: Iterable[Mapping[str, Any]], required: Iterable[str]) -> tuple[bool, list[str]]:
    """Whether every required job concluded ``success`` (and the lines that say so, or why not). A job listed more
    than once (a rerun) counts by its latest entry."""
    latest: dict[str, Mapping[str, Any]] = {}
    for entry in jobs:
        latest[str(entry.get("name"))] = entry
    ok, lines = True, []
    for name in required:
        job = latest.get(name)
        if job is None:
            ok = False
            lines.append(f"MISSING  {name}: not in this run")
            continue
        conclusion = job.get("conclusion") or job.get("status") or "unknown"
        good = conclusion == "success"
        ok &= good
        lines.append(f"{'ok      ' if good else 'FAILED  '}{name}: {conclusion}  {job.get('html_url', '')}".rstrip())
    return ok, lines


def _run_jobs(repo: str, run_id: str) -> list[dict[str, Any]]:
    out = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100",
                          "--jq", ".jobs[]"], check=True, capture_output=True, text=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--os", required=True, dest="os_name")
    parser.add_argument("--python", required=True)
    args = parser.parse_args(argv)
    required = required_jobs(args.os_name, args.python)
    jobs = _run_jobs(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"])
    ok, lines = verdict(jobs, required)
    print("\n".join(lines))
    print(f"tests ({args.os_name}, py{args.python}): {'all required jobs succeeded' if ok else 'NOT all required jobs succeeded'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
