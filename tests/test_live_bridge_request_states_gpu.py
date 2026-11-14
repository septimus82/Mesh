"""#462 S3 in Mesh Studio's own window (hidden): an AI's proposal that timed out while Studio was busy never shows up.

Studio's main thread is busy (no frames run) while an AI proposes a change over MCP: the answer is "timeout", the
request cancelled. Studio's frames then run again, its own update draining the live session's queue: nothing reaches
the person's AI panel, the project is unchanged. The same proposal sent while Studio runs is staged once, and
``request_status`` reports both requests as they ended. GL-gated: set MESH_GL_SMOKE=1.

Why a real window: the queue is drained by Studio's own ``on_update``, which the headless tests stand in for.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture
def driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    import hd2d_floors_demo
    from hd2d_studio_demo import StudioDriver

    monkeypatch.delenv("MESH_STUDIO_NO_AI_BRIDGE", raising=False)  # (this test needs the live session)
    project = hd2d_floors_demo.build(tmp_path / "HD-2D studio")
    d = StudioDriver(project)
    try:
        yield d
    finally:
        d.close()


def test_a_proposal_that_timed_out_while_studio_was_busy_never_reaches_the_person(driver: Any) -> None:
    from engine.mcp_server import tools

    d, studio = driver, driver.studio
    root = str(studio.project.root)
    change = [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64}]
    documents, revision = studio.project.all_documents(), studio.project.revision
    studio.ai.bridge.request_timeout = 0.3

    busy = tools.propose_changes(change, title="While busy", root=root)  # (no frames run meanwhile)
    assert busy["reason"] == "timeout", busy
    d.advance(30)  # Studio runs again: its update drains the queue
    assert studio.ai.proposals == [] and studio.project.all_documents() == documents  # (was: staged now, "timed out")
    assert studio.project.revision == revision and busy["request_state"] == "cancelled"

    studio.ai.bridge.request_timeout = 5.0
    box: dict[str, Any] = {}
    thread = threading.Thread(target=lambda: box.update(answer=tools.propose_changes(change, title="Running",
                                                                                     root=root)))
    thread.start()
    for _ in range(600):
        if not thread.is_alive():
            break
        d.advance()
    thread.join(5)
    running = box["answer"]
    assert running["ok"] is True and running["request_state"] == "finished", running
    assert [(p.title, p.status) for p in studio.ai.proposals] == [("Running", "pending")]
    d.advance(30)
    assert len(studio.ai.proposals) == 1
    assert tools.request_status(busy["request_id"], root=root)["state"] == "cancelled"
    assert tools.request_status(running["request_id"], root=root)["result"]["proposal_id"] == running["proposal_id"]
