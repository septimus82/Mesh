from __future__ import annotations

from typing import Any


class ProposalInbox:
    """Main-thread model for staged AI proposals owned by the live bridge."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def list_pending(self) -> list[dict[str, Any]]:
        bridge = getattr(self._editor, "live_bridge", None)
        list_pending = getattr(bridge, "list_pending_proposals", None)
        if not callable(list_pending):
            return []
        proposals = list_pending()
        return proposals if isinstance(proposals, list) else []

    def accept(self, proposal_id: str) -> dict[str, Any]:
        bridge = getattr(self._editor, "live_bridge", None)
        accept = getattr(bridge, "accept_pending_proposal", None)
        if not callable(accept):
            return {"ok": False, "mode": "live_editor", "reason": "no_live_session"}
        return dict(accept(str(proposal_id)))

    def reject(self, proposal_id: str) -> dict[str, Any]:
        bridge = getattr(self._editor, "live_bridge", None)
        reject = getattr(bridge, "reject_pending_proposal", None)
        if not callable(reject):
            return {"ok": False, "mode": "live_editor", "reason": "no_live_session"}
        return dict(reject(str(proposal_id)))
