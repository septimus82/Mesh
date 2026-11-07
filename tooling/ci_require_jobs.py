"""The CI fan-in (H3, #422 F13): one OS's ``tests`` result is green only when every job it is made of succeeded.

Each OS's work runs as parallel jobs: ``pytest (<os>, py3.11)`` (the full default suite; on Windows, since F13-C,
two shard jobs ``pytest (windows-latest, py3.11, shard 1/2)`` and ``2/2``), ``verify (<os>, py3.11)``
(verify-all, the release bundle and its strict verification, the artifacts) and, since H5, ``installed (<os>,
py3.11)`` (this commit's wheel installed and run outside the checkout) and, since H6, ``acceptance (<os>, py3.11)``
(the creator-workflow GL tests). The ``tests (<os>, py3.11)`` job, the check
reviews and merges look at, runs after them (``if: always()``) and calls this: it reads the run's
latest jobs from the GitHub API (``filter=latest``, so "re-run failed jobs" counts the jobs carried over from the
earlier attempt) and fails unless each required job is there and concluded ``success``. Failed, cancelled, skipped,
timed-out or missing jobs fail it, each named. (``needs.<job>.result`` can't tell one OS's leg of a matrix from the
other's; the jobs list can.) ``always()`` rather than ``!cancelled()`` on purpose: a cancelled run then gives a red
``tests``, never a skipped one, which branch protection would count as passing. The list is read again, a bounded
number of times, until one read is complete and current (see ``check``): a single read was wrong during a GitHub
incident (H7).
One read can stay stale for minutes, though: GitHub listed both of extended.yml's Windows gpu shards as "in_progress" for
over 4 minutes after they had finished, while the fan-in was already running because of them (#468's Extended run
41875533588). So the fan-in also reads the workflow engine's own word, ``NEEDS_RESULTS`` (``toJSON(needs.*.result)``):
when every job it ``needs:`` succeeded, every leg of those matrices did, so a required job the list names, from this
attempt, but still calls queued or running is taken as succeeded (see ``observe``). Nothing else changes: a missing job,
a finished one that didn't succeed, an older attempt's entry or an incomplete list still waits or fails as before.

    python tooling/ci_require_jobs.py --os ubuntu-latest --python 3.11

Another fan-in names its jobs itself (extended.yml's Windows gpu shards, #422 F13):

    python tooling/ci_require_jobs.py --job "gpu (windows-latest, py3.11, shard 1/2)" --job "..." --name "gpu (...)"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

COMPONENTS = ("pytest", "verify", "installed", "acceptance")
# F13-C: an OS whose ``pytest`` runs as shards, one job each (``tooling/ci_shards.py`` SHARDS; ci.yml's matrix).
SHARDED = {"windows-latest": 2}


def required_jobs(os_name: str, python: str) -> list[str]:
    names = []
    for part in COMPONENTS:
        shards = SHARDED.get(os_name, 0) if part == "pytest" else 0
        names += [f"{part} ({os_name}, py{python}, shard {k}/{shards})" for k in range(1, shards + 1)] or [
            f"{part} ({os_name}, py{python})"]
    return names


def verdict(jobs: Iterable[Mapping[str, Any]], required: Iterable[str]) -> tuple[bool, list[str]]:
    """Whether every required job concluded ``success`` (and the lines that say so, or why not). A job listed more
    than once (a rerun) counts by its newest attempt (``run_attempt``; the later entry when that's equal), so an older
    success never hides a newer failure."""
    latest: dict[str, tuple[int, int, Mapping[str, Any]]] = {}
    for position, entry in enumerate(jobs):
        key = (int(entry.get("run_attempt") or 0), position)
        name = str(entry.get("name"))
        if name not in latest or key > latest[name][:2]:
            latest[name] = (*key, entry)
    ok, lines = True, []
    for name in required:
        found = latest.get(name)
        if found is None:
            ok = False
            lines.append(f"MISSING  {name}: not in this run")
            continue
        job = found[2]
        conclusion = job.get("conclusion") or job.get("status") or "unknown"
        good = conclusion == "success"
        ok &= good
        lines.append(f"{'ok      ' if good else 'FAILED  '}{name}: {conclusion}  {job.get('html_url', '')}".rstrip())
    return ok, lines


# H7 (#422): the jobs list GitHub returns can be wrong for a while (an Actions incident gave HTTP 5xx, jobs still
# "in_progress" after needs: had finished, and lists missing finished jobs), so one read is not trusted. Each read is a
# whole snapshot; the verdict is always one snapshot's, never successes pieced together from several. A snapshot
# decides only when it is complete (as many jobs as its total_count) and current (every required job from this run
# attempt and finished); otherwise it is read again, a bounded number of times, and then the check fails, saying why.
DELAYS = (5, 10, 20, 30, 30)  # seconds between reads: 6 reads, ~95 s of waiting, inside the job's 10-minute limit
TIMEOUT = 30  # seconds per request
_SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})")


class FetchError(Exception):
    """A read of the jobs list that failed (the message is safe to print)."""


def _sanitized(text: str) -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        text = text.replace(token, "***")
    return _SECRET.sub("***", " ".join(text.split()))[-400:]


def fetch_jobs(repo: str, run_id: str, *, timeout: float = TIMEOUT,
               run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> tuple[list[dict[str, Any]], int]:
    """One snapshot of the run's latest jobs: (jobs, the total_count GitHub reported), page by page, each request
    limited to ``timeout`` seconds. Raises FetchError naming what went wrong."""
    jobs: list[dict[str, Any]] = []
    total = 0
    for page in range(1, 11):
        url = f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100&page={page}"
        try:
            proc = run(["gh", "api", url], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise FetchError(f"no answer within {timeout:g} s (page {page})") from None
        if proc.returncode != 0:
            raise FetchError(f"gh api failed (exit {proc.returncode}, page {page}): "
                             f"{_sanitized(proc.stderr or proc.stdout) or 'no output'}")
        try:
            body = json.loads(proc.stdout)
            total, batch = int(body["total_count"]), list(body["jobs"])
        except (ValueError, KeyError, TypeError) as exc:
            raise FetchError(f"unreadable answer (page {page}): {type(exc).__name__}: "
                             f"{_sanitized(proc.stdout) or 'empty'}") from None
        jobs += batch
        if not batch or len(jobs) >= total:
            break
    return jobs, total


def needs_succeeded(raw: str | None) -> bool:
    """Whether ``NEEDS_RESULTS`` (a JSON list, ``toJSON(needs.*.result)``) says every needed job succeeded. Anything
    else, absent or unreadable included, is False: then only the jobs list decides, as before."""
    try:
        results = json.loads(raw or "")
    except ValueError:
        return False
    return isinstance(results, list) and bool(results) and all(r == "success" for r in results)


def _vouched(jobs: list[dict[str, Any]], required: list[str]) -> list[dict[str, Any]]:
    """The snapshot with each required job listed but not yet ``completed`` taken as succeeded: only for when every
    ``needs:`` job succeeded, so the list is stale (see the docstring). An entry from an earlier attempt keeps its
    ``run_attempt``, so ``observe`` still reads again for it."""
    return [{**job, "status": "completed", "conclusion": "success",
             "html_url": f"(listed as {job.get('status')}; needs: says it succeeded) {job.get('html_url', '')}".rstrip()}
            if str(job.get("name")) in required and job.get("status") != "completed" else job
            for job in jobs]


def observe(jobs: list[dict[str, Any]], total: int, required: list[str], attempt: int,
            needs_ok: bool = False) -> tuple[str, list[str]]:
    """What one snapshot says: ("pass" | "fail" | "retry", lines). It decides ("pass"/"fail") only when it is complete
    and current; a finished required job that didn't succeed fails it then and there. ``needs_ok``: every ``needs:``
    job succeeded, so a required job still listed as running from this attempt did succeed."""
    if needs_ok:
        jobs = _vouched(jobs, required)
    waiting: list[str] = []
    if len(jobs) != total:
        waiting.append(f"incomplete list: {len(jobs)} of {total} jobs")
    newest: dict[str, dict[str, Any]] = {}
    for job in jobs:
        name = str(job.get("name"))
        if name not in newest or int(job.get("run_attempt") or 0) >= int(newest[name].get("run_attempt") or 0):
            newest[name] = job
    for name in required:
        listed = newest.get(name)
        if listed is None:
            waiting.append(f"{name} not listed")
        elif listed.get("status") != "completed":
            waiting.append(f"{name} still {listed.get('status')}")
        elif attempt and int(listed.get("run_attempt") or 0) < attempt:
            waiting.append(f"{name} listed from attempt {listed.get('run_attempt')}, not this attempt ({attempt})")
    ok, lines = verdict(jobs, required)
    if waiting:
        return "retry", waiting
    return ("pass" if ok else "fail"), lines


def check(fetch: Callable[[], tuple[list[dict[str, Any]], int]], required: list[str], attempt: int, *,
          needs_ok: bool = False, delays: tuple[float, ...] = DELAYS, sleep: Callable[[float], None] = time.sleep,
          log: Callable[[str], None] = lambda line: print(line, flush=True)) -> tuple[bool, list[str]]:
    """Read snapshots until one decides, at most ``len(delays) + 1`` reads: (passed, the deciding lines or why none
    decided)."""
    reason: list[str] = []
    for read in range(len(delays) + 1):
        try:
            state, lines = observe(*fetch(), required, attempt, needs_ok)
        except FetchError as exc:
            state, lines = "retry", [f"read failed: {exc}"]
        if state != "retry":
            return state == "pass", lines
        reason = lines
        if read < len(delays):
            log(f"read {read + 1}/{len(delays) + 1} not usable ({'; '.join(lines)}); reading again in {delays[read]:g} s")
            sleep(delays[read])
    return False, [f"no complete, current jobs list after {len(delays) + 1} reads; the last one: {'; '.join(reason)}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--os", dest="os_name")
    parser.add_argument("--python")
    parser.add_argument("--job", action="append", default=[], help="A required job by name (instead of --os/--python)")
    parser.add_argument("--name", default=None, help="This fan-in's name, for its verdict line (with --job)")
    args = parser.parse_args(argv)
    if args.job and (args.os_name or args.python):
        parser.error("give --job, or --os and --python, not both")
    if not args.job and not (args.os_name and args.python):
        parser.error("--os and --python are required (or --job)")
    required = list(args.job) or required_jobs(args.os_name, args.python)
    name = args.name or (f"tests ({args.os_name}, py{args.python})" if not args.job else "the fan-in")
    repo, run_id = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"]
    ok, lines = check(lambda: fetch_jobs(repo, run_id), required, int(os.environ.get("GITHUB_RUN_ATTEMPT") or 0),
                      needs_ok=needs_succeeded(os.environ.get("NEEDS_RESULTS")))
    print("\n".join(lines))
    print(f"{name}: {'all required jobs succeeded' if ok else 'NOT all required jobs succeeded'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
