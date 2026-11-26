from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_BASELINE_PATH = Path(__file__).resolve().parent / "baselines" / "unmarked_test_nodeids.txt"
_UPDATE_COMMAND = (
    "python -c \"import os, subprocess, sys; import tests.test_tier_marker_ratchet as t; "
    "os.environ['MESH_UPDATE_UNMARKED_BASELINE']='1'; "
    "raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-q', t.__file__]))\""
)


def _load_baseline() -> list[str]:
    if not _BASELINE_PATH.exists():
        return []
    rows: list[str] = []
    for line in _BASELINE_PATH.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        rows.append(text)
    return sorted(rows)


def test_unmarked_test_nodeids_ratchet(unmarked_test_nodeids: list[str]) -> None:
    current = sorted(str(x) for x in unmarked_test_nodeids)
    if os.getenv("MESH_UPDATE_UNMARKED_BASELINE") == "1":
        _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(current)
        if payload:
            payload += "\n"
        _BASELINE_PATH.write_text(payload, encoding="utf-8")

    allowed = set(_load_baseline())
    unexpected = sorted(nodeid for nodeid in current if nodeid not in allowed)
    assert not unexpected, (
        "New unmarked tests detected (sorted):\n"
        + "\n".join(unexpected)
        + "\n\n"
        + f"Update baseline intentionally with:\n{_UPDATE_COMMAND}"
    )


def test_every_fast_test_is_in_a_module_the_fast_tier_collects(fast_tests_outside_rule: list[str]) -> None:
    # For exactly ``-m fast``, tests/conftest.py leaves out test modules that can't hold a fast test (#422 F13). A full
    # collection, like CI's pytest job, sees every test: a fast test in a module the rule would leave out fails here.
    assert not fast_tests_outside_rule, (
        "Fast tests the fast tier would not collect (their module never says 'fast'; mark it there or add the module "
        "to _FAST_TEST_NODEIDS in tests/conftest.py):\n" + "\n".join(fast_tests_outside_rule)
    )


def test_the_fast_tier_collection_rule(tmp_path: Path) -> None:
    from tests.conftest import _may_hold_fast_tests

    cases = {
        "test_marked.py": "pytestmark = [pytest.mark.fast]\n",
        "test_alias.py": "from tests.tiers import FastBase\n\nclass TestThing(FastBase):\n    pass\n",
        "test_behaviour_loading_contract.py": "def test_x():\n    pass\n",  # fast by conftest's node-id list
        "test_slow_only.py": "pytestmark = [pytest.mark.slow]\n",
    }
    for name, source in cases.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    kept = {name for name in cases if _may_hold_fast_tests(tmp_path / name, {})}
    assert kept == {"test_marked.py", "test_alias.py", "test_behaviour_loading_contract.py"}


@pytest.mark.parametrize("listing", ["unmarked_test_nodeids.txt", "never_runs.txt"])
def test_listed_tests_still_exist(listing: str) -> None:
    # The other direction of each ratchet (#624, as the fast-marking allow-list's "no longer needed" check): a listed
    # test that was deleted or renamed leaves a free slot for a new one. Checked on the source, so any partial run
    # (a shard, one file) sees the same; a listed test that was since marked needs a full collection to notice.
    import re

    root = _BASELINE_PATH.parents[2]
    sources: dict[str, str] = {}
    stale = []
    for line in (_BASELINE_PATH.parent / listing).read_text(encoding="utf-8").splitlines():
        nodeid = line.split("  #", 1)[0].strip()
        if not nodeid or nodeid.startswith("#"):
            continue
        path, _, rest = nodeid.partition("::")
        if path not in sources:
            source_path = root / path
            sources[path] = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""
        name = rest.split("::")[-1].split("[")[0]
        if not re.search(rf"\b{re.escape(name)}\b", sources[path]):
            stale.append(nodeid)
    assert not stale, f"tests/baselines/{listing} lists tests that no longer exist; remove them:\n" + "\n".join(stale)
