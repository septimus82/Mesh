"""AI proposals for Mesh Studio: changes from outside (an AI over MCP, a script) that a person reviews.

An outside tool sends a batch of ``engine.authoring`` changes over the loopback live-session
bridge (``engine.editor.live_session_bridge``, the same transport the legacy editor uses).
Studio never applies them on its own:

- **Staging** checks the batch on a copy of the project, as of the revision the tool read
  (``base_revision``), and lists what it would change. A batch that can't apply is refused
  straight back to the tool with the reason.
- **Accept** (a person, in Studio) applies the batch to the open documents as one undo step.
  If the person changed the project since the tool read it, both sets of changes are compared
  property by property: separate edits (a painted floor, a new NPC) both survive; the same
  property changed both ways is a conflict, reported, and nothing is applied.
- **Reject** leaves the project as it was.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any

from engine import authoring

Doc = dict[str, Any]
SNAPSHOTS_KEPT = 30


@dataclass
class Proposal:
    changes: list[Doc]
    title: str
    source: str
    base_revision: int
    base: Doc
    after: Doc
    summary: list[str]
    proposal_id: str = ""
    status: str = "pending"  # pending | accepted | rejected | conflict | failed
    message: str = ""
    conflicts: list[Doc] = field(default_factory=list)
    created: dict[int, str] = field(default_factory=dict)
    staged_at: float = field(default_factory=time.time)

    def view(self) -> Doc:
        return {"proposal_id": self.proposal_id, "title": self.title, "source": self.source, "status": self.status,
                "message": self.message, "summary": list(self.summary), "conflicts": list(self.conflicts),
                "base_revision": self.base_revision, "created": {str(k): v for k, v in self.created.items()}}


class StudioAIHost:
    """The bridge's host for Mesh Studio (it duck-types the legacy editor's live-ops methods)."""

    host_kind = "mesh_studio"

    def __init__(self, studio: Any) -> None:
        self.studio = studio
        self.window = studio.window  # the bridge reads window.scene_controller for the current room
        self.proposals: list[Proposal] = []
        self._snapshots: dict[int, Doc] = {}
        self.bridge: Any = None

    @property
    def project(self) -> Any:
        return self.studio.project

    # ------------------------------------------------------------------ bridge lifecycle
    def start(self) -> None:
        from engine.editor.live_session_bridge import EditorLiveSessionBridge  # noqa: PLC0415

        self.bridge = EditorLiveSessionBridge(self, self.project.root)
        self.bridge.start()

    def stop(self) -> None:
        if self.bridge is not None:
            self.bridge.stop()
            self.bridge = None

    def drain(self) -> None:
        if self.bridge is not None:
            self.bridge.drain_pending()

    # ------------------------------------------------------------------ what the tool reads
    def read_live_scene(self, *, compact: bool = False) -> Doc:  # noqa: ARG002 - the bridge's read endpoint
        """The whole open project (unsaved edits included) and its revision, to base changes on."""
        docs = copy.deepcopy(self.project.all_documents())
        self._remember(self.project.revision, docs)
        rooms = {key: {"label": label, "path": path, "room": docs["rooms"][key]} for key, label, path in self.project.rooms()}
        return {"ok": True, "mode": "live_studio", "revision": self.project.revision, "current_room": self.project.current,
                "unsaved": self.project.is_dirty, "world": docs["world"], "rooms": rooms,
                "models": authoring.models(self.project)}

    def _remember(self, revision: int, docs: Doc) -> None:
        self._snapshots[revision] = docs
        for old in sorted(self._snapshots)[:-SNAPSHOTS_KEPT]:
            del self._snapshots[old]

    # ------------------------------------------------------------------ staging
    def stage_proposal_payload(self, payload: Doc) -> Proposal | Doc:
        changes = payload.get("changes", payload.get("ops"))
        if not isinstance(changes, list):
            return {"ok": False, "mode": "live_studio", "reason": "invalid_change", "index": 0, "op": "",
                    "message": "A proposal needs its changes as a list."}
        title = str(payload.get("title") or "Changes from an AI").strip()[:80]
        source = str(payload.get("source") or "an AI").strip()[:60]
        revision = payload.get("base_revision")
        current = self.project.revision
        base_revision = int(revision) if isinstance(revision, int) and revision in self._snapshots else current
        base = self._snapshots[base_revision] if base_revision != current else copy.deepcopy(self.project.all_documents())
        try:
            before, after = authoring.dry_run(self.project, changes, base=base)
        except authoring.ChangeError as err:
            return {"ok": False, "mode": "live_studio", "reason": "invalid_change", "index": err.index, "op": err.op,
                    "message": str(err)}
        proposal = Proposal(changes=copy.deepcopy(changes), title=title, source=source, base_revision=base_revision,
                            base=before, after=after, summary=authoring.summarize(before, after) or ["(no visible change)"])
        self.proposals.append(proposal)
        self.studio.on_ai_proposal(proposal)
        return proposal

    def stage_proposal(self, ops: list[Doc]) -> Proposal | Doc:
        """The legacy editor's signature: stage a bare list of changes."""
        return self.stage_proposal_payload({"changes": ops})

    # ------------------------------------------------------------------ decisions
    def accept_proposal(self, proposal: Proposal) -> Doc:  # noqa: ARG002 - the bridge's accept endpoint
        """Outside tools can't accept: the person in Studio decides."""
        return {"ok": False, "mode": "live_studio", "reason": "needs_person",
                "message": "Mesh Studio applies outside changes only when the person accepts them there."}

    def reject_proposal(self, proposal: Proposal) -> Doc:
        """Withdraw a proposal (the tool that made it may do this too)."""
        if proposal.status in ("pending", "conflict"):
            proposal.status, proposal.message = "rejected", "Rejected: nothing changed."
            self.studio.on_ai_decided(proposal)
        return {"ok": True, "mode": "live_studio", "status": proposal.status}

    def proposal_status(self, proposal_id: str) -> Doc:
        found = next((p for p in self.proposals if p.proposal_id == proposal_id), None)
        if found is None:
            return {"ok": False, "mode": "live_studio", "reason": "proposal_not_found"}
        return {"ok": True, "mode": "live_studio", "proposal": found.view(), "revision": self.project.revision}

    def accept(self, proposal: Proposal) -> Doc:
        """The person accepted: apply on top of whatever they have done since, unless it clashes."""
        if proposal.status not in ("pending", "conflict"):
            return {"ok": False, "reason": proposal.status}
        if self.project.revision != proposal.base_revision:
            ours = authoring.changes_between(proposal.base, self.project.all_documents())
            theirs = authoring.changes_between(proposal.base, proposal.after)
            clashes = authoring.conflicts(ours, theirs)
            if clashes:
                proposal.status, proposal.conflicts = "conflict", clashes
                proposal.message = (f"Not applied: {len(clashes)} place(s) were changed both here and by the proposal. "
                                    "Nothing was lost; reject it and ask for a new one.")
                return {"ok": False, "reason": "conflict", "conflicts": clashes}
        try:
            result = authoring.apply(self.project, proposal.changes)
        except authoring.ChangeError as err:
            proposal.status, proposal.message = "failed", f"Not applied: {err}"
            return {"ok": False, "reason": "invalid_change", "message": str(err)}
        proposal.status, proposal.created = "accepted", dict(result["created"])
        proposal.message = f"Accepted: {len(proposal.summary)} change(s). Undo takes them back."
        return {"ok": True, "created": proposal.created, "revision": self.project.revision}

    def pending(self) -> list[Proposal]:
        return [p for p in self.proposals if p.status in ("pending", "conflict")]
