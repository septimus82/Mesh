"""Scratch (CI-422A): every Extended run's GPU-lane terrain_stroke measurement with its runner calibration."""
import glob
import json
import subprocess
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
runs = json.loads(subprocess.run(["gh", "run", "list", "--workflow", "extended.yml", "--limit", "200", "--json",
                                  "databaseId,event,headSha,headBranch,createdAt,status,conclusion,attempt"],
                                 capture_output=True, text=True, check=True).stdout)
rows = []
for r in runs:
    if r["event"] == "pull_request" or r["status"] != "completed":
        continue
    d = OUT / str(r["databaseId"])
    if not d.exists():
        res = subprocess.run(["gh", "run", "download", str(r["databaseId"]), "-D", str(d), "-p", "lane-gpu-*"],
                             capture_output=True, text=True)
        if res.returncode != 0:
            d.mkdir(parents=True, exist_ok=True)
            (d / "none.txt").write_text(res.stderr)
    for f in glob.glob(str(d / "**" / "pytest_gpu_summary.json"), recursive=True):
        s = json.load(open(f, encoding="utf-8"))
        m = (s.get("measurements") or {}).get("terrain_stroke")
        if isinstance(m, str):
            try:
                m = json.loads(m)
            except ValueError:
                m = None
        if not m:
            continue
        b = (s.get("runner") or {}).get("before") or {}
        a = (s.get("runner") or {}).get("after") or {}
        h = (s.get("runner") or {}).get("host") or {}
        failed = [t for t in (s.get("failed") or []) if "sculpts_live" in t]
        rows.append({"run": r["databaseId"], "attempt": r["attempt"], "date": r["createdAt"][:16], "event": r["event"],
                     "sha": r["headSha"][:7], "branch": r["headBranch"], "lane": Path(f).parent.name,
                     "os": h.get("runner_os"), "image": h.get("image_version"), "cpu": b.get("cpu"), "vcpus": b.get("vcpus"),
                     "cpu_ms": b.get("cpu_ms"), "gl_frame_ms": b.get("gl_frame_ms"), "cpu_ms_after": a.get("cpu_ms"),
                     "gl_frame_ms_after": a.get("gl_frame_ms"),
                     "frame_median": m["frame_ms"]["median"], "frame_p95": m["frame_ms"]["p95"], "frame_max": m["frame_ms"]["max"],
                     "update_ms": m.get("update_terrain_ms", {}).get("median"), "commit_ms": m.get("commit_ms"),
                     "release_ms": m.get("release_to_next_frame_ms"), "test_failed": bool(failed)})
(OUT / "rows.json").write_text(json.dumps(rows, indent=1))
print(len(runs), "runs listed;", len(rows), "terrain measurements")
