"""Acceptance test, Milestone 6: a person in Mesh Studio and an external AI edit the same project.

The AI side is the real Mesh MCP server (``python -m engine.mcp_server.server``) in its own
process, driven over stdio by the official MCP client library, exactly as Claude, Codex or any
MCP client would drive it: no internal calls. The person's side is Mesh Studio, driven through
its real window with OS-level mouse and keyboard. The Studio's layout dump and the saved files are
only read, to find things and check results.

 1 paint a room, unsaved                     8 the AI adds dialogue and a flag condition (accepted)
 2 the AI proposes an NPC (over MCP)          9 a proposal is rejected: nothing changes
 3 review and accept it in Studio            10 the AI and the person change the same property
 4 the NPC is there at once                  11 the conflict is reported, nothing lost
 5 the unsaved painting is still there       12 save, close, reopen
 6 undo the NPC, not the painting            13 play: the NPC and its dialogue work
 7 redo it                                   14 the same changes through `mesh author` give the same room

Run from the repo root:  py -3.13 tooling/acceptance_ai_coauthoring.py [--out DIR]
(needs the optional MCP dependency: pip install -e .[mcp]). MESH_GUI_AT / MESH_GUI_POLITE as for
the other GUI tests. Writes DIR/report.json, DIR/mcp_transcript.json and a screenshot per step.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))
from acceptance_event_authoring import AuthorPage  # noqa: E402
from gui_driver import Driver  # noqa: E402

from engine.schema_validation import validate  # noqa: E402

SCENE = "packs/core_regions/scenes/start.json"
WALL = "Stone wall"


class McpClient:
    """An MCP client session to the Mesh MCP server (a subprocess), usable from plain code."""

    def __init__(self, transcript: list[dict[str, Any]]) -> None:
        self.transcript = transcript
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._ready = asyncio.run_coroutine_threadsafe(self._open(), self._loop)
        self._ready.result(timeout=60)

    async def _open(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(command=sys.executable, args=["-m", "engine.mcp_server.server"], cwd=str(REPO),
                                       env={**os.environ, "PYTHONPATH": str(REPO)})
        self._stdio = stdio_client(params)
        read, write = await self._stdio.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        tools = await self._session.list_tools()
        self.tools = sorted(tool.name for tool in tools.tools)

    def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        future = asyncio.run_coroutine_threadsafe(self._session.call_tool(tool, arguments), self._loop)
        result = future.result(timeout=60)
        payload: Any = getattr(result, "structuredContent", None)
        if isinstance(payload, dict) and set(payload) == {"result"}:
            payload = payload["result"]
        if not isinstance(payload, dict):
            text = "".join(getattr(part, "text", "") for part in getattr(result, "content", []) or [])
            payload = json.loads(text) if text.strip().startswith("{") else {"text": text}
        self.transcript.append({"tool": tool, "arguments": arguments, "result": payload})
        return payload

    def close(self) -> None:
        async def shut() -> None:
            await self._session.__aexit__(None, None, None)
            await self._stdio.__aexit__(None, None, None)

        try:
            asyncio.run_coroutine_threadsafe(shut(), self._loop).result(timeout=20)
        except Exception:  # noqa: BLE001  # REASON: best-effort shutdown of the test's client
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    layout = out / "layout.json"
    env = {**os.environ, "PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout)}
    os.environ.update(env)
    project = work / "coauthored"
    results: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []
    holder: dict[str, Any] = {"driver": None, "page": None, "mcp": None}
    memo: dict[str, Any] = {}

    def launch() -> AuthorPage:
        layout.unlink(missing_ok=True)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=project, shots=out)
        page = AuthorPage(driver, layout)
        page.memo_positions = memo.setdefault("positions", {})
        holder["driver"], holder["page"] = driver, page
        page.wait(lambda s: s["mode"] == "edit" and s["objects"], "the Studio", timeout=60)
        return page

    def step(name: str, action: Callable[[], Any]) -> bool:
        started = time.time()
        try:
            detail, ok, error = action(), True, None
        except Exception as exc:  # noqa: BLE001  # REASON: record every failure in the report, then stop
            ok, error, detail = False, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=4)
        driver = holder["driver"]
        shot = driver.shot(f"{len(results) + 1:02d}_{name}").name if driver and driver.proc.poll() is None else None
        results.append({"step": name, "ok": ok, "error": error, "detail": detail,
                        "seconds": round(time.time() - started, 1), "screenshot": shot})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {error}" if error else ""), flush=True)
        return ok

    def p() -> AuthorPage:
        return holder["page"]

    def ai(tool: str, **arguments: Any) -> dict[str, Any]:
        return holder["mcp"].call(tool, root=str(project), **arguments)

    def objects() -> dict[str, dict[str, Any]]:
        return {o["name"]: o for o in p().fresh()["objects"]}

    def walls() -> list[int]:
        return list(p().fresh()["map"]["layers"]["walls"])

    def on_disk() -> dict[str, Any]:
        return json.loads((project / SCENE).read_text(encoding="utf-8"))

    def review_and(button: str) -> dict[str, Any]:
        """Open the AI panel (it shows the waiting count) and press Accept or Reject."""
        state = p().wait(lambda s: any(w["type"] == "button" and w["text"].startswith("AI (") for w in s["widgets"]),
                         "the AI button counting a proposal")
        label = next(w["text"] for w in state["widgets"] if w["type"] == "button" and w["text"].startswith("AI ("))
        if state["panel"] != "ai":
            p().button(label)
        p().wait(lambda s: s["panel"] == "ai", "the AI panel")
        p().d.shot(f"{len(results) + 1:02d}_review_{button.lower()}")
        p().press(button)
        return p().fresh()

    # ------------------------------------------------------------------------- steps
    def s01_paint_unsaved() -> dict[str, Any]:
        subprocess.run([sys.executable, "-m", "mesh_cli", "new", "coauthored", "--template", "blank"], cwd=work, env=env,
                       check=True, capture_output=True)
        launch()
        p().tile(WALL)
        p().stroke((3, 2), (9, 2))
        memo["painted"] = walls()
        assert p().state()["dirty"], "the painting is unsaved"
        holder["mcp"] = McpClient(transcript)
        assert {"read_project", "propose_changes", "proposal_status", "authoring_operations"} <= set(holder["mcp"].tools)
        return {"wall_tiles": sum(1 for t in memo["painted"] if t), "mcp_tools": holder["mcp"].tools}

    def s02_ai_proposes_npc() -> dict[str, Any]:
        ops_list = ai("authoring_operations")
        assert any(o["op"] == "place_prefab" for o in ops_list["operations"])
        seen = ai("read_project")
        assert seen["source"] == "mesh_studio" and seen["unsaved"], "the AI sees the open, unsaved project"
        memo["base"] = seen["revision"]
        proposal = ai("propose_changes", title="Add a sexton", base_revision=seen["revision"], changes=[
            {"op": "place_prefab", "prefab": "person", "x": 448, "y": 224},
            {"op": "rename_entity", "entity_id": "@0", "name": "Sexton"}])
        assert proposal["ok"], proposal
        memo["npc_proposal"] = proposal["proposal_id"]
        # While the AI waited, the person kept painting: both must survive.
        p().stroke((3, 3), (9, 3))
        memo["painted"] = walls()
        return {"summary": proposal["proposal"]["summary"], "revision_seen": seen["revision"]}

    def s03_review_and_accept() -> dict[str, Any]:
        state = review_and("Accept")
        assert "Sexton" in {o["name"] for o in state["objects"]}
        status = ai("proposal_status", proposal_id=memo["npc_proposal"])
        assert status["proposal"]["status"] == "accepted", status
        return {"status": status["proposal"]["status"], "created": status["proposal"]["created"]}

    def s04_npc_appears() -> dict[str, Any]:
        sexton = objects()["Sexton"]
        assert (sexton["x"], sexton["y"]) == (448, 224)
        assert p().state()["selected"] == sexton["id"], "accepting selects what it made"
        memo["positions"]["Sexton"] = (448.0, 224.0)
        return {"sexton": sexton["id"]}

    def s05_painting_kept() -> None:
        assert walls() == memo["painted"], "both strokes, one made while the AI's proposal waited, are still there"
        assert p().state()["dirty"]

    def s06_undo_npc_only() -> None:
        p().d.key("CTRL+Z")
        p().wait(lambda s: "Sexton" not in {o["name"] for o in s["objects"]}, "the NPC undone")
        assert walls() == memo["painted"], "undo took the AI's change back, not the painting"

    def s07_redo_npc() -> None:
        p().d.key("CTRL+Y")
        p().wait(lambda s: "Sexton" in {o["name"] for o in s["objects"]}, "the NPC back")
        assert walls() == memo["painted"]

    def s08_ai_adds_dialogue_and_condition() -> dict[str, Any]:
        seen = ai("read_project")
        proposal = ai("propose_changes", title="The sexton speaks, once the lantern is lit", base_revision=seen["revision"],
                      changes=[
                          {"op": "set_dialogue_text", "entity_id": "Sexton", "text": "Who goes there, so late?"},
                          {"op": "add_line", "entity_id": "Sexton", "text": "Mind the open graves."},
                          {"op": "set_conversation", "entity_id": "Sexton", "once": False},
                          {"op": "set_show_when", "entity_id": "Sexton", "require": "lantern_lit", "forbid": ""},
                          {"op": "place_blank", "name": "Lantern", "x": 288, "y": 128},
                          {"op": "set_trigger_zone", "entity_id": "@4", "width": 96, "height": 96, "set_flags": "lantern_lit"},
                      ])
        assert proposal["ok"], proposal
        review_and("Accept")
        status = ai("proposal_status", proposal_id=proposal["proposal_id"])
        assert status["proposal"]["status"] == "accepted", status
        names = {o["name"]: o for o in p().fresh()["objects"]}
        assert "Lantern" in names and "ConditionalActivator" in names["Sexton"]["behaviours"]
        memo["positions"]["Lantern"] = (288.0, 128.0)
        return {"summary": status["proposal"]["summary"]}

    def s09_reject_changes_nothing() -> dict[str, Any]:
        before = p().fresh()["room_doc"]
        proposal = ai("propose_changes", title="Remove the sexton", changes=[{"op": "remove_entity", "entity_id": "Sexton"}])
        assert proposal["ok"], proposal
        review_and("Reject")
        assert p().fresh()["room_doc"] == before, "a rejected proposal changes nothing"
        status = ai("proposal_status", proposal_id=proposal["proposal_id"])
        assert status["proposal"]["status"] == "rejected"
        refused = ai("propose_changes", changes=[{"op": "move_entity", "entity_id": "Ghost", "x": 1, "y": 1}])
        assert not refused["ok"] and "no object 'Ghost'" in refused["message"], refused
        return {"rejected": status["proposal"]["status"], "invalid": refused["message"]}

    def s10_conflicting_edits() -> dict[str, Any]:
        seen = ai("read_project")
        p().d.key("ESC")  # put the wall brush down: back to Select
        p().wait(lambda s: s["tool"] == "select", "the Select tool")
        p().select("Sexton")
        p().fill("name", "Warden")  # the person renames him...
        proposal = ai("propose_changes", title="Rename the sexton", base_revision=seen["revision"],  # ...so does the AI
                      changes=[{"op": "rename_entity", "entity_id": "Sexton", "name": "Gravedigger"}])
        assert proposal["ok"], proposal
        memo["conflict"] = proposal["proposal_id"]
        review_and("Accept")
        return {"proposal": memo["conflict"]}

    def s11_conflict_reported_nothing_lost() -> dict[str, Any]:
        state = p().fresh()
        mine = next(p for p in state["ai"] if p["proposal_id"] == memo["conflict"])
        assert mine["status"] == "conflict" and mine["conflicts"][0]["studio"] == "Warden", mine
        assert mine["conflicts"][0]["ai"] == "Gravedigger"
        assert "Warden" in {o["name"] for o in state["objects"]}, "the person's edit stands"
        assert any(w["type"] == "button" and w["text"] == "Accept" and w["disabled"] for w in state["widgets"])
        status = ai("proposal_status", proposal_id=memo["conflict"])
        assert status["proposal"]["status"] == "conflict"
        p().press("Reject")
        return {"conflicts": mine["conflicts"]}

    def s12_save_close_reopen() -> dict[str, Any]:
        p().d.key("CTRL+S")
        p().wait(lambda s: not s["dirty"], "saved")
        memo["saved"] = on_disk()
        validate(memo["saved"], "scene.schema.json", "scene")
        p().d.click_close_button()
        p().d.proc.wait(timeout=20)
        page = launch()
        assert on_disk() == memo["saved"]
        names = {o["name"] for o in page.state()["objects"]}
        assert {"Warden", "Lantern", "Player"} <= names, names
        assert walls() == memo["painted"]
        return {"objects": sorted(names)}

    def s13_play() -> dict[str, Any]:
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "the game", timeout=30)
        time.sleep(1.0)
        hidden = not any(s["name"] == "Warden" and s["visible"] for s in p().play_state()["sprites"])
        p().go_to(288, 128)  # into the lantern's zone
        p().wait(lambda s: s["play"]["flags"].get("lantern_lit"), "lantern_lit")
        p().wait(lambda s: any(x["name"] == "Warden" and x["visible"] for x in s["play"]["sprites"]), "the warden appearing")
        memo["positions"]["Warden"] = (448.0, 224.0)
        p().talk_to("Warden")
        p().wait_dialogue("Who goes there")
        p().d.shot(f"{len(results) + 1:02d}_talking")
        p().tap("E")
        p().wait_dialogue("Mind the open graves")
        p().close_dialogue()
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "edit", "back to editing")
        return {"hidden_until_lit": hidden}

    def s14_cli_gives_the_same_room() -> dict[str, Any]:
        other = work / "offline"
        subprocess.run([sys.executable, "-m", "mesh_cli", "new", "offline", "--template", "blank"], cwd=work, env=env,
                       check=True, capture_output=True)
        accepted = [t for t in transcript if t["tool"] == "propose_changes" and t["arguments"].get("title") in
                    ("Add a sexton", "The sexton speaks, once the lantern is lit")]
        studio_room = memo["saved"]
        wall_gid = max(studio_room_tiles(studio_room, "walls"))
        width = studio_room["tilemap"]["width"]
        painted = [[i % width, i // width] for i, t in enumerate(studio_room_tiles(studio_room, "walls")) if t]
        changes = [{"op": "paint_tiles", "layer": "walls", "cells": painted, "tile": wall_gid}]
        for call in accepted:  # @N counts within its own batch: shift it to where that batch starts here
            start = len(changes)
            changes += [{k: (f"@{int(v[1:]) + start}" if isinstance(v, str) and v.startswith("@") else v)
                         for k, v in change.items()} for change in call["arguments"]["changes"]]
        changes += [{"op": "rename_entity", "entity_id": "Sexton", "name": "Warden"}]
        batch = out / "offline_changes.json"
        batch.write_text(json.dumps({"changes": changes}, indent=2), encoding="utf-8")
        run = subprocess.run([sys.executable, "-m", "mesh_cli", "author", "apply", str(batch), "--project", str(other)],
                             cwd=REPO, env=env, capture_output=True, text=True)
        assert run.returncode == 0, run.stdout + run.stderr
        offline = json.loads((other / SCENE).read_text(encoding="utf-8"))
        validate(offline, "scene.schema.json", "scene")
        assert entities_by_id(offline) == entities_by_id(studio_room), "the same objects, the same settings"
        assert studio_room_tiles(offline, "walls") == studio_room_tiles(studio_room, "walls")
        return {"changes": len(changes), "cli": json.loads(run.stdout)["summary"]}

    steps = [s01_paint_unsaved, s02_ai_proposes_npc, s03_review_and_accept, s04_npc_appears, s05_painting_kept,
             s06_undo_npc_only, s07_redo_npc, s08_ai_adds_dialogue_and_condition, s09_reject_changes_nothing,
             s10_conflicting_edits, s11_conflict_reported_nothing_lost, s12_save_close_reopen, s13_play,
             s14_cli_gives_the_same_room]
    try:
        for action in steps:
            if not step(action.__name__.split("_", 1)[1], action):
                break
    finally:
        if holder["mcp"] is not None:
            holder["mcp"].close()
        if holder["driver"] is not None:
            holder["driver"].close()
    passed = sum(r["ok"] for r in results)
    (out / "report.json").write_text(json.dumps({"passed": passed, "total": len(steps), "steps": results}, indent=2),
                                     encoding="utf-8")
    (out / "mcp_transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    print(f"{passed}/{len(steps)} steps passed; report: {out / 'report.json'}")
    return 0 if passed == len(steps) else 1


def studio_room_tiles(room: dict[str, Any], layer: str) -> list[int]:
    return next(entry["tiles"] for entry in room["tilemap"]["tile_layers"] if entry["id"] == layer)


def entities_by_id(room: dict[str, Any]) -> dict[str, Any]:
    return {e["id"]: e for e in room["entities"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_ai_coauthoring")
    raise SystemExit(run(parser.parse_args().out))
