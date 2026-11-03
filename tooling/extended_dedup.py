"""Extended's duplicate pull-request run (#422): whether a pull request's Extended lanes would only repeat the push run.

#344 (``redesign/visual-editor`` into ``main``) is open for good, and ``main`` is an ancestor of the integration
branch, so every merge started Extended twice on the same tree: the push run and #344's pull-request run (~71 runner
minutes each, 22 of 22 merges). This decides, for one pull-request run, whether its lanes may be left out: only when
every one of these holds, each checked positively, and otherwise they run as before.

  1. the pull request comes from this repository, not a fork;
  2. its head branch is the push-tested integration branch (the one ``on.push`` in extended.yml names);
  3. the commit tested here (the pull request's merge commit, ``GITHUB_SHA``) has the pull request's base and head as
     its parents, and the same tree as the head: the lanes would test exactly what the push run tests;
  4. the base is an ancestor of the head (GitHub's compare: the head is ``ahead`` of it or ``identical``);
  5. Extended has a push run for that head commit on that branch, and its newest one is queued, running or succeeded.
     A failed, cancelled or timed-out push run, or none, means the lanes run here.

Any read that fails or answers something unexpected means the lanes run. Leaving them out is not a pass: the summary
says so and links the push run, which is the evidence, and may still be running.

    python3 -m tooling.extended_dedup --push-branch redesign/visual-editor --workflow extended.yml
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from typing import Any

from tooling.ci_require_jobs import TIMEOUT, FetchError, _sanitized

PENDING = {"queued", "in_progress", "waiting", "requested", "pending"}


def gh_get(path: str, *, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> Any:
    """One GitHub API read (``gh api``), as JSON. Raises FetchError naming what went wrong."""
    try:
        proc = run(["gh", "api", path], capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise FetchError(f"no answer within {TIMEOUT:g} s: {path}") from None
    if proc.returncode != 0:
        raise FetchError(f"gh api failed (exit {proc.returncode}): {path}: "
                         f"{_sanitized(proc.stderr or proc.stdout) or 'no output'}")
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise FetchError(f"unreadable answer: {path}: {_sanitized(proc.stdout) or 'empty'}") from None


def decide(event: Mapping[str, Any], *, repo: str, sha: str, push_branch: str, workflow: str,
           get: Callable[[str], Any]) -> tuple[bool, list[str], dict[str, str]]:
    """(skip the lanes?, one line per check, the facts the summary shows). The first check that doesn't hold, or a
    read that fails or answers something unexpected, decides "run"."""
    lines: list[str] = []
    facts: dict[str, str] = {"tested": sha}

    def fail(why: str) -> tuple[bool, list[str], dict[str, str]]:
        lines.append(f"NO   {why}")
        return False, lines, facts

    def ok(why: str) -> None:
        lines.append(f"ok   {why}")

    try:
        pr = event["pull_request"]
        head_sha, base_sha = str(pr["head"]["sha"]), str(pr["base"]["sha"])
        head_ref, head_repo = str(pr["head"]["ref"]), str((pr["head"].get("repo") or {}).get("full_name"))
    except (KeyError, TypeError, AttributeError):
        return fail("not a pull_request event with a head and a base")
    facts.update(head=head_sha, base=base_sha)

    if head_repo != repo:
        return fail(f"the head is from {head_repo}, not {repo}")
    ok(f"the head is from {repo}")
    if head_ref != push_branch:
        return fail(f"the head branch is {head_ref}, not the push-tested {push_branch}")
    ok(f"the head branch is the push-tested {push_branch}")

    try:
        merge = get(f"repos/{repo}/commits/{sha}")
        parents = [str(p["sha"]) for p in merge["parents"]]
        merge_tree = str(merge["commit"]["tree"]["sha"])
        head_tree = str(get(f"repos/{repo}/commits/{head_sha}")["commit"]["tree"]["sha"])
        compare = get(f"repos/{repo}/compare/{base_sha}...{head_sha}")
        status, behind = str(compare["status"]), int(compare["behind_by"])
        runs = get(f"repos/{repo}/actions/workflows/{workflow}/runs"
                   f"?event=push&branch={push_branch}&head_sha={head_sha}&per_page=20")["workflow_runs"]
    except FetchError as exc:
        return fail(f"a read failed: {exc}")
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return fail(f"an answer was not as expected: {type(exc).__name__}: {exc}")
    facts.update(tree=merge_tree)

    if parents != [base_sha, head_sha]:
        return fail(f"the tested commit's parents are {parents}, not [base, head]")
    ok("the tested commit merges the base and the head")
    if merge_tree != head_tree:
        return fail(f"the tested tree {merge_tree} is not the head's {head_tree}")
    ok(f"the tested tree is the head's ({head_tree})")
    if status not in ("ahead", "identical") or behind != 0:
        return fail(f"the base is not an ancestor of the head (compare: {status}, behind by {behind})")
    ok(f"the base is an ancestor of the head (compare: {status})")

    mine = [r for r in runs if isinstance(r, Mapping) and r.get("head_sha") == head_sha
            and r.get("event") == "push" and r.get("head_branch") == push_branch]
    if not mine:
        return fail(f"no {workflow} push run for {head_sha} on {push_branch}")
    newest = max(mine, key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0)))
    state = str(newest.get("conclusion") or newest.get("status"))
    facts.update(push_run=str(newest.get("html_url") or newest.get("id")), push_state=state)
    if not (newest.get("status") in PENDING or newest.get("conclusion") == "success"):
        return fail(f"the newest push run for {head_sha} is {state}: {facts['push_run']}")
    ok(f"the push run for {head_sha} is {state}: {facts['push_run']}")
    return True, lines, facts


def summary(skip: bool, lines: list[str], facts: Mapping[str, str]) -> str:
    out = ["## Duplicate check (#422)", ""]
    if skip:
        out += ["**The lanes did NOT run in this pull-request run.** It would test the same tree as the push run "
                "below, which is the evidence. This is not a test result: the push run may still be running, and "
                "only its outcome counts.", ""]
    else:
        out += ["**The lanes run in this pull-request run.**", ""]
    out += [f"- {k}: `{v}`" for k, v in facts.items()]
    out += ["", "```", *lines, "```"]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--push-branch", required=True)
    parser.add_argument("--workflow", required=True)
    args = parser.parse_args(argv)
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as fh:
        event = json.load(fh)
    skip, lines, facts = decide(event, repo=os.environ["GITHUB_REPOSITORY"], sha=os.environ["GITHUB_SHA"],
                                push_branch=args.push_branch, workflow=args.workflow, get=gh_get)
    text = summary(skip, lines, facts)
    print(text)
    for name, value in (("GITHUB_STEP_SUMMARY", text), ("GITHUB_OUTPUT", f"skip={'true' if skip else 'false'}\n")):
        if os.environ.get(name):
            with open(os.environ[name], "a", encoding="utf-8") as fh:
                fh.write(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
