# Milestone 6: unified human and AI editing — results and notes

Branch `redesign/visual-editor`. Summary and status: [`MESH_REBUILD.md`](../../MESH_REBUILD.md).

The test: a person edits a game in Mesh Studio while an external AI modifies the same project
through Mesh's authoring interface. The person reviews the AI's changes, undoes them, and keeps
working without losing anything.

## One authoring architecture

```
            Mesh Studio (person)      MCP server (any AI client)      mesh author (CLI, scripts)
                    \                          |                               /
                     \                engine/authoring_session.py  ---------- /
                      \                 (Studio open? -> proposal; else files)
                       \                       |
                        +------ engine/authoring.py: named changes, one transaction ------+
                                               |
                         engine/project_ops.py: pure, validated operations
                                               |
                        engine/studio_project.Project: documents, undo, save
```

- **`engine/authoring.py`** is the API.
  - A change is `{"op", "room"?, ...settings}`. Objects are named by id or unique name, and `@N` refers to an object made earlier in the same batch.
  - A batch runs as one transaction. It is one undo step in the Studio, and it is all or nothing, failing with the change and the reason.
  - **The operation list is generated** from the signatures and docstrings in `project_ops` (37 operations), so there is no hand-kept catalogue.
  - `changes_between`, `conflicts` and `summarize` describe a batch in plain words for review.
- **`engine/authoring_session.py`** is the outside entry point.
  - When Mesh Studio has the project open, a batch becomes a **proposal** there.
  - Otherwise it applies to the files, with every room checked against the scene schema before it is written.
- **Mesh Studio** uses `project_ops` directly. It also hosts the existing loopback live-session bridge (`engine/editor/live_session_bridge.py`: discovery file, bearer token, main-thread queue) through `engine/studio_ai.py`. AI proposals appear under **AI** in the top bar.
- **MCP:** six provider-neutral tools: `authoring_operations`, `read_project`, `propose_changes`, `apply_changes`, `proposal_status`, `withdraw_proposal`. Nothing in the authoring path names a particular AI or model.
- **CLI:** `mesh author ops | read | apply | propose | status`, JSON in and JSON out. Any agent that can run a command can use it.

### Proposals, revisions and conflicts

1. **Staging.** The AI reads the project (`read_project` returns a `revision`) and proposes a batch with that `base_revision`.
   - Studio dry-runs the batch on a copy as of that revision and lists what it would change.
   - An invalid batch is refused straight back to the AI with the reason.
2. **Accepting.** The person accepts in Studio. AI tools cannot accept: `live_accept_proposal` is refused with `needs_person`.
   - If the person changed nothing since the AI read, the batch applies as one undo step.
   - Otherwise both sides' changes are compared property by property (objects matched by id, tiles cell by cell):
     - **Separate edits:** both survive. For example, the person paints a wall while the AI adds an NPC.
     - **The same property changed differently:** a **conflict**. It is listed with both values, nothing is applied, and the person's version stands.
3. **Rejecting** changes nothing.
4. **Files are never written behind Studio's back:**
   - `apply_changes`, and the everyday `apply_ops` operations, turn into a proposal while Studio is open.
   - The other `apply_ops` operations refuse while Studio is open.
   - A Studio save that finds a file changed on disk since it opened it keeps that version as `.outside-change.bak` and says so.

## The integration test

`py -3.13 tooling/acceptance_ai_coauthoring.py --out DIR` (needs `pip install -e .[mcp]`).

- **The AI side** is the real Mesh MCP server (`python -m engine.mcp_server.server`) in its own process, driven over stdio by the official `mcp` client library, as Claude, Codex or any MCP client would drive it.
- **The person's side** is Mesh Studio, driven through its real window with OS-level mouse and keyboard.

**Final run: 14/14.** Evidence in [`milestone6_screens/`](milestone6_screens/):
- `report.json`;
- `mcp_transcript.json`: every MCP call and its result, accepted and rejected;
- `offline_changes.json`: the batch given to the CLI;
- screenshots.

| # | Step | Checked | Result |
|---|---|---|---|
| 1 | Paint a room in Studio, unsaved | A wall stroke; Studio dirty; the MCP client connected and lists the authoring tools | Pass |
| 2 | The AI proposes an NPC | `authoring_operations`, `read_project` (sees the open, unsaved project, revision R), `propose_changes` (place a Person, rename it Sexton, `@0`). Meanwhile the person paints another stroke. | Pass |
| 3 | Review and accept in Studio | The **AI (1)** button, the panel listing the changes, **Accept**; `proposal_status` = accepted | Pass |
| 4 | The NPC appears at once | In the room at 448, 224; selected | Pass |
| 5 | The unsaved painting is still there | Both strokes, including the one painted after the AI read the project | Pass |
| 6 | Undo the NPC, not the painting | Ctrl+Z: Sexton gone, every wall tile still there | Pass |
| 7 | Redo | Ctrl+Y: Sexton back | Pass |
| 8 | Dialogue and a flag condition | Two lines, repeatable, "shows only when `lantern_lit`", and a trigger zone (Lantern) that sets the flag; accepted | Pass |
| 9 | A rejected proposal | "Remove the sexton", **Reject**: the room document is identical; status rejected. An invalid batch (an object that doesn't exist) is refused at once with the reason. | Pass |
| 10 | The same property, both ways | The person renames Sexton to Warden in the inspector; the AI, from the earlier revision, proposes Gravedigger; **Accept** | Pass |
| 11 | Conflict identified, nothing lost | Status conflict, listing name and speaker, here 'Warden' vs proposed 'Gravedigger'. Accept is disabled; Warden stands; rejected. | Pass |
| 12 | Save, close, reopen | Saved file passes the scene schema; reopened identical; Warden, Lantern and the painting are there | Pass |
| 13 | Play | The Warden is hidden until the Lantern zone sets `lantern_lit`, then appears; talking gives "Who goes there, so late?" then "Mind the open graves." | Pass |
| 14 | Offline CLI, same result | The same changes (the painting, both accepted AI batches, the rename) through `mesh author apply` on a fresh Blank project: identical objects and settings, identical tiles, schema-valid | Pass |

## Priority 0: changing an animated object's picture

- Animation settings are never dropped any more.
  - Removing a picture and choosing it again brings the animation back. This was the My Game1 case.
  - A same-layout sheet carries the animation over, and Animator clips follow it.
  - A different layout is kept and flagged in the Look and Animation tabs, with **Use this picture** and **Reset animation**, both undoable.
- Checked in the real window, 6/6: remove and re-choose, a mismatched picture flagged, reset, undo, save and reopen, still flagged after reopening.
- Unit tests are in `tests/test_project_ops_authoring.py`.

## The audit: what edits projects, and through what

| Path | Before | Now |
|---|---|---|
| Mesh Studio | `project_ops` | `project_ops`, plus AI proposals through `authoring` |
| MCP: new authoring tools | — | `authoring` (live proposal or files) |
| MCP `apply_ops`: `add_entity_from_prefab`, `delete_entity`, `set_behaviour_params`, `paint_tiles` on a Studio project | `AIOps`, which wrote files directly | Adapter to `authoring` (same validation; becomes a proposal while Studio is open) |
| MCP `apply_ops`: lights, quests, world, cutscenes, legacy scenes | `AIOps` | Unchanged; refused while Studio is open |
| MCP `live_*` tools and the legacy editor's inbox | The legacy editor's six live ops | Unchanged for the legacy editor. Against Studio, staging goes to the Studio inbox and accepting is refused. The one-call add tool no longer reports false success. |
| CLI `mesh author` | — | `authoring` |
| CLI `scene …`, `room scaffold`, `world …`, `new-npc`, `apply-plan` | Each has its own JSON code | Unchanged (next slice: route those that target Studio projects through `authoring`, then retire the duplicates) |
| Legacy editor command classes | Their own | Unchanged; the legacy editor stays this milestone |

## Fixed along the way

- **MCP server on mcp 2.x.** `pyproject` declares `mcp>=1.0`, so a fresh install got 2.x, where `FastMCP` is `MCPServer`. The server then refused to start for every new developer. It now runs on either version.
- **The one-call add tool.** `live_add_entity_from_prefab` reported success when the change could not apply, and left the failed proposal in the inbox.

## Regression

| Check | Result |
|---|---|
| Milestone 1 acceptance | 15/15 |
| Milestone 2 acceptance | 23/23 |
| Milestone 3 acceptance | 15/15 |
| Milestone 4 acceptance | 20/20 |
| Milestone 5 acceptance | 17/17 |
| Milestone 6 co-authoring | 14/14 |
| MCP, AIOps, live-bridge and creator-mode tests | 630 pass, now with the real `mcp` SDK installed |
| Full suite | 9 failed, 9,341 passed: exactly the 9 baseline failures, none new. The ruff gate and mypy island are clean. |
