"""Collect the verify-all step timings of recent CI ``tests`` jobs into the index ``ci_timing_analysis.py`` reads.

    python tooling/ci_timing_collect.py --branch redesign/visual-editor --runs 30 --out ci_timing
    python tooling/ci_timing_analysis.py --index ci_timing/index.json --durations-dir ci_timing/durations --write-data d.json

Uses the GitHub CLI (``gh``; in Actions with ``GH_TOKEN``). For each completed CI run of ``--branch`` (newest first,
``--runs`` of them), each ``tests`` job's ``verify_step_durations.json`` is taken from its ``mesh-artifacts-<os>-py3.11``
artifact (kept 7 days). Jobs whose artifact has expired or whose verify-all didn't run are skipped.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=False).stdout


def _seconds(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    t = [datetime.fromisoformat(v.replace("Z", "+00:00")) for v in (start, end)]
    return round((t[1] - t[0]).total_seconds())


def collect(branch: str, runs: int, out: Path) -> list[dict[str, Any]]:
    durations = out / "durations"
    durations.mkdir(parents=True, exist_ok=True)
    listed = json.loads(_gh("run", "list", "--workflow", "ci.yml", "--branch", branch, "--limit", str(runs * 2),
                            "--json", "databaseId,event,headSha,createdAt,status") or "[]")
    index: list[dict[str, Any]] = []
    for run in [r for r in listed if r["status"] == "completed"][:runs]:
        jobs = json.loads(_gh("run", "view", str(run["databaseId"]), "--json", "jobs") or "{}").get("jobs", [])
        for job in jobs:
            if not job["name"].startswith("tests (") or job.get("conclusion") in ("cancelled", "skipped"):
                continue
            os_name = "windows" if "windows" in job["name"] else "linux"
            tmp = Path(tempfile.mkdtemp())
            try:
                _gh("run", "download", str(run["databaseId"]), "-n",
                    f"mesh-artifacts-{'windows' if os_name == 'windows' else 'ubuntu'}-latest-py3.11", "-D", str(tmp))
                src = tmp / "verify_step_durations.json"
                if not src.exists():
                    continue
                name = f"{run['databaseId']}_{os_name}.json"
                shutil.copyfile(src, durations / name)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            entry: dict[str, Any] = {"run_id": run["databaseId"], "os": os_name, "event": run["event"],
                                     "sha": run["headSha"], "date": run["createdAt"], "regime": "post-opt",
                                     "durations": name}
            job_s = _seconds(job.get("startedAt"), job.get("completedAt"))
            if job_s is not None:
                entry["job_s"] = job_s
            index.append(entry)
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", required=True)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(f"collected {len(collect(args.branch, args.runs, args.out))} tests jobs")


if __name__ == "__main__":
    main()
