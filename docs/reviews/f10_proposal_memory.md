# F10: bounded AI proposal memory (#422)

## The problem

When an AI proposes changes to a project open in Mesh Studio (`propose_changes`), Studio keeps two whole-project
copies with each proposal (`engine/studio_ai.py`, `Proposal`):

- `base`: what the tool read;
- `after`: the result of its changes, from a dry run.

It needs them to compare the AI's changes with the person's own edits when the person accepts.

Before F10, Studio kept every proposal, with both copies and its changes, for the rest of the session: accepted,
rejected and failed ones as much as waiting ones. A second, unexpected holder was the live-session bridge's map of
proposals (`EditorLiveSessionBridge._proposals`). It lets go of a proposal only when the tool accepts or withdraws it
over the bridge. When the person decided in Studio, as they always do for acceptance, the bridge kept the proposal,
copies included.

## What a decided proposal needs

The only reader of `base`, `after` and `changes` is `StudioAIHost.accept`: it compares for conflicts and applies.
Every other reader uses the proposal's identity and record:

| reader | uses |
|---|---|
| `Proposal.view()` | `proposal_status` over MCP, Studio's layout dump |
| Studio's AI panel | `title`, `source`, `summary`, `status`, `message`, `conflicts` |
| `Studio.accept_ai` | `created` |

`accept` refuses a decided proposal before it touches the documents: `{"ok": false, "reason": <its status>}`.

## The change

- **Releasing on decision:** `Proposal.settle(status, message)` is the one place a decision becomes final
  (`accepted`, `rejected` or `failed`). It replaces `base`, `after` and `changes` with empty values. It never empties
  them in place, so nothing else holding the same objects loses them.
- **What stays:**
  - the proposal's id, title, source, status, summary, message, conflicts, created ids and base revision;
  - so `proposal_status`, Studio's history and `accept_ai` are unchanged.
- **Waiting proposals keep everything:** a proposal `pending` or in `conflict` still waits for the person, so it
  keeps both copies and its changes. Conflict detection is unchanged, and a proposal in conflict can still be
  accepted once the clash is gone (for example, after the person undoes their edit).
- **A limit on waiting proposals:** at most `PENDING_MAX` = 20 proposals wait at once, pending or in conflict.
  - **The refusal:** a 21st is refused before its dry run: `{"ok": false, "reason": "too_many_pending", "pending",
    "limit", "message"}`. Nothing is staged, and nothing appears in the person's inbox.
  - **Freeing a place:** accepting, rejecting or withdrawing one frees a place.
- **Bounded history:** Studio remembers the last `HISTORY_KEPT` = 100 decided proposals, already released. Older
  ones are forgotten by Studio and by the bridge together (`EditorLiveSessionBridge.forget_proposal`), so neither
  keeps anything alive. A forgotten one answers `proposal_not_found`, saying how many are kept.

The human-approval requirement and the proposal architecture are unchanged.

## Measurements

`tooling/f10_proposal_memory.py` runs a long session on a disposable, realistically populated project: the starter
room plus eight rooms, each with a 64 × 48 map painted on two layers and twenty people. The project's documents
come to about 600 KB as JSON.

The session runs as in Studio, without a window:

- **Setup:** Studio's AI host with its live session on.
- **The AI's side:** the AI proposes through the MCP path (`propose`, `proposal_status`, `withdraw`).
- **The person's side:**
  - they accept most proposals and reject some;
  - some proposals fail on acceptance, because the person removed the same person first;
  - some end in a conflict with the person's own rename;
  - the last two conflicts are still waiting at the end.
- **Measured afterwards, after garbage collection:**
  - `proposal_copies`: how many proposals still hold whole-project documents;
  - `exclusive`: the bytes reachable only through the proposals (Studio's list and the bridge's map), excluding what
    the project itself (documents, undo history) and the F6 revision snapshots hold anyway;
  - `traced`: everything Python allocated during the session and still holds (tracemalloc), for scale.

Before is the unchanged engine at `9620d8f` (in a temporary worktree, removed afterwards); after is F10. Both run the
same script. Windows, Python 3.13.

| proposals | engine | kept (Studio / bridge) | holding copies | exclusive | traced |
|---|---|---|---|---|---|
| 120 | before | 120 / 100 | 120 | 380.0 MB | 596.8 MB |
| 120 | F10 | 102 / 85 | 2 | 6.5 MB | 223.4 MB |
| 240 | before | 240 / 200 | 240 | 785.6 MB | 1,067.6 MB |
| 240 | F10 | 102 / 85 | 2 | 6.9 MB | 288.9 MB |

- **Growth before:** about 3.3 MB per proposal kept only for proposals (the two copies, as Python objects), on a
  project of 0.6 MB as JSON. It grows without limit.
- **With F10, flat:** only the proposals still waiting hold copies; here, the two in conflict.
- **What `traced` still includes:** with F10, that growth is the project's own undo history and the F6 revision
  snapshots (at most 30). Both are outside F10.

## Tests

`tests/test_proposal_memory.py` (7 tests, integration, headless):

- **Decided proposals:** accepted, rejected and failed proposals let go of both copies and their changes. No
  whole-project document is reachable from them, their view and status query stay identical, history is truthful,
  and nothing is written to the files.
- **Conflicts:** a proposal in conflict keeps its copies. A separate edit is still accepted alongside, and the
  conflicting one is accepted once the person undoes their clash.
- **Undo:** it still takes an accepted proposal back, and redo restores it.
- **F6 snapshots:** a revision snapshot the proposal was based on stays intact after release.
- **Over MCP:**
  - the 21st waiting proposal is refused, `too_many_pending`, with nothing staged, and a withdrawal frees a place;
  - decided history is bounded, the bridge forgets with Studio, and a forgotten proposal answers
    `proposal_not_found`;
  - a status query for a proposal released after the person accepted it is still truthful.

**Against the unchanged `studio_ai.py` and bridge** (with only the two new constants added so the tests can be
collected), all 7 fail.

## Limitations

- **The undo history isn't bounded:** each accepted change keeps the project's undo snapshot, as before. That and
  the 30 F6 revision snapshots are what remains of a long session's growth.
- **Conflicts are kept as they are:** a decided proposal keeps its `conflicts` records, leaf-level values from both
  sides for the person and the tool to see. They aren't capped.
- **The limit counts waiting proposals only:** a tool that keeps 20 waiting can't stage more until the person
  decides, by design.
- **The history keeps 100 decided proposals;** a status query for an older one answers `proposal_not_found`.
