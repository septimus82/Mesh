"""F13-C (#422): ``python -m pytest -p tooling.ci_shards_plugin --mesh-shard K/N --mesh-shard-record PATH`` runs shard
K of N of the collected suite (whole modules, ``tooling/ci_shards.py`` decides which) and writes its record to PATH.

The record says what the shard collected (the whole selected suite, test ids with the checkout's path written
``<repo>``), which of those it ran, every one's outcome and seconds, the modules skipped at collection, the commit
and the assignment scheme. It is written once collection ends (``complete: false``) and again when the session
finishes (``complete: true``, with pytest's exit status), so a shard stopped part way leaves an incomplete record.
``ci_shards.py check`` reads the records of all shards.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tooling import ci_shards


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("mesh-shard")
    group.addoption("--mesh-shard", default=None, help="Run shard K/N of the collected suite (whole modules).")
    group.addoption("--mesh-shard-record", default=None, help="Where to write the shard's record (JSON).")


class _Shard:
    def __init__(self, config: pytest.Config, shard: int, shards: int, path: Path) -> None:
        self.root = str(config.rootpath)
        self.path = path
        try:
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True,
                                    check=False).stdout.strip()
        except OSError:
            commit = ""
        self.record: dict[str, Any] = {
            "schema": ci_shards.RECORD_SCHEMA, "complete": False, "shard": shard, "shards": shards,
            "commit": commit, "scheme_digest": ci_shards.scheme_digest(shards),
            "collected": [], "collected_digest": "", "collection_skips": [], "selected": [],
            "outcomes": {}, "durations": {}, "exitstatus": None,
        }

    def _id(self, nodeid: str) -> str:
        return ci_shards.normalize(nodeid, self.root)

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.record, indent=0, sort_keys=True) + "\n", encoding="utf-8")

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.skipped:  # (a module skipped as a whole: every shard collects it, so the check counts it once)
            self.record["collection_skips"].append(self._id(report.nodeid))

    @pytest.hookimpl(trylast=True)  # (after -m and every other plugin has chosen the suite)
    def pytest_collection_modifyitems(self, config: pytest.Config, items: list[pytest.Item]) -> None:
        shard, shards = self.record["shard"], self.record["shards"]
        keep = [item for item in items if ci_shards.shard_of(ci_shards.module_of(item.nodeid), shards) == shard]
        drop = [item for item in items if ci_shards.shard_of(ci_shards.module_of(item.nodeid), shards) != shard]
        collected = [self._id(item.nodeid) for item in items]
        self.record.update(collected=sorted(collected), collected_digest=ci_shards.ids_digest(collected),
                           selected=sorted(self._id(item.nodeid) for item in keep))
        self.record["collection_skips"].sort()
        if drop:
            config.hook.pytest_deselected(items=drop)
        items[:] = keep
        self.write()

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        nodeid = self._id(report.nodeid)
        durations, outcomes = self.record["durations"], self.record["outcomes"]
        durations[nodeid] = round(durations.get(nodeid, 0.0) + report.duration, 4)
        if report.failed:
            outcomes[nodeid] = "failed" if report.when == "call" else "error"
        elif outcomes.get(nodeid) in ("failed", "error"):
            pass
        elif report.skipped:
            outcomes[nodeid] = "xfailed" if hasattr(report, "wasxfail") else "skipped"
        elif report.when == "call":
            outcomes[nodeid] = "xpassed" if hasattr(report, "wasxfail") else "passed"

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        self.record.update(complete=True, exitstatus=int(exitstatus))
        self.record["collection_skips"].sort()
        self.write()


def pytest_configure(config: pytest.Config) -> None:
    spec = config.getoption("--mesh-shard")
    if spec is None:
        return
    try:
        shard, shards = (int(part) for part in str(spec).split("/"))
    except ValueError:
        raise pytest.UsageError(f"--mesh-shard {spec}: expected K/N, e.g. 1/2") from None
    if not 1 <= shard <= shards:
        raise pytest.UsageError(f"--mesh-shard {spec}: K must be 1..N")
    record = config.getoption("--mesh-shard-record")
    if not record:
        raise pytest.UsageError("--mesh-shard needs --mesh-shard-record PATH")
    config.pluginmanager.register(_Shard(config, shard, shards, Path(record)), "mesh-shard")
