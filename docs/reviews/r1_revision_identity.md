# R1: session-safe AI revision identity

#462 R1. An AI's revision read in one Mesh Studio session could pass for the same-numbered revision of the next one,
after Studio restarted, so its old proposal was staged and accepted with no stale-base check over the person's
saved work.

**Verdict: READY FOR INDEPENDENT REVIEW.**

Base `ee04d03c2bf9225e369f5de6ea50dbecd13159ee`. Evidence: `docs/reviews/r1_revision_identity_evidence/`.

## 1. The defect, reproduced

Two genuine Studio lifetimes, each its own process with Studio's project, AI host and loopback bridge (the R2 helper
`tests/studio_owner_process.py`); the AI is `engine.authoring_session`, what the MCP tools and `mesh author` call
(`repro_r1.py.txt`).

| step | baseline `ee04d03c` (`repro_before.json`) | with the fix (`repro_after.json`) |
|---|---|---|
| the AI reads in lifetime A | revision 0 | revision 0, `revision_id` `<A>:0` |
| the person renames the Warden "Creator Warden" and saves | saved | saved |
| Studio closes and opens (lifetime B) | revision 0 again | revision 0 again |
| the AI proposes its rename on revision 0 | **staged**, base revision 0 | refused, `revision_id_required` |
| ... on `revision_id` `<A>:0` | (no such thing) | refused, `revision_from_another_session` |
| the person's inbox | the proposal | empty |
| the person accepts it | **applied with no conflict**: "AI Warden" over "Creator Warden" | (nothing to accept) |
| undo | brings "Creator Warden" back | (not needed) |
| the saved rename on disk | intact (not saved over in the script) | intact |

The central regression (`test_a_revision_read_before_studio_restarted_never_passes_for_the_reopened_project`)
failed on the baseline before anything else changed: "the revision read before the restart was taken as the
reopened project's" (`regression_before.txt`).

## 2. Root cause

`Project.revision` starts at 0 each time a project is opened and goes up with every change, undo and redo. It is a
counter within one opening. The AI host keeps snapshots by that number and checks `base_revision` against it, so a
number read in an earlier opening was indistinguishable from the same number now. Revision 0 of lifetime B was
taken as the AI's base: the proposal was compared with today's project, the person's rename was in "the base", and
the AI's change met it as no conflict.

Where revisions live (traced): created by `Project` (`studio_project.py`); returned by
`StudioAIHost.read_live_scene` through the bridge's `/live/read_scene` to `authoring_session.read_project`, the MCP
`read_project` and `mesh author read`; stored as F6 snapshots (`StudioAIHost._snapshots`, by number); submitted as
`base_revision` by `authoring_session.propose` (MCP `propose_changes`, `mesh author propose --base-revision`) and by
in-process callers of `stage_proposal_payload` (tools, tests); checked in `StudioAIHost._base`; used at approval by
`StudioAIHost.accept` (`project.revision != proposal.base_revision` decides whether to compare). The legacy
editor's live ops have their own `content_revision` and take no base from the request; they are not this path.

## 3. The identity chosen

`Project.session`: 16 random hex digits (`secrets.token_hex(8)`), made when a project is opened and never saved.
A reading's identity is `revision_id = "<session>:<revision>"`.

- **Unique across restarts, crashes and projects:** every opening draws a new session; nothing counts, persists or
  resets. Two sessions both at revision 0 have different ids (asserted). A project in another Studio has another
  session.
- **No new state anywhere:** no file, no database, no format change. The number keeps its meaning (a local
  counter), and F6 snapshots stay keyed by it: a Studio has one project for its lifetime (`Studio.project` is set
  once), so within a host only the session needs checking.
- **Why not the bridge's `session_id`:** it belongs to the live-session bridge, which can stop and start while the
  project stays open (its revisions still valid), and it says nothing about the project. The project's own opening
  is what revisions count in.

## 4. Public API

| | before | now |
|---|---|---|
| `read_project` (Studio open) | `revision` | `revision` (unchanged) **and `revision_id`** |
| `read_project` (files) | `revision: null` | also `revision_id: null` |
| `propose_changes` / `authoring_session.propose` | `base_revision` (int) | **`base_revision_id`** (str); `base_revision` kept, see below |
| `mesh author propose` | `--base-revision N` | **`--base-revision-id ID`**; `--base-revision` kept, see below |
| proposal view | `base_revision` | also `base_revision_id`: the verified base, or `null` when proposed with no base |
| new refusal reasons | | `revision_id_required`, `revision_from_another_session` |

**Old numeric revisions** (intentional compatibility change): a bare `base_revision` is refused with
`revision_id_required`, current or not, kept or not. A number can't say which session it was read in, so it can't be
validated safely; the message says to read again and send `revision_id` as `base_revision_id`. A malformed number is
still `invalid_base_revision`, as before. `base_revision` sent with `base_revision_id` must name the same revision.

**Unbased proposals** keep their documented meaning: no base at all is checked against the project as it is now. The
proposal's `base_revision_id` is `null` there, telling it apart from one whose base was verified.

**No refusal hands out the current `revision_id`.** A tool gets it by reading the project, with what the person has
changed since; otherwise a careless retry could rebase onto work it never saw.

## 5. Behaviour

`StudioAIHost._base(base_revision, base_revision_id)`, in order:

1. neither given: the project as it is now, no verified base;
2. a `base_revision` that isn't a revision (not a whole number, out of range): `invalid_base_revision` (unchanged);
3. a number with no id: `revision_id_required`;
4. an id that isn't one read_project gave (`REVISION_ID`: exactly `<16 hex>:<n>`): `invalid_base_revision`;
5. an id of another session or project: `revision_from_another_session`;
6. a number and an id that disagree, or an id naming a revision this session hasn't had: `invalid_base_revision`;
7. this session's current revision: the project as it is now; an older one Studio keeps: its snapshot (F6);
8. an older one it no longer keeps: `base_revision_unavailable` (F6, unchanged).

Every refusal stages nothing: nothing in the person's inbox, no project document or file changed. Accepting,
rejecting, conflicts, undo and redo are untouched: `accept` compares the proposal's snapshot with the project
exactly as before, and an accepted proposal is still one undo step.

## 6. Evidence

**Across real restarts** (`tests/test_studio_revision_identity.py`, 3 tests, separate Studio processes):

- the reproduction: lifetimes A and B both at revision 0 have different ids; the old number and A's id are refused
  in B; B's inbox empty, the files byte-identical, the saved rename on disk; B's own fresh id is staged, shows what
  it replaces, is accepted, and undo and redo work;
- after a crash: the crashed session's id is refused; B's own is staged and the person's reject changes nothing;
- another project: two Studios on two projects, both at revision 0, different ids; one's id is refused by the other,
  and nothing reaches either inbox.

**Mesh Studio itself** (`tests/test_studio_revision_identity_gpu.py`, 1 test, GPU lane): the same through
`open_studio` in real hidden windows: Studio's own way of opening a project gives each opening its identity.

**Same session** (`tests/test_studio_ai_base_revision.py`, F6, integration; `tests/test_studio_ai_base_revision_policy.py`, fast):
an older kept revision is compared with its own snapshot (separate edits survive, the same property both ways is a
conflict); eviction is refused (`base_revision_unavailable`), never rebased; the current revision needs no snapshot;
unbased proposals as documented (`base_revision_id` null); malformed ids (15 shapes, including a future revision,
upper case, spaces, a leading zero, lists, objects) and a number and an id that disagree are refused; a bare number
is refused for current, kept and evicted revisions; ids of another session are refused; the bridge itself, the MCP
tool and `mesh author propose` (its own process) refuse a bare number and another session's id with the same reason,
and take the reading's own id.

**Deliberate faults** (`faults.json`, `mutate.py.txt`): 6 of 6 fail a test: the session never compared; a bare
current number accepted; every opening with the same identity; a future number of this session accepted; a refusal
handing out the current id; an unbased proposal reported as verified.

**Local** (Windows): the revision, proposal, write-set, identity, authoring, MCP, CLI, creator-mode, co-creative and
bridge modules with the R2 ownership tests, 998 passed; the real-window revision, write-set and ownership tests, 4
passed; ruff and mypy. Linux is CI's.

## 7. Existing tests and tools changed

A bare number is refused now, so callers that proposed against `read["revision"]` propose against
`read["revision_id"]`: `tests/test_studio_ai_write_set.py`, `tests/test_studio_ai_identity.py` (their `_propose`
helpers), `tests/test_authoring_session.py`, `tests/test_proposal_memory.py`, `tests/test_studio_ai_write_set_gpu.py`,
`tests/test_studio_ai_base_revision.py` (F6, plus new cases), `tests/test_studio_ai_base_revision_policy.py` (its
fake project has a session; new cases), and the tools `tooling/acceptance_ai_coauthoring.py`,
`tooling/f10_proposal_memory.py`, `tooling/hd2d_post_studio.py`. What they assert is unchanged.
`tests/studio_owner_process.py` (R2's helper) gained test-only commands: rename, undo, redo, reject.

## 8. Limits

- **Older clients that send `base_revision`** are refused until they send `base_revision_id` (by design; the message
  says how).
- **`docs/generated/cli_snapshot.json`** was already out of date on the baseline (it lacks R2's `mesh author recover`
  and F13-B's `--reuse-evidence` flags; its `--verify` reports only). Regenerating it would carry those unrelated
  changes, so it is left as it was: it doesn't show `--base-revision-id` either.
- **The legacy editor's live ops** (`content_revision`) are not changed: they take no base from the request.
- **Not addressed:** R3 (ids reused for structures, rivers, dialogue lines).
